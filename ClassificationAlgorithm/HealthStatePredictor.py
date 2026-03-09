import pandas as pd
import joblib
import sys
import os
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

sys.path.append(str(Path(__file__).parent.parent))

try:
    from config import Config
except ImportError:
    from .config import Config

class HealthStatePredictor:
    def __init__(self, model_path):
        self.model_info = joblib.load(model_path)
        
        if isinstance(self.model_info, dict):
            self.model = self.model_info['model']
            self.feature_columns = self.model_info.get('feature_columns', ['temperature', 'heart_rate', 'blood_oxygen'])
            self.label_encoder = self.model_info.get('label_encoder', None)
            print(f"Model loaded from {model_path}")
            print(f"Training accuracy: {self.model_info.get('accuracy', 'N/A')}")
        else:
            self.model = self.model_info
            self.feature_columns = ['temperature', 'heart_rate', 'blood_oxygen']
            self.label_encoder = None
            print(f"Model loaded from {model_path}")

    def predict_state(self, temperature, heart_rate, blood_oxygen):
        input_data = pd.DataFrame([{
            'temperature': temperature,
            'heart_rate': heart_rate,
            'blood_oxygen': blood_oxygen
        }], columns=self.feature_columns)
        
        probabilities = self.model.predict_proba(input_data)[0]
        max_prob = np.max(probabilities)
        prediction_idx = np.argmax(probabilities)
        
        if self.label_encoder:
            prediction = self.label_encoder.inverse_transform([prediction_idx])[0]
        else:
            prediction = self.model.classes_[prediction_idx]
            
        # Confidence logic: override to 'risky' if max confidence < 50%
        if max_prob < 0.5:
            return 'risky'
            
        return prediction

    def predict_with_confidence(self, temperature, heart_rate, blood_oxygen):
        input_data = pd.DataFrame([{
            'temperature': temperature,
            'heart_rate': heart_rate,
            'blood_oxygen': blood_oxygen
        }], columns=self.feature_columns)
        
        probabilities = self.model.predict_proba(input_data)[0]
        max_prob = np.max(probabilities)
        prediction_idx = np.argmax(probabilities)
        
        # Decode classes to human-readable labels
        if self.label_encoder:
            classes = self.label_encoder.inverse_transform(self.model.classes_)
            prediction = self.label_encoder.inverse_transform([prediction_idx])[0]
        else:
            classes = self.model.classes_
            prediction = self.model.classes_[prediction_idx]
        
        # If max confidence < 50%, probably, it's risky
        if max_prob < 0.5:
            prediction = 'risky'
            
        confidence_scores = dict(zip(classes, probabilities))
        return prediction, confidence_scores

    def plot_confidence_bar(self, confidence_scores, title=None):
        classes = list(confidence_scores.keys())
        probs = [confidence_scores[c] for c in classes]

        fig, ax = plt.subplots(figsize=(6, 2.5))
        bars = ax.barh(classes, probs, color=['#4CAF50', '#FFC107', '#F44336'])
        ax.set_xlim(0, 1)
        ax.set_xlabel('Confidence')
        ax.set_title(title or 'Prediction Confidence')
        
        # Annotate bars with percentages
        for bar, prob in zip(bars, probs):
            ax.text(prob + 0.02, bar.get_y() + bar.get_height()/2,
                    f"{prob*100:.1f}%", va='center')

        plt.tight_layout()
        plt.show()


# Example usage
if __name__ == "__main__":

    model_path = Config.CLASSIFICATION["TRAINMODEL"]

    predictor = HealthStatePredictor(model_path)
        
    # Simulate a sequence: Fever Event (High Temp)
    # Healthy -> Risky -> Dangerous
    print("\n=== TESTING SEQUENCE PREDICTION (High Fever Event) ===")
    
    # Generate a sequence: Temp rising, HR rising, SpO2 rising
    # Temp 36.5 -> 39.5
    temps = np.linspace(36.5, 39.5, 15)
    # HR 70 -> 110 
    hrs = np.linspace(70, 110, 15)
    # SpO2 constant at 98%
    o2s = np.full(15, 98.0)
    
    for i, (t, h, o) in enumerate(zip(temps, hrs, o2s)):
        t, h, o = round(t, 1), round(h, 0), round(o, 1)
        
        pred, conf = predictor.predict_with_confidence(t, h, o)
        #predictor.plot_confidence_bar(conf, title="Health State Prediction Confidence")

        score = "N/A"
        if pred == 'dangerous': score = "CRITICAL"
        elif pred == 'risky': score = "WARNING"
        else: score = "NORMAL"
        
        print(f"Step {i+1:02d}: T={t} C, HR={h} bpm, O2={o}% -> {score} ({pred}) [{conf[pred]:.1%}]")

