import pandas as pd
import joblib
import os
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from sklearn.preprocessing import LabelEncoder
import xgboost as xgb
import numpy as np
from config import Config

def train_health_model():
    print("Step 1: Loading training data...")
    
    data_path = Config.CLASSIFICATION["SAMPLEPATH"]
    if not os.path.exists(data_path):
        print(f"Dataset not found at {data_path}!")
        return

    data = pd.read_csv(data_path)
    print(f"Data loaded: {len(data)} samples")
    
    print("Step 2: Preparing features...")
    feature_cols = ['temperature', 'heart_rate', 'blood_oxygen']
    data_processed = data.dropna(subset=feature_cols)
    X = data_processed[feature_cols]
    y = data_processed['status']
    
    # (Target: 80% Healthy, 15% Risky, 5% Dangerous)
    print("\nStep 3: Balancing Data...")
    df_h = data_processed[data_processed['status'] == 'healthy']
    df_r = data_processed[data_processed['status'] == 'risky']
    df_d = data_processed[data_processed['status'] == 'dangerous']
    
    n_h, n_r, n_d = len(df_h), len(df_r), len(df_d)
    if n_h > 0 and n_r > 0 and n_d > 0:
        max_total = min(n_h/0.8, n_r/0.15, n_d/0.05)
        target_h, target_r, target_d = int(max_total * 0.8), int(max_total * 0.15), int(max_total * 0.05)
        
        df_h = df_h.sample(target_h, replace=False, random_state=42)
        df_r = df_r.sample(target_r, replace=False, random_state=42)
        df_d = df_d.sample(target_d, replace=False, random_state=42)
        
        data_balanced = pd.concat([df_h, df_r, df_d]).sample(frac=1, random_state=42).reset_index(drop=True)
        X = data_balanced[feature_cols]
        y = data_balanced['status']
        print(f"Balanced Data Shape: {data_balanced.shape}")

    label_encoder = LabelEncoder()
    y_encoded = label_encoder.fit_transform(y)
    
    # Step 4: Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_encoded, test_size=0.2, stratify=y_encoded, random_state=42
    )
    
    # Step 5: Train model
    model = xgb.XGBClassifier(
        n_estimators=400,
        learning_rate=0.01,
        max_depth=4,
        eval_metric='mlogloss',
        random_state=42
    )

    model.fit(X_train, y_train)  
    print("Model trained successfully!")

    # Step 6: Evaluate and save model
    y_pred = model.predict(X_test)
    print(f"Accuracy: {accuracy_score(y_test, y_pred):.3f}")
    
    model_info = {
        'model': model,
        'feature_columns': feature_cols,
        'original_features': feature_cols,
        'label_encoder': label_encoder,
        'accuracy': accuracy_score(y_test, y_pred)
    }

    joblib.dump(model_info, Config.CLASSIFICATION["TRAINMODEL"])
    print(f"Model saved as '{Config.CLASSIFICATION['TRAINMODEL']}'")
    
    return model

if __name__ == "__main__":
    train_health_model()