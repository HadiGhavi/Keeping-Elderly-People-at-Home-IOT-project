from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import classification_report, confusion_matrix
from imblearn.over_sampling import SMOTE
import joblib
import pandas as pd
import os


# Path to the dataset
script_dir = os.path.dirname(os.path.abspath(__file__))
data_path = os.path.join(script_dir, "realistic_elderly_health_data.csv")

# Load the dataset
data = pd.read_csv(data_path)


# Split the data into features and labels
X = data[['temperature', 'heart_rate', 'blood_oxygen']]
y = data['label']

# Check class distribution
class_distribution = y.value_counts()
print("Class distribution before SMOTE:")
print(class_distribution)

# If any class has only one sample, remove SMOTE
if any(class_distribution <= 1):
    print("Some classes have only one sample. Skipping SMOTE.")
    X_resampled, y_resampled = X, y
else:
    # Balance the dataset using SMOTE
    smote = SMOTE(random_state=42)
    X_resampled, y_resampled = smote.fit_resample(X, y)

# Split the resampled data into training and testing sets
X_train, X_test, y_train, y_test = train_test_split(X_resampled, y_resampled, test_size=0.3, random_state=42)

# Train the model using Decision Tree
model = DecisionTreeClassifier(random_state=42)
model.fit(X_train, y_train)

# Evaluate the model
y_pred = model.predict(X_test)
print("Confusion Matrix:\n", confusion_matrix(y_test, y_pred))
print("\nClassification Report:\n", classification_report(y_test, y_pred))

# Save the trained model to disk
model_path = 'trained_model.pkl'
joblib.dump(model, model_path)
print(f"Model saved to {model_path}")
