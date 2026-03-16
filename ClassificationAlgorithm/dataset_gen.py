import vitaldb
import pandas as pd
import numpy as np
import ssl
import certifi
from config import Config


# SSL setup for vitaldb connection
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())

def get_eligible_patients(min_age=60, max_asa=1, max_cases=None):
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
    df = df.copy()
    if target_status == 'healthy':
        return df, 'healthy'
    
    anomaly_type = np.random.choice(['fever', 'hypoxia', 'cardiac_stress'])
    
    if anomaly_type == 'fever':
        # Fever: High temp, High HR
        if target_status == 'risky':
            temp_inc = np.random.uniform(0.7, 1.2)
        else: # dangerous
            temp_inc = np.random.uniform(2.0, 3.0)
            
        df['temperature'] += temp_inc
        df['heart_rate'] += (temp_inc * 8) + np.random.normal(0, 2, len(df))
        
    elif anomaly_type == 'hypoxia':
        # Hypoxia: Low SpO2, High HR (compensatory)
        if target_status == 'risky':
            spo2_dec = np.random.uniform(3, 5)
        else: # dangerous
            spo2_dec = np.random.uniform(8, 15)
            
        df['blood_oxygen'] -= spo2_dec
        df['heart_rate'] += np.random.uniform(5, 15, len(df))

    elif anomaly_type == 'cardiac_stress':
        # Cardiac Stress: High or Low HR
        if target_status == 'risky':
            hr_mult = np.random.choice([1.15, 0.85])
        else: # dangerous
            hr_mult = np.random.choice([1.4, 0.6])
            
        df['heart_rate'] *= hr_mult

    # Clipping
    df['blood_oxygen'] = df['blood_oxygen'].clip(50, 100)
    df['temperature'] = df['temperature'].clip(34, 42)
    df['heart_rate'] = df['heart_rate'].clip(30, 220)
    
    return df, target_status

def generate_vitaldb_dataset():
    # 1. Get Patients
    case_ids = get_eligible_patients(min_age=60, max_asa=1) 
    if not case_ids:
        print("No cases found.")
        return

    # Potential temperature tracks
    temp_tracks = ['Solar8000/BT', 'Solar8000/TEMP_ESOPH', 'Solar8000/T1', 'Solar8000/TEMP_SKIN']
    vital_tracks = ['Solar8000/HR', 'Solar8000/PLETH_SPO2']
    
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
            # Load all potential tracks directly. missing_track_behavior='nan' is default.
            current_tracks = vital_tracks + temp_tracks
            
            # Step A: Get Vitals (30s interval)
            vitals = vitaldb.load_case(case_id, current_tracks, interval=30)
            
            df_vitals = pd.DataFrame(vitals, columns=['heart_rate', 'blood_oxygen', 'temp_bt', 'temp_esoph', 'temp_t1', 'temp_skin'])
            
            # Step B: (pick the first temp available)
            def get_first_valid_temp(row):
                for col in ['temp_bt', 'temp_esoph', 'temp_t1', 'temp_skin']:
                    if not pd.isna(row[col]): return row[col]
                return np.nan
            
            df_vitals['temperature'] = df_vitals.apply(get_first_valid_temp, axis=1)
            
            # Clean up temporary temp columns
            df_vitals = df_vitals.drop(columns=['temp_bt', 'temp_esoph', 'temp_t1', 'temp_skin'])
            
            # If temp is still missing, generate synthetic baseline
            if df_vitals['temperature'].isna().all():
                 df_vitals['temperature'] = np.random.normal(36.6, 0.2, len(df_vitals))
                 
            df_vitals['timestamp'] = np.arange(len(df_vitals)) * 30
            df_vitals = df_vitals.dropna(subset=['heart_rate', 'blood_oxygen']) # Temp already handled
            
            #  Baseline filters
            df_vitals = df_vitals[
                (df_vitals['heart_rate'] >= 50) & (df_vitals['heart_rate'] <= 100) &
                (df_vitals['blood_oxygen'] >= 95) & (df_vitals['blood_oxygen'] <= 100) &
                (df_vitals['temperature'] >= 35.5) & (df_vitals['temperature'] <= 37.5)
            ]
            
            if len(df_vitals) < 50: continue
            
            print(f"   Success: Case {case_id} had {len(df_vitals)} valid baseline rows. (Target: {target_status})")
            
            # Add anomalies
            df_injected, actual_status = inject_anomaly(df_vitals, target_status)
            df_injected['status'] = actual_status
            df_injected['patient_id'] = f"V{case_id}"
            
            
            cols = ['timestamp', 'patient_id', 'temperature', 'heart_rate', 'blood_oxygen', 'status']
            df_final = df_injected[cols]
            if len(df_final) > 500: df_final = df_final.iloc[:500]
                
            all_data.append(df_final)
                
        except Exception as e:
            import traceback
            print(f"Failed to load case {case_id}: {type(e).__name__} - {e}")
            continue

    if not all_data:
        print("No valid data extracted.")
        return

    # 3. Save
    full_df = pd.concat(all_data, ignore_index=True)
    output_file = Config.CLASSIFICATION["SAMPLEPATH"]
    full_df.to_csv(output_file, index=False)
    
    print(f"\nSUCCESS. Saved {len(full_df)} samples to {output_file}")
    print("Status Distribution:")
    print(full_df['status'].value_counts(normalize=True))

if __name__ == "__main__":
    generate_vitaldb_dataset()
