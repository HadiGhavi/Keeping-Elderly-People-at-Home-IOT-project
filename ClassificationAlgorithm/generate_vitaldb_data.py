import vitaldb
import pandas as pd
import numpy as np
import ssl
import certifi
import os

# SSL setup for vitaldb connection
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

def get_eligible_patients(min_age=60, max_asa=2, max_cases=10):
    """Find elderly patients in the Clinical Info"""
    print("Fetching clinical info...")
    try:
        clinical_df = pd.read_csv("https://api.vitaldb.net/cases")
        clinical_df['age'] = pd.to_numeric(clinical_df['age'], errors='coerce')
        clinical_df['asa'] = pd.to_numeric(clinical_df['asa'], errors='coerce')
        eligible = clinical_df[(clinical_df['age'] > min_age) & (clinical_df['asa'] <= max_asa)]
        case_ids = eligible['caseid'].tolist()
        print(f"Found {len(case_ids)} patients > {min_age} years old and ASA <= {max_asa}.")
        return case_ids[:max_cases]
    except Exception as e:
        print(f"Error fetching cases: {e}")
        return []

def inject_anomaly(df, target_status):
    """
    Inject physiologically consistent noise to create risky or dangerous states.
    Refined for subtler anomalies.
    """
    df = df.copy()
    if target_status == 'healthy':
        return df, 'healthy'
    
    # Randomly pick an anomaly type
    anomaly_type = np.random.choice(['fever', 'hypoxia', 'cardiac_stress'])
    
    if anomaly_type == 'fever':
        # Fever: High temp, High HR
        if target_status == 'risky':
            # Subtler: 0.7 to 1.2 degrees
            temp_inc = np.random.uniform(0.7, 1.2)
        else: # dangerous
            # 2.0 to 3.0 degrees
            temp_inc = np.random.uniform(2.0, 3.0)
            
        df['temperature'] += temp_inc
        df['heart_rate'] += (temp_inc * 8) + np.random.normal(0, 2, len(df))
        
    elif anomaly_type == 'hypoxia':
        # Hypoxia: Low SpO2, High HR (compensatory)
        if target_status == 'risky':
            # Subtler: 3 to 5% drop (98 -> 93-95)
            spo2_dec = np.random.uniform(3, 5)
        else: # dangerous
            # 8 to 15% drop (98 -> 83-90)
            spo2_dec = np.random.uniform(8, 15)
            
        df['blood_oxygen'] -= spo2_dec
        df['heart_rate'] += np.random.uniform(5, 15, len(df))

    elif anomaly_type == 'cardiac_stress':
        # Cardiac Stress: High or Low HR
        if target_status == 'risky':
            # Subtler: 1.15x or 0.85x
            hr_mult = np.random.choice([1.15, 0.85])
        else: # dangerous
            # 1.4x or 0.6x
            hr_mult = np.random.choice([1.4, 0.6])
            
        df['heart_rate'] *= hr_mult

    # Clip to physical limits
    df['blood_oxygen'] = df['blood_oxygen'].clip(50, 100)
    df['temperature'] = df['temperature'].clip(34, 42)
    df['heart_rate'] = df['heart_rate'].clip(30, 220)
    
    return df, target_status

def generate_vitaldb_dataset():
    # 1. Get Patients
    case_ids = get_eligible_patients(min_age=65, max_cases=40) 
    if not case_ids:
        print("No cases found.")
        return

    vital_tracks = ['Solar8000/HR', 'Solar8000/PLETH_SPO2', 'Solar8000/BT']
    
    all_data = []
    
    # 2. Assign Target Statuses
    num_cases = len(case_ids)
    target_statuses = (
        ['healthy'] * int(num_cases * 0.8) + 
        ['risky'] * int(num_cases * 0.15) + 
        ['dangerous'] * int(num_cases * 0.05)
    )
    np.random.shuffle(target_statuses)
    while len(target_statuses) < num_cases:
        target_statuses.append('healthy')

    print(f"Downloading data for {len(case_ids)} patients...")
    print(f"Target Distribution: {pd.Series(target_statuses).value_counts().to_dict()}")

    for i, case_id in enumerate(case_ids):
        target_status = target_statuses[i]
        print(f"Processing Case {case_id} ({i+1}/{len(case_ids)}) -> Target: {target_status}")
        
        try:
            # A. Get Vitals (5s interval)
            vitals = vitaldb.load_case(case_id, vital_tracks, interval=5)
            df_vitals = pd.DataFrame(vitals, columns=['heart_rate', 'blood_oxygen', 'temperature'])
            df_vitals['timestamp'] = np.arange(len(df_vitals)) * 5
            
            # CLEANING: Baseline Healthy
            df_vitals = df_vitals.dropna()
            df_vitals = df_vitals[
                (df_vitals['heart_rate'] > 60) & (df_vitals['heart_rate'] < 90) &
                (df_vitals['blood_oxygen'] > 97) & (df_vitals['blood_oxygen'] <= 100) &
                (df_vitals['temperature'] > 36.3) & (df_vitals['temperature'] < 37.0)
            ]
            
            if len(df_vitals) < 100: continue
            
            # B. INJECTION ENGINE
            df_injected, actual_status = inject_anomaly(df_vitals, target_status)
            df_injected['status'] = actual_status
            df_injected['patient_id'] = f"V{case_id}"
            
            # Select columns (NO HRV)
            cols = ['timestamp', 'patient_id', 'temperature', 'heart_rate', 'blood_oxygen', 'status']
            df_final = df_injected[cols]
            if len(df_final) > 1000: df_final = df_final.iloc[:1000]
                
            all_data.append(df_final)
                
        except Exception as e:
            print(f"Failed to load case {case_id}: {e}")
            continue

    if not all_data:
        print("No valid data extracted.")
        return

    # 3. Combine and Save
    full_df = pd.concat(all_data, ignore_index=True)
    output_file = 'ClassificationAlgorithm/time_series_health_data.csv'
    full_df.to_csv(output_file, index=False)
    
    print(f"\nSUCCESS. Saved {len(full_df)} samples to {output_file}")
    print("Status Distribution:")
    print(full_df['status'].value_counts(normalize=True))

if __name__ == "__main__":
    generate_vitaldb_dataset()
