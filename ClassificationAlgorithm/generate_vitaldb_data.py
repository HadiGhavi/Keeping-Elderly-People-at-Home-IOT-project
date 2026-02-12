import vitaldb
import pandas as pd
import numpy as np
import ssl
import certifi
import os
from scipy import signal

# SSL setup for vitaldb connection
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

def get_eligible_patients(min_age=60, max_cases=10):
    """Find elderly patients in the Clinical Info"""
    print("Fetching clinical info...")
    try:
        clinical_df = pd.read_csv("https://api.vitaldb.net/cases")
        clinical_df['age'] = pd.to_numeric(clinical_df['age'], errors='coerce')
        eligible = clinical_df[clinical_df['age'] > min_age]
        case_ids = eligible['caseid'].tolist()
        print(f"Found {len(case_ids)} patients > {min_age} years old.")
        return case_ids[:max_cases]
    except Exception as e:
        print(f"Error fetching cases: {e}")
        return []

# --- ECG & HRV Processing ---

def detect_r_peaks(ecg_signal, sampling_rate=500):
    """Detects R-peaks in an ECG signal."""
    # Bandpass filter (0.5 - 40 Hz)
    nyquist = sampling_rate / 2
    low = 0.5 / nyquist
    high = 40 / nyquist
    b, a = signal.butter(4, [low, high], btype='band')
    filtered_ecg = signal.filtfilt(b, a, ecg_signal)
    
    # Square the signal
    squared = filtered_ecg ** 2
    
    # Find peaks
    peak_distance = int(0.3 * sampling_rate) # ~200 bpm max
    threshold = np.mean(squared) + 0.5 * np.std(squared)
    peaks, _ = signal.find_peaks(squared, distance=peak_distance, height=threshold)
    return peaks

def calculate_hrv_features(rr_intervals):
    """Calculates HRV features from R-R intervals (seconds)."""
    if len(rr_intervals) < 5:
        return {'mean_hr': np.nan, 'sdnn': np.nan, 'rmssd': np.nan}
    
    sdnn = np.std(rr_intervals)
    successive_diffs = np.diff(rr_intervals)
    rmssd = np.sqrt(np.mean(successive_diffs ** 2))
    mean_hr = 60 / np.mean(rr_intervals)
    return {'mean_hr': mean_hr, 'sdnn': sdnn, 'rmssd': rmssd}

def process_ecg_chunk(ecg_data, sampling_rate=500, window_sec=30):
    """
    Process ECG stream in chunks to get HRV.
    Returns DataFrame with timestamp and HRV metrics.
    """
    # ecg_data is a numpy array or list of values
    # We want to create a time series of features
    
    samples_per_window = window_sec * sampling_rate
    num_windows = len(ecg_data) // samples_per_window
    
    results = []
    
    for i in range(num_windows):
        start = i * samples_per_window
        end = start + samples_per_window
        chunk = ecg_data[start:end]
        
        # Detect peaks
        peaks = detect_r_peaks(chunk, sampling_rate)
        
        # Calculate HRV
        if len(peaks) > 1:
            rr = np.diff(peaks) / sampling_rate
            feats = calculate_hrv_features(rr)
        else:
            feats = {'mean_hr': np.nan, 'sdnn': np.nan, 'rmssd': np.nan}
            
        # Timestamp = middle of window
        # Assuming data starts at 0 and is continuous
        time_sec = (start + end) / 2 / sampling_rate
        feats['time'] = time_sec
        results.append(feats)
        
    return pd.DataFrame(results)

def classify_multimodal_risk(row):
    """
    Classify based on Vitals + HRV.
    Returns: 'healthy', 'risky', 'dangerous'
    """
    score = 0
    
    # 1. Vitals
    hr = row.get('heart_rate', np.nan)
    spo2 = row.get('blood_oxygen', np.nan)
    temp = row.get('temperature', np.nan)
    
    if pd.isna(hr) or pd.isna(spo2) or pd.isna(temp):
        return 'unknown'

    # Dangerous Vitals
    if hr < 40 or hr > 130: score += 3
    if spo2 < 88: score += 4
    if temp > 39 or temp < 35: score += 4 # Increased from 3 to 4 (Automatic Dangerous)
    
    # Risky Vitals
    if (40 <= hr < 50) or (110 < hr <= 130): score += 1
    if (88 <= spo2 < 92): score += 2
    if (38.0 < temp <= 39) or (35 <= temp < 36): score += 2 # Increased from 1 to 2 (Guaranteed Risky)

    # 2. HRV (if available)
    sdnn = row.get('sdnn', np.nan)
    rmssd = row.get('rmssd', np.nan)
    
    # Low HRV = Stress/Risk
    if not pd.isna(sdnn):
        if sdnn < 0.015: score += 2  # Very low variability
        elif sdnn < 0.030: score += 1
        
    if not pd.isna(rmssd):
        if rmssd < 0.010: score += 1

    # Thresholds
    if score >= 4: return 'dangerous'
    if score >= 2: return 'risky'
    return 'healthy'

def simulate_fever(df_vitals):
    """
    Simulate a fever event by increasing temperature.
    """
    # Create a copy to avoid checking caveats
    df = df_vitals.copy()
    
    # 50% chance of a gradual rise, 50% chance of a high constant fever
    if np.random.rand() > 0.5:
        # Gradual rise
        # t is 0...N
        n = len(df)
        rise = np.linspace(0, 3.5, n) # rise by up to 3.5 degrees
        df['temperature'] = df['temperature'] + rise
        # Fever causes tachycardia (~10 bpm per degree)
        df['heart_rate'] = df['heart_rate'] + (rise * 10)
    else:
        # Constant high fever (fluctuating around 38-39.5)
        df['temperature'] = np.random.uniform(38.0, 39.5, len(df))
        # HR increase for constant fever (approx +20-30 bpm)
        df['heart_rate'] = df['heart_rate'] + np.random.uniform(20, 30, len(df))
        
    return df

