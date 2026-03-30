import pandas as pd
import joblib
import os
import numpy as np
import xgboost as xgb

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix, ConfusionMatrixDisplay
from sklearn.utils.class_weight import compute_class_weight
import matplotlib.pyplot as plt

from config import Config


def train_health_model():
    print("Step 1: Loading data...")
    
    data_path = Config.CLASSIFICATION["SAMPLEPATH"]
    if not os.path.exists(data_path):
        print(f"Dataset not found at {data_path}")
        return

    df = pd.read_csv(data_path)
    df = df.sort_values(['patient_id', 'timestamp'])

    print(f"Loaded {len(df)} rows")

    # =========================================================
    # 🔥 STEP 2: FEATURE ENGINEERING
    # =========================================================
    print("Step 2: Feature engineering...")

    df['hr_diff'] = df.groupby('patient_id')['heart_rate'].diff().fillna(0)
    df['spo2_diff'] = df.groupby('patient_id')['blood_oxygen'].diff().fillna(0)
    df['temp_diff'] = df.groupby('patient_id')['temperature'].diff().fillna(0)

    feature_cols = [
        'temperature', 'heart_rate', 'blood_oxygen',
        'hr_diff', 'spo2_diff', 'temp_diff'
    ]

    # Add Rolling Windows (Temporal Patterns)
    windows = [5, 10] # 2.5 min and 5 min at 30s interval
    for w in windows:
        for col in ['temperature', 'heart_rate', 'blood_oxygen']:
            df[f'{col}_roll_mean_{w}'] = df.groupby('patient_id')[col].transform(lambda x: x.rolling(w, min_periods=1).mean())
            df[f'{col}_roll_std_{w}'] = df.groupby('patient_id')[col].transform(lambda x: x.rolling(w, min_periods=1).std().fillna(0))
            feature_cols.append(f'{col}_roll_mean_{w}')
            feature_cols.append(f'{col}_roll_std_{w}')

    df = df.dropna(subset=feature_cols + ['status'])

    # =========================================================
    # 🔥 STEP 3: LABEL ENCODING
    # =========================================================
    print("Step 3: Encoding labels...")

    label_encoder = LabelEncoder()
    df['label'] = label_encoder.fit_transform(df['status'])

    print("Label mapping:")
    for i, cls in enumerate(label_encoder.classes_):
        print(f"{cls} → {i}")

    # =========================================================
    # 🔥 STEP 4: SPLIT PER PATIENT (NO DATA LEAKAGE)
    # =========================================================
    print("Step 4: Patient-level split...")

    # Stratify patients by their final (most severe) status reached
    patient_statuses = df.groupby('patient_id')['status'].last()
    
    train_patients, test_patients = train_test_split(
        patient_statuses.index, 
        test_size=0.2, 
        random_state=42,
        stratify=patient_statuses.values
    )

    train_df = df[df['patient_id'].isin(train_patients)]
    test_df  = df[df['patient_id'].isin(test_patients)]

    X_train = train_df[feature_cols].values
    y_train = train_df['label'].values

    X_test = test_df[feature_cols].values
    y_test = test_df['label'].values

    print(f"Train samples: {len(X_train)}")
    print(f"Test samples: {len(X_test)}")
    
    unique_train, counts_train = np.unique(y_train, return_counts=True)
    unique_test, counts_test = np.unique(y_test, return_counts=True)
    print("Train distribution:", dict(zip(label_encoder.inverse_transform(unique_train), counts_train)))
    print("Test distribution:", dict(zip(label_encoder.inverse_transform(unique_test), counts_test)))

    # =========================================================
    # 🔥 STEP 5: CLASS WEIGHTS (NO DOWNSAMPLING)
    # =========================================================
    print("Step 5: Computing class weights...")

    classes = np.unique(y_train)
    weights = compute_class_weight(
        class_weight='balanced',
        classes=classes,
        y=y_train
    )

    class_weights = dict(zip(classes, weights))
    sample_weights = np.array([class_weights[y] for y in y_train])

    print("Class weights:", class_weights)

    # =========================================================
    # 🔥 STEP 6: MODEL
    # =========================================================
    print("Step 6: Training model...")

    model = xgb.XGBClassifier(
        n_estimators=500,
        learning_rate=0.05,
        max_depth=7,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric='mlogloss',
        random_state=42
    )

    model.fit(X_train, y_train, sample_weight=sample_weights)

    print("Model trained!")

    # =========================================================
    # 🔥 STEP 7: EVALUATION 
    # =========================================================
    print("Step 7: Evaluation...")

    y_pred = model.predict(X_test)

    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=label_encoder.classes_))

    # Confusion Matrix Visualization
    print("\nStep 7.1: Generating Confusion Matrix...")
    cm = confusion_matrix(y_test, y_pred)
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=label_encoder.classes_)
    
    fig, ax = plt.subplots(figsize=(10, 8))
    disp.plot(ax=ax, cmap='Blues', values_format='d')
    plt.title('Health State Classification Confusion Matrix')
    
    cm_path = os.path.join(os.path.dirname(Config.CLASSIFICATION["TRAINMODEL"]), "confusion_matrix.png")
    plt.savefig(cm_path)
    print(f"Confusion matrix saved at {cm_path}")

    # =========================================================
    # 🔥 STEP 8: SAVE MODEL
    # =========================================================
    print("Step 8: Saving model...")

    model_info = {
        'model': model,
        'feature_columns': feature_cols,
        'label_encoder': label_encoder,
        'accuracy': model.score(X_test, y_test)
    }

    joblib.dump(model_info, Config.CLASSIFICATION["TRAINMODEL"])

    print(f"Model saved at {Config.CLASSIFICATION['TRAINMODEL']}")

    return model


if __name__ == "__main__":
    train_health_model()