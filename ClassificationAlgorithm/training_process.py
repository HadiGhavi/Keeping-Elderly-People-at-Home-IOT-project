import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import os
from sklearn.preprocessing import LabelEncoder
import xgboost as xgb



def train_health_model():
    """Train a health state prediction model"""
    
    # Step 1: Generate or load training data
    print("Step 1: Loading training data...")
    
    # First, check if we have the CSV data
    if os.path.exists('realistic_elderly_health_data.csv'):
        print("Loading existing data...")
        data = pd.read_csv('realistic_elderly_health_data.csv')
    else:
        print("No data file found. Run data_gen.py first!")
        print("Running: python data_gen.py")
        os.system('python data_gen.py')
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_path = os.path.join(script_dir, "realistic_elderly_health_data.csv")

        # Load the dataset
        data = pd.read_csv(data_path)
    print(f"Data loaded: {len(data)} samples")
    print("Label distribution:")
    print(data['status'].value_counts())
    print()
    
    
    # Step 2: Prepare features and target
    print("Step 2: Preparing features...")
    X = data[['temperature', 'heart_rate', 'blood_oxygen']]
    y = data['status']

    # Encode labels to numeric 
    label_encoder = LabelEncoder()
    y_encoded = label_encoder.fit_transform(y)
    print(dict(zip(label_encoder.classes_, label_encoder.transform(label_encoder.classes_))))
    
    # Step 3: Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_encoded, test_size=0.2, random_state=42, stratify=y_encoded
    )
    
    print(f"Training set: {len(X_train)} samples")
    print(f"Test set: {len(X_test)} samples")
    print()
    
    # Step 4: Train model
    model = xgb.XGBClassifier(
        n_estimators=400,
        learning_rate=0.01,
        max_depth=4,
        subsample=1.0,
        min_child_weight=1,
        gamma=0.1,
        colsample_bytree=0.9,
        eval_metric='mlogloss',
        random_state=42
    )

    model.fit(X_train, y_train)    

    print("Model trained successfully!")
    print()

    #Step 5: Evaluate model
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
        'feature_columns': ['temperature', 'heart_rate', 'blood_oxygen'],
        'label_encoder': label_encoder,
        'accuracy': accuracy_score,
        'training_samples': len(X_train)
    }

    joblib.dump(model_info, 'trained_model.pkl')
    print("Model saved as 'trained_model.pkl'")
    print()
    
    # Step 7: Test with sample data
    print("Step 7: Testing with sample predictions...")
    test_cases = [
        [36.8, 72, 97],   # Should be healthy
        [38.5, 95, 94],   # Should be risky  
        [40, 110, 87]   # Should be dangerous
    ]
    
    for i, case in enumerate(test_cases):
        pred = model.predict([case])[0]
        print(f"Case {i+1}: Temp {case[0]}°C, HR {case[1]}, O2 {case[2]}% → {pred}")
    
    return model

if __name__ == "__main__":
    train_health_model()