def generate_vitaldb_dataset():
    # 1. Get Patients
    # Increase cases SIGNIFICANTLY to ensure we have enough Healthy data to balance against Dangerous
    case_ids = get_eligible_patients(min_age=65, max_cases=80) 
    if not case_ids:
        print("No cases found.")
        return

    # 2. Tracks to download
    # Vitals (low freq) + ECG (high freq, usually 500Hz)
    
    vital_tracks = ['Solar8000/HR', 'Solar8000/PLETH_SPO2', 'Solar8000/BT']
    ecg_track = 'SNUADC/ECG_II'
    
    all_data = []
    
    print(f"Downloading data for {len(case_ids)} patients...")
    
    # Setup for fever injection
    fever_count = 0
    
    for i, case_id in enumerate(case_ids):
        print(f"Processing Case {case_id} ({i+1}/{len(case_ids)})...")
        try:
            # A. Get Vitals (5s interval)
            # ------------------------------------------------
            vitals = vitaldb.load_case(case_id, vital_tracks, interval=5)
            df_vitals = pd.DataFrame(vitals, columns=['heart_rate', 'blood_oxygen', 'temperature'])
            df_vitals['timestamp'] = np.arange(len(df_vitals)) * 5 # relative time seconds
            
            # Clean Vitals
            df_vitals = df_vitals.dropna()
            df_vitals = df_vitals[
                (df_vitals['heart_rate'] > 20) & (df_vitals['heart_rate'] < 200) &
                (df_vitals['blood_oxygen'] > 50) & (df_vitals['blood_oxygen'] <= 100) &
                (df_vitals['temperature'] > 30) & (df_vitals['temperature'] < 42)
            ]
            
            if df_vitals.empty: continue
            
            # AUGMENTATION: Inject Fever
            # Apply to ~20% of patients (Reduced to bias towards Healthy)
            if np.random.rand() < 0.2:
                print(f"  -> Injecting simulated FEVER event for Case {case_id}")
                df_vitals = simulate_fever(df_vitals)
                fever_count += 1

            # B. Get ECG (High Freq) -> Compute HRV
            # ------------------------------------------------
            # Load raw ECG (no interval = max res)
            
            # Use 0.004s (250Hz).
            ecg_vals = vitaldb.load_case(case_id, [ecg_track], interval=0.004) 
            ecg_sig = ecg_vals[:, 0]
            ecg_sig = ecg_sig[~np.isnan(ecg_sig)] # drop nans
            
            if len(ecg_sig) < 250 * 60: # need at least a minute
                print("  -> Insufficient ECG data")
                # Fallback: Just use vitals without HRV
                df_hrv = pd.DataFrame({'time': [], 'sdnn': [], 'rmssd': []})
            else:
                # Compute HRV in 30s windows
                df_hrv = process_ecg_chunk(ecg_sig, sampling_rate=250, window_sec=30)
                
            # C. Merge Vitals and HRV
            # ------------------------------------------------
            # We have df_vitals (time=0, 5, 10...) and df_hrv (time=15, 45, 75...)
            # Use merge_asof
            
            # Fix type mismatch: ensure both are float
            df_vitals['timestamp'] = df_vitals['timestamp'].astype(float)
            df_hrv['time'] = df_hrv['time'].astype(float)
            
            df_vitals = df_vitals.sort_values('timestamp')
            df_hrv = df_hrv.sort_values('time')
            
            # If no HRV, we just fill NaNs
            if df_hrv.empty:
                df_merged = df_vitals.copy()
                df_merged['sdnn'] = np.nan
                df_merged['rmssd'] = np.nan
            else:
                df_merged = pd.merge_asof(
                    df_vitals, 
                    df_hrv, 
                    left_on='timestamp', 
                    right_on='time', 
                    direction='nearest', 
                    tolerance=30 # look up to 30s away
                )
                
            # D. Generate Labels (Multimodal)
            # ------------------------------------------------
            statuses = df_merged.apply(classify_multimodal_risk, axis=1)
            df_merged['status'] = statuses
            df_merged['patient_id'] = f"V{case_id}"
            
            # Select columns
            cols = ['timestamp', 'patient_id', 'temperature', 'heart_rate', 'blood_oxygen', 'sdnn', 'rmssd', 'status']
            # fill missing cols if any
            for c in cols:
                if c not in df_merged.columns: df_merged[c] = np.nan
                
            df_final = df_merged[cols]
            
            # Limit rows per patient
            if len(df_final) > 1000:
                df_final = df_final.iloc[:1000]
                
            all_data.append(df_final)
                
        except Exception as e:
            print(f"Failed to load case {case_id}: {e}")
            continue

    if not all_data:
        print("No valid data extracted.")
        return

    # 3. Combine and Save
    full_df = pd.concat(all_data, ignore_index=True)
    
    output_file = 'time_series_health_data.csv'
    full_df.to_csv(output_file, index=False)
    
    print(f"\nSUCCESS. Saved {len(full_df)} samples to {output_file}")
    print("Status Distribution:")
    print(full_df['status'].value_counts())
    print("\nColumns:", full_df.columns.tolist())

if __name__ == "__main__":
    generate_vitaldb_dataset()
