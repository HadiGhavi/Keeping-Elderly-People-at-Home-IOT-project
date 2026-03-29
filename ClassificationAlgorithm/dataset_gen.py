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
    n = len(df)
    
    # Dynamic Labeling: transition baseline -> risky -> dangerous
    labels = np.full(n, 'healthy', dtype='object')
    
    if target_status == 'risky':
        labels[int(n*0.25):] = 'risky'
    elif target_status == 'dangerous':
        labels[int(n*0.25):int(n*0.50)] = 'risky'
        labels[int(n*0.50):] = 'dangerous'

    if target_status == 'healthy':
        return df, labels
    
    types = ['fever', 'hypoxia', 'cardiac_stress']
    if target_status == 'dangerous':
        types.append('systemic_crisis')
        
    anomaly_type = np.random.choice(types)
    
    if anomaly_type == 'fever':
        temp_inc = np.random.uniform(0.7, 3.5)
        trend = np.linspace(0, temp_inc, n)
        df['temperature'] += trend + np.random.normal(0, 0.1, n)
        
        if target_status == 'dangerous':
            df['heart_rate'] += trend * 15 + np.random.normal(0, 3, n)
            df['blood_oxygen'] -= trend * 2.5 + np.random.normal(0, 0.5, n)
        else:
            df['heart_rate'] += trend * 8 + np.random.normal(0, 2, n)
            df['blood_oxygen'] -= np.random.uniform(0.5, 1.5, n)

    elif anomaly_type == 'hypoxia':
        spo2_dec = np.random.uniform(3, 18)
        trend = np.linspace(0, spo2_dec, n)
        df['blood_oxygen'] -= trend
        
        if target_status == 'dangerous':
            df['heart_rate'] += trend * 4.0 + np.random.normal(0, 4, n)
        else:
            df['heart_rate'] += trend * 1.5 + np.random.normal(0, 2, n)

    elif anomaly_type == 'cardiac_stress':
        factor = np.random.choice([1.15, 0.85]) if target_status == 'risky' else np.random.choice([1.5, 0.6])
        trend = np.linspace(1, factor, n)
        df['heart_rate'] *= trend
        
        if target_status == 'dangerous':
            df['blood_oxygen'] -= np.linspace(0, 5, n)

    elif anomaly_type == 'systemic_crisis':
        trend = np.linspace(0, 1, n)
        df['temperature'] += trend * 3.0 + np.random.normal(0, 0.1, n)
        df['blood_oxygen'] -= trend * 15 + np.random.normal(0, 0.5, n)
        df['heart_rate'] += trend * 50 + np.random.normal(0, 2, n)

    # clipping realistico
    df['blood_oxygen'] = df['blood_oxygen'].clip(50, 100)
    df['temperature'] = df['temperature'].clip(34, 42)
    df['heart_rate'] = df['heart_rate'].clip(30, 220)

    return df, labels

def generate_vitaldb_dataset():
    np.random.seed(327834)
    # 1. Get Patients
    case_ids = get_eligible_patients(min_age=60, max_asa=1, max_cases=400) 
    if not case_ids:
        print("No cases found.")
        return

    # Potential temperature tracks
    temp_tracks = ['Solar8000/BT', 'Solar8000/TEMP_ESOPH', 'Solar8000/T1', 'Solar8000/TEMP_SKIN']
    vital_tracks = ['Solar8000/HR', 'Solar8000/PLETH_SPO2']
    
    all_data = []
    
    # 2. Assign Target Statuses
    num_cases = len(case_ids)
    probs = [0.60, 0.20, 0.20]  
    target_statuses = np.random.choice(
        ['healthy', 'risky', 'dangerous'], 
        size=num_cases,
        p=probs
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
            tracks = [
                'Solar8000/HR',
                'Solar8000/PLETH_SPO2',
                'Solar8000/BT',
                'Solar8000/TEMP_ESOPH',
                'Solar8000/T1',
                'Solar8000/TEMP_SKIN'
            ]
           
            # Step A: Get Vitals (30s interval)
            vitals = vitaldb.load_case(case_id, tracks, interval=30)
            
            df_vitals = pd.DataFrame(vitals)
            df_vitals.columns = [
                'heart_rate','blood_oxygen',
                'temp_bt','temp_esoph','temp_t1','temp_skin'
            ]            
            # Step B: (pick the first temp available)
            def get_first_valid_temp(row):
                for col in ['temp_bt', 'temp_esoph', 'temp_t1', 'temp_skin']:
                    if not pd.isna(row[col]): return row[col]
                return np.nan
            
            df_vitals['temperature'] = df_vitals[['temp_bt', 'temp_esoph', 'temp_t1', 'temp_skin']].bfill(axis=1).iloc[:, 0]
            
            # Clean up temporary temp columns
            df_vitals = df_vitals.drop(columns=['temp_bt', 'temp_esoph', 'temp_t1', 'temp_skin'])
            
            # If temp is still missing, generate synthetic baseline
            if df_vitals['temperature'].isna().all():
                 df_vitals['temperature'] = np.random.normal(36.6, 0.2, len(df_vitals))
                 
            df_vitals['timestamp'] = np.arange(len(df_vitals)) * 30
            df_vitals = df_vitals.dropna(subset=['heart_rate', 'blood_oxygen']) 
            
            #  Baseline filters
            df_vitals = df_vitals[
                (df_vitals['heart_rate'] >= 45) & (df_vitals['heart_rate'] <= 110) &
                (df_vitals['blood_oxygen'] >= 95) & (df_vitals['blood_oxygen'] <= 100) &
                (df_vitals['temperature'] >= 35.0) & (df_vitals['temperature'] <= 37.5)
            ]
            
            if len(df_vitals) < 50: continue
            
            print(f"   Success: Case {case_id} had {len(df_vitals)} valid baseline rows. (Target: {target_status})")
            
            # Add anomalies
            df_injected, row_statuses = inject_anomaly(df_vitals, target_status)
            df_injected['status'] = row_statuses
            df_injected['patient_id'] = f"V{case_id}"
            
            
            cols = ['timestamp', 'patient_id', 'temperature', 'heart_rate', 'blood_oxygen', 'status']
            df_final = df_injected[cols]
            if len(df_final) > 500: 
                start = np.random.randint(0, len(df_final) - 500)
                df_final = df_final.iloc[start:start+500]
                
            all_data.append(df_final)
                
        except Exception as e:
            import traceback
            print(f"Failed to load case {case_id}: {type(e).__name__} - {e}")
            continue

    if not all_data:
        print("No valid data extracted.")
        return

    full_df = pd.concat(all_data, ignore_index=True)
    output_file = Config.CLASSIFICATION["SAMPLEPATH"]
    full_df.to_csv(output_file, index=False)
    
    print(f"\nSUCCESS. Saved {len(full_df)} samples to {output_file}")
    print("Status Distribution:")
    print(full_df['status'].value_counts(normalize=True))

if __name__ == "__main__":
    generate_vitaldb_dataset()
