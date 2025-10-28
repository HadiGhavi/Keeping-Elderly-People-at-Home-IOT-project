import pandas as pd
import joblib
import sys
from pathlib import Path
import os
import matplotlib.pyplot as plt

sys.path.append(str(Path(__file__).parent.parent))

class HealthStatePredictor:
    def __init__(self, model_path):
        """Initialize the predictor with the trained model"""
        self.model_info = self._load_model(model_path)
        
        if isinstance(self.model_info, dict):
            self.model = self.model_info['model']
            self.feature_columns = self.model_info.get(
                'feature_columns', ['temperature', 'heart_rate', 'blood_oxygen']
            )
            self.label_encoder = self.model_info.get('label_encoder', None)
            print(f"Model loaded from {model_path}")
            print(f"Training accuracy: {self.model_info.get('accuracy', 'N/A')}")
        else:
            # Legacy format
            self.model = self.model_info
            self.feature_columns = ['temperature', 'heart_rate', 'blood_oxygen']
            self.label_encoder = None
            print(f"Model loaded from {model_path} (legacy format)")

    def _load_model(self, path):
        """Private method to load the model from disk"""
        return joblib.load(path)
    
    def predict_state(self, temperature, heart_rate, blood_oxygen):
        """Predict health state (decoded label)"""
        input_data = pd.DataFrame([[temperature, heart_rate, blood_oxygen]],
                                columns=self.feature_columns)
        
        prediction = self.model.predict(input_data)[0]
        if self.label_encoder:
            prediction = self.label_encoder.inverse_transform([prediction])[0]
        return prediction

    def predict_with_confidence(self, temperature, heart_rate, blood_oxygen):
        """Predict with confidence scores (decoded labels)"""
        input_data = pd.DataFrame([[temperature, heart_rate, blood_oxygen]],
                                columns=self.feature_columns)
        
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
    
    # Test with your real data examples
    real_world_cases = [
        {'name': 'Kevin - Case 1', 'temp': 38.6, 'hr': 105, 'o2': 97.2},
        {'name': 'Kevin - Case 2', 'temp': 36.9, 'hr': 100, 'o2': 97.3},
        {'name': 'Barbara - Case 1', 'temp': 36.6, 'hr': 100, 'o2': 96.9},
        {'name': 'NO Healthy elderly', 'temp': 36.8, 'hr': 72, 'o2': 90.0},
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
        predictor.plot_confidence_bar(confidence, title=f"{case['name']} ({prediction})")
