import pandas as pd
import joblib
import sys
from pathlib import Path
import os
import matplotlib.pyplot as plt
import numpy as np
from collections import deque

sys.path.append(str(Path(__file__).parent.parent))

class HealthStatePredictor:
    def __init__(self, model_path):
        """Initialize the predictor with the trained model"""
        self.model_info = self._load_model(model_path)
        
        if isinstance(self.model_info, dict):
            self.model = self.model_info['model']
            self.feature_columns = self.model_info.get('feature_columns', [])
            self.label_encoder = self.model_info.get('label_encoder', None)
            
            # Load window size, default to 1 if not present (backward compatibility)
            self.window_size = self.model_info.get('window_size', 1)
            
            # Initialize history buffer
            self.history = deque(maxlen=self.window_size)
            
            print(f"Model loaded from {model_path}")
            print(f"Window size: {self.window_size}")
            print(f"Training accuracy: {self.model_info.get('accuracy', 'N/A')}")
        else:
            # Legacy format support
            self.model = self.model_info
            self.feature_columns = ['temperature', 'heart_rate', 'blood_oxygen']
            self.label_encoder = None
            self.window_size = 1
            self.history = deque(maxlen=1)
            print(f"Model loaded from {model_path} (legacy format)")

    def _load_model(self, path):
        """Private method to load the model from disk"""
        return joblib.load(path)
    
    def _extract_features(self, temp, hr, o2):
        """
        Compute rolling features from history buffer.
        """
        # Add current measurement to history
        self.history.append({'temperature': temp, 'heart_rate': hr, 'blood_oxygen': o2})
        
        # If history is not full, fill it by duplicating the last measurement
        # This prevents cold-start issues, though predictions might be less accurate initially
        current_history = list(self.history)
        while len(current_history) < self.window_size:
            current_history.insert(0, current_history[0]) # Pad with oldest available
            
        df = pd.DataFrame(current_history)
        
        # If window_size is 1, return raw features
        if self.window_size == 1:
            return df[['temperature', 'heart_rate', 'blood_oxygen']]

        # Compute features
        features = {}
        original_cols = ['temperature', 'heart_rate', 'blood_oxygen']
        
        # Raw current values
        for col in original_cols:
            features[col] = df.iloc[-1][col]
            
        # Rolling stats
        for col in original_cols:
            features[f'{col}_mean'] = df[col].mean()
            features[f'{col}_std'] = df[col].std(ddof=1) if len(df) > 1 else 0.0
            features[f'{col}_min'] = df[col].min()
            features[f'{col}_max'] = df[col].max()
            features[f'{col}_change'] = df.iloc[-1][col] - df.iloc[0][col]
            
        # Create single-row DataFrame with correct column order
        return pd.DataFrame([features], columns=self.feature_columns)

    def predict_state(self, temperature, heart_rate, blood_oxygen):
        """Predict health state (decoded label) based on history + current"""
        input_data = self._extract_features(temperature, heart_rate, blood_oxygen)
        
        prediction = self.model.predict(input_data)[0]
        if self.label_encoder:
            prediction = self.label_encoder.inverse_transform([prediction])[0]
        return prediction

    def predict_with_confidence(self, temperature, heart_rate, blood_oxygen):
        """Predict with confidence scores (decoded labels)"""
        input_data = self._extract_features(temperature, heart_rate, blood_oxygen)
        
        prediction = self.model.predict(input_data)[0]
        probabilities = self.model.predict_proba(input_data)[0]
        
        # Decode classes to human-readable labels
        if self.label_encoder:
            classes = self.label_encoder.inverse_transform(self.model.classes_)
            prediction = self.label_encoder.inverse_transform([prediction])[0]
        else:
            classes = self.model.classes_
        
        confidence_scores = dict(zip(classes, probabilities))
        return prediction, confidence_scores

    def reset_history(self):
        """Clear the history buffer (useful when switching patients)"""
        self.history.clear()

    def plot_confidence_bar(self, confidence_scores, title=None):
        """Visualize prediction confidence as a horizontal bar chart."""
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
    # Initialize predictor
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_path = os.path.join(script_dir, "trained_model.pkl")

    predictor = HealthStatePredictor(model_path)
    
    print(f"\nModel Window Size: {predictor.window_size}")
    
    # Simulate a sequence: Fever Event (High Temp)
    # Healthy -> Risky -> Dangerous
    print("\n=== TESTING SEQUENCE PREDICTION (High Fever Event) ===")
    
    # Generate a sequence: Temp rising, HR rising, SpO2 rising
    # Temp 36.5 -> 39.5
    temps = np.linspace(36.5, 39.5, 12)
    # HR 70 -> 110 
    hrs = np.linspace(70, 110, 12)
    # SpO2 85 -> 98
    o2s = np.linspace(85, 98, 12)
    
    predictor.reset_history()
    
    for i, (t, h, o) in enumerate(zip(temps, hrs, o2s)):
        t, h, o = round(t, 1), round(h, 0), round(o, 1)
        
        pred, conf = predictor.predict_with_confidence(t, h, o)
        
        score = "N/A"
        if pred == 'dangerous': score = "CRITICAL"
        elif pred == 'risky': score = "WARNING"
        else: score = "NORMAL"
        
        print(f"Step {i+1:02d}: T={t} C, HR={h} bpm, O2={o}% -> {score} ({pred}) [{conf[pred]:.1%}]")
