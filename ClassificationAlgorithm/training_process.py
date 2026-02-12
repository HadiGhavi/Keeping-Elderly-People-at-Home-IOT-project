import pandas as pd
import joblib
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import os
from sklearn.preprocessing import LabelEncoder
import xgboost as xgb
import numpy as np

def create_window_features(df, features, window_size=6):
    """
    Create rolling window features for time-series data.
    Assumes df has 'patient_id' to group by.
    """
    df_rolled = df.copy()
    
    # Sort just in case
    df_rolled = df_rolled.sort_values(['patient_id', 'timestamp'])
    
    new_features = []
    
    for feature in features:
        # Rolling stats
        df_rolled[f'{feature}_mean'] = df_rolled.groupby('patient_id')[feature].transform(
            lambda x: x.rolling(window=window_size, min_periods=window_size).mean())
        df_rolled[f'{feature}_std'] = df_rolled.groupby('patient_id')[feature].transform(
            lambda x: x.rolling(window=window_size, min_periods=window_size).std())
        df_rolled[f'{feature}_min'] = df_rolled.groupby('patient_id')[feature].transform(
            lambda x: x.rolling(window=window_size, min_periods=window_size).min())
        df_rolled[f'{feature}_max'] = df_rolled.groupby('patient_id')[feature].transform(
            lambda x: x.rolling(window=window_size, min_periods=window_size).max())
        
        # Delta (Change from start of window to end)
        df_rolled[f'{feature}_change'] = df_rolled.groupby('patient_id')[feature].transform(
            lambda x: x.diff(window_size-1))
            
        new_features.extend([f'{feature}_mean', f'{feature}_std', f'{feature}_min', f'{feature}_max', f'{feature}_change'])
    
    # Add raw current values too
    new_features = features + new_features
    
    # Drop NaNs created by rolling
    df_rolled = df_rolled.dropna()
    
    return df_rolled, new_features

def train_health_model():
    """Train a health state prediction model using sequence data"""
    
    # Step 1: Load training data
    print("Step 1: Loading training data...")
    
    data_path = 'ClassificationAlgorithm/time_series_health_data.csv'
    if not os.path.exists(data_path):
        print("Dataset not found! Please run generate_time_series_data.py first.")
        return

    data = pd.read_csv(data_path)
    print(f"Data loaded: {len(data)} samples")
    
    # Step 2: Feature Engineering (Windowing)
    print("Step 2: Creating window features...")
    WINDOW_SIZE = 6 # e.g., 30 mins if 5 min intervals
    feature_cols = ['temperature', 'heart_rate', 'blood_oxygen']
    data_processed, feature_cols = create_window_features(data, feature_cols, window_size=WINDOW_SIZE)
    
    print(f"Processed data shape: {data_processed.shape}")
    
    # --- BALANCING STEP (80% Healthy, 15% Risky, 5% Dangerous) ---
    print("\nStep 3: Balancing Data (Target: 80% Healthy, 15% Risky, 5% Dangerous)...")
    
    df_h = data_processed[data_processed['status'] == 'healthy']
    df_r = data_processed[data_processed['status'] == 'risky']
    df_d = data_processed[data_processed['status'] == 'dangerous']
    
    print(f"Original Counts: H={len(df_h)}, R={len(df_r)}, D={len(df_d)}")
    
    # Calculate limits based on the scarcest resource relative to target %
    # Total based on Healthy: H / 0.8
    # Total based on Risky: R / 0.15
    # Total based on Dangerous: D / 0.05
    
    n_h_avail, n_r_avail, n_d_avail = len(df_h), len(df_r), len(df_d)
    
    if n_h_avail == 0 or n_r_avail == 0 or n_d_avail == 0:
         print("WARNING: One or more classes are empty. Skipping balancing.")
    else:
        max_total = min(n_h_avail/0.8, n_r_avail/0.15, n_d_avail/0.05)
        
        target_h = int(max_total * 0.8)
        target_r = int(max_total * 0.15)
        target_d = int(max_total * 0.05)
        
        print(f"Target Counts: H={target_h}, R={target_r}, D={target_d}")
        
        # Sample
        df_h = df_h.sample(target_h, replace=False, random_state=42)
        df_r = df_r.sample(target_r, replace=False, random_state=42)
        df_d = df_d.sample(target_d, replace=False, random_state=42)
        
        data_processed = pd.concat([df_h, df_r, df_d]).sample(frac=1, random_state=42).reset_index(drop=True)
        print(f"Balanced Data Shape: {data_processed.shape}")
        print("Distribution:\n", data_processed['status'].value_counts(normalize=True))

    print(f"Feature columns: {len(feature_cols)}")
    
    X = data_processed[feature_cols]
    y = data_processed['status']

    # Encode labels
    label_encoder = LabelEncoder()
    y_encoded = label_encoder.fit_transform(y)
    
    # Step 3: Split data
    # Note: For strict time series, we should split by patient_id, but customized random split 
    # is okay here as long as windows don't leak (we dropped NaNs).
    # Ideally split by patient ID to test generalization to new patients.
    patients = data_processed['patient_id'].unique()
    train_patients, test_patients = train_test_split(patients, test_size=0.2, random_state=42)
    
    train_mask = data_processed['patient_id'].isin(train_patients)
    X_train = X[train_mask]
    X_train.to_csv('X_train.csv', index=False)  # Save for inspection
    y_train = y_encoded[train_mask]
    
    test_mask = data_processed['patient_id'].isin(test_patients)
    X_test = X[test_mask]
    y_test = y_encoded[test_mask]
    
    print(f"Training set: {len(X_train)} samples")
    print(f"Test set: {len(X_test)} samples")
    
    # Step 4: Train model
    model = xgb.XGBClassifier(
        n_estimators=500,
        learning_rate=0.05,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric='mlogloss',
        random_state=42
    )

    model.fit(X_train, y_train)    
    print("Model trained successfully!")

    # Step 5: Evaluate model
    y_pred = model.predict(X_test)
    y_pred_labels = label_encoder.inverse_transform(y_pred)
    y_test_labels = label_encoder.inverse_transform(y_test)

    print(f"Accuracy: {accuracy_score(y_test_labels, y_pred_labels):.3f}")
    print("\nClassification Report:")
    print(classification_report(y_test_labels, y_pred_labels))

    # Step 6: Save model
    print("Step 6: Saving model...")
    
    model_info = {
        'model': model,
        'feature_columns': feature_cols,
        'original_features': ['temperature', 'heart_rate', 'blood_oxygen'],
        'window_size': WINDOW_SIZE,
        'label_encoder': label_encoder,
        'accuracy': accuracy_score(y_test_labels, y_pred_labels)
    }

    joblib.dump(model_info, 'trained_model.pkl')
    print("Model saved as 'trained_model.pkl'")
    
    return model

if __name__ == "__main__":
    train_health_model()