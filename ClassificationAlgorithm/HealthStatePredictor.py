import pandas as pd
import joblib
import sys
from pathlib import Path
import os
sys.path.append(str(Path(__file__).parent.parent))

class HealthStatePredictor:
    def __init__(self, model_path):
        """Initialize the predictor with the trained model"""
        self.model_info = self._load_model(model_path)
        # Handle both old and new model formats
        if isinstance(self.model_info, dict):
            self.model = self.model_info['model']
            self.feature_columns = self.model_info.get('feature_columns', 
                                                     ['temperature', 'heart_rate', 'blood_oxygen'])
            print(f"Model loaded from {model_path}")
            print(f"Training accuracy: {self.model_info.get('accuracy', 'N/A')}")
        else:
            # Old format - just the model
            self.model = self.model_info
            self.feature_columns = ['temperature', 'heart_rate', 'blood_oxygen']
            print(f"Model loaded from {model_path} (legacy format)")
    
    def _load_model(self, path):
        """Private method to load the model from disk"""
        return joblib.load(path)
    
    def predict_state(self, temperature, heart_rate, blood_oxygen):
        """Predict health state based on input parameters"""
        input_data = pd.DataFrame(
            [[temperature, heart_rate, blood_oxygen]], 
            columns=self.feature_columns  # Use proper column names
        )
        return self.model.predict(input_data)[0]
    
    def predict_with_confidence(self, temperature, heart_rate, blood_oxygen):
        """Predict with confidence scores"""
        input_data = pd.DataFrame(
            [[temperature, heart_rate, blood_oxygen]], 
            columns=self.feature_columns
        )
        prediction = self.model.predict(input_data)[0]
        probabilities = self.model.predict_proba(input_data)[0]
        
        # Get class names and probabilities
        classes = self.model.classes_
        confidence_scores = dict(zip(classes, probabilities))
        
        return prediction, confidence_scores


# Example usage
if __name__ == "__main__":
    # Initialize predictor
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, "trained_model.pkl")

    predictor = HealthStatePredictor(model_path)
    
    # Test with your real data examples
    real_world_cases = [
        {'name': 'Kevin - Case 1', 'temp': 36.6, 'hr': 105, 'o2': 97.2},
        {'name': 'Kevin - Case 2', 'temp': 36.9, 'hr': 100, 'o2': 97.3},
        {'name': 'Barbara - Case 1', 'temp': 36.6, 'hr': 100, 'o2': 96.9},
        {'name': 'Healthy elderly', 'temp': 36.8, 'hr': 72, 'o2': 97.0},
    ]
    
    print("\n=== TESTING WITH REAL DATA ===")
    for case in real_world_cases:
        prediction = predictor.predict_state(case['temp'], case['hr'], case['o2'])
        pred_conf, confidence = predictor.predict_with_confidence(case['temp'], case['hr'], case['o2'])
        
        print(f"\n{case['name']}:")
        print(f"  Vitals: {case['temp']}°C, {case['hr']} bpm, {case['o2']}%")
        print(f"  Prediction: {prediction}")
        print(f"  Confidence: {confidence[prediction]:.2%}")
        
        # Show if this makes medical sense
        if case['temp'] < 37.5 and 60 <= case['hr'] <= 100 and case['o2'] >= 95:
            expected = "healthy"
        else:
            expected = "risky or dangerous"
        
        print(f"  Medical expectation: {expected}")
        print(f"  Match: {'✓' if prediction == 'healthy' and expected == 'healthy' else '✗'}")