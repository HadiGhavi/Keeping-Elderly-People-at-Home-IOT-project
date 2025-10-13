import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import os

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
    print(data['label'].value_counts())
    print()
    
    # Step 2: Prepare features and target
    print("Step 2: Preparing features...")
    X = data[['temperature', 'heart_rate', 'blood_oxygen']]
    y = data['label']
    
    # Step 3: Split data
    print("Step 3: Splitting data...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    
    print(f"Training set: {len(X_train)} samples")
    print(f"Test set: {len(X_test)} samples")
    print()
    
    # Step 4: Train model
    print("Step 4: Training model...")
    model = RandomForestClassifier(
        n_estimators=100,
        random_state=42,
        class_weight='balanced'  # Handle any remaining imbalance
    )
    
    model.fit(X_train, y_train)
    print("Model trained successfully!")
    print()
    
    # Step 5: Evaluate model
    print("Step 5: Evaluating model...")
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    
    print(f"Accuracy: {accuracy:.3f}")
    print("\nDetailed Classification Report:")
    print(classification_report(y_test, y_pred))
    
    # Step 6: Save model
    print("Step 6: Saving model...")
    model_info = {
        'model': model,
        'feature_columns': ['temperature', 'heart_rate', 'blood_oxygen'],
        'accuracy': accuracy,
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
        [39.8, 110, 89]   # Should be dangerous
    ]
    
    for i, case in enumerate(test_cases):
        pred = model.predict([case])[0]
        print(f"Case {i+1}: Temp {case[0]}°C, HR {case[1]}, O2 {case[2]}% → {pred}")
    
    return model

if __name__ == "__main__":
    train_health_model()