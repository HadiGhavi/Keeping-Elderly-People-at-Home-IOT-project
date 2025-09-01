import pandas as pd
import joblib
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from config import Config

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
    model_path =  Config.CLASSIFICATION["TRAINMODEL"]
    predictor = HealthStatePredictor(model_path)
    
    # Make prediction
    # example_temperature = 36.5
    # example_heart_rate = 75
    # example_blood_oxygen = 97
    
    # predicted_state = predictor.predict_state(
    #     example_temperature, 
    #     example_heart_rate, 
    #     example_blood_oxygen
    # )
    # print(f"Predicted State: {predicted_state}")