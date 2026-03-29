import sys
import os
from pathlib import Path
from collections import deque

import pandas as pd
import joblib
import numpy as np
import matplotlib.pyplot as plt

sys.path.append(str(Path(__file__).parent.parent))

try:
    from config import Config
except ImportError:
    from .config import Config

class HealthStatePredictor:
    MAX_WINDOW = 10
    
    def __init__(self, model_path=None):
        model_path = model_path or Config.CLASSIFICATION["TRAINMODEL"]
        self.model_info = joblib.load(model_path)
        
        # Initialize buffers for each base feature
        self.buffers = {
            'temperature': deque(maxlen=self.MAX_WINDOW),
            'heart_rate': deque(maxlen=self.MAX_WINDOW),
            'blood_oxygen': deque(maxlen=self.MAX_WINDOW)
        }
        
        if isinstance(self.model_info, dict):
            self.model = self.model_info['model']
            self.feature_columns = self.model_info.get('feature_columns', ['temperature', 'heart_rate', 'blood_oxygen'])
            self.label_encoder = self.model_info.get('label_encoder', None)
            
            acc = self.model_info.get('accuracy', 'N/A')
            acc_str = f"{acc:.2%}" if isinstance(acc, (float, int)) else str(acc)
            
            #print(f"Model loaded from {model_path}")
            #print(f"Training accuracy: {acc_str}")
        else:
            self.model = self.model_info
            self.feature_columns = ['temperature', 'heart_rate', 'blood_oxygen']
            self.label_encoder = None
            #print(f"Model loaded from {model_path}")

    def _get_features(self, temperature, heart_rate, blood_oxygen):
        # Update buffers
        self.buffers['temperature'].append(temperature)
        self.buffers['heart_rate'].append(heart_rate)
        self.buffers['blood_oxygen'].append(blood_oxygen)
        
        # Base features
        features = {
            'temperature': temperature,
            'heart_rate': heart_rate,
            'blood_oxygen': blood_oxygen
        }
        
        # Diffs (compared to previous reading)
        if len(self.buffers['temperature']) > 1:
            features['temp_diff'] = self.buffers['temperature'][-1] - self.buffers['temperature'][-2]
            features['hr_diff'] = self.buffers['heart_rate'][-1] - self.buffers['heart_rate'][-2]
            features['spo2_diff'] = self.buffers['blood_oxygen'][-1] - self.buffers['blood_oxygen'][-2]
        else:
            features['temp_diff'] = 0.0
            features['hr_diff'] = 0.0
            features['spo2_diff'] = 0.0
            
        # Rolling features
        windows = [5, 10]
        for w in windows:
            for col in ['temperature', 'heart_rate', 'blood_oxygen']:
                data = list(self.buffers[col])[-w:]
                features[f'{col}_roll_mean_{w}'] = np.mean(data)
                features[f'{col}_roll_std_{w}'] = np.std(data) if len(data) > 1 else 0.0
                
        return pd.DataFrame([features], columns=self.feature_columns)

    def predict_state(self, temperature, heart_rate, blood_oxygen):
        input_data = self._get_features(temperature, heart_rate, blood_oxygen)
        
        probabilities = self.model.predict_proba(input_data)[0]
        max_prob = np.max(probabilities)
        prediction_idx = np.argmax(probabilities)
        
        if self.label_encoder:
            prediction = self.label_encoder.inverse_transform([prediction_idx])[0]
        else:
            prediction = self.model.classes_[prediction_idx]
            
        # Override to 'risky' if max confidence < 50%
        if max_prob < 0.5:
            return 'risky'
            
        return prediction

    def predict_with_confidence(self, temperature, heart_rate, blood_oxygen):
        input_data = self._get_features(temperature, heart_rate, blood_oxygen)
        
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
        
        # If max confidence < 40%, we are unsure, label as 'risky' for safety
        if max_prob < 0.4:
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
    
    # Generate a sequence: Temp rising, HR rising, SpO2 constant
    # Temp 36.5 -> 40.0 (more points for realistic trend)
    steps = 60
    temps = np.linspace(36.5, 40.0, steps)
    # HR 70 -> 115
    hrs = np.linspace(70, 115, steps)
    # SpO2 constant at 98%
    o2s = np.full(steps, 98.0)
    
    for i, (t, h, o) in enumerate(zip(temps, hrs, o2s)):
        t, h, o = round(t, 1), round(h, 0), round(o, 1)
        
        pred, conf = predictor.predict_with_confidence(t, h, o)
        
        score = "NORMAL"
        if pred == 'dangerous': score = "CRITICAL"
        elif pred == 'risky': score = "WARNING"
        
        print(f"Step {i+1:02d}: T={t} C, HR={h} bpm, O2={o}% -> {score} ({pred}) [{conf[pred]:.1%}]")

