import pandas as pd
import joblib
import sys
from pathlib import Path
import os
sys.path.append(str(Path(__file__).parent.parent))

class HealthStatePredictor:
    def __init__(self, model_path):
        """Initialize the predictor with the trained model"""
        self.model = self._load_model(model_path)
        print(f"Model loaded from {model_path}")
    
    def _load_model(self, path):
        """Private method to load the model from disk"""
        return joblib.load(path)
    
    def predict_state(self, temperature, heart_rate, blood_oxygen):
        """Predict health state based on input parameters"""
        input_data = pd.DataFrame(
            [[temperature, heart_rate, blood_oxygen]], 
            columns=['temperature', 'heart_rate', 'blood_oxygen']
        )
        return self.model.predict(input_data)[0]


# Example usage
if __name__ == "__main__":
    # Initialize predictor
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, "trained_model.pkl")

    predictor = HealthStatePredictor(model_path)
    
    """  # Make prediction
    example_temperature = 38.5
    example_heart_rate = 100
    example_blood_oxygen = 97
    
    predicted_state = predictor.predict_state(
        example_temperature, 
        example_heart_rate, 
        example_blood_oxygen
    )
    print(f"Predicted State: {predicted_state}")  """