import pandas as pd
import numpy as np

# Function to generate synthetic data ensuring each class has at least 5% of the data
def generate_synthetic_data(num_samples=1000):
    np.random.seed(42)

    # Generate random data for temperature, heart rate, and blood oxygen
    temperature = np.random.normal(loc=37, scale=1, size=num_samples)
    heart_rate = np.random.normal(loc=70, scale=10, size=num_samples)
    blood_oxygen = np.random.normal(loc=98, scale=1, size=num_samples)


    temperature = np.clip(temperature, 34.0, 42.0)
    heart_rate = np.clip(heart_rate, 40.0, 150.0)
    blood_oxygen = np.clip(blood_oxygen, 60.0, 100.0)

    # Ensure at least 5% of the data belongs to each class
    min_samples_per_class = int(num_samples * 0.05)
    remaining_samples = num_samples - 3 * min_samples_per_class

    labels = ['normal'] * min_samples_per_class + \
             ['risky'] * min_samples_per_class + \
             ['dangerous'] * min_samples_per_class + \
             np.random.choice(['normal', 'risky', 'dangerous'], remaining_samples).tolist()

    # Shuffle the data to mix the labels
    np.random.shuffle(labels)

    # Create a DataFrame
    data = pd.DataFrame({
        'temperature': temperature,
        'heart_rate': heart_rate,
        'blood_oxygen': blood_oxygen,
        'label': labels
    })

    return data

# Generate the synthetic dataset
synthetic_data = generate_synthetic_data()

# Save the dataset to a CSV file
file_path = 'synthetic_elderly_health_data.csv'  # Replace with the desired path
synthetic_data.to_csv(file_path, index=False)
print(f"Dataset saved to {file_path}")
