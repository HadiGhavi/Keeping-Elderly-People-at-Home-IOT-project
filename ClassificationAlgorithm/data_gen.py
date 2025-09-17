import pandas as pd
import numpy as np

def generate_realistic_health_data(num_samples=10000):
    """
    Generate synthetic elderly health data with medically meaningful labels
    """
    np.random.seed(42)
    
    # Initialize arrays
    temperature = []
    heart_rate = []
    blood_oxygen = []
    labels = []
    
    # Target distribution: 60% normal, 25% risky, 15% dangerous
    normal_count = int(num_samples * 0.60)
    risky_count = int(num_samples * 0.25)
    dangerous_count = num_samples - normal_count - risky_count
    
    # Generate NORMAL cases (healthy elderly)
    for _ in range(normal_count):
        temp = np.random.normal(36.8, 0.3)  # Normal temp range
        hr = np.random.normal(72, 8)        # Normal heart rate  
        o2 = np.random.normal(97, 1.5)      # Good oxygen levels
        
        temperature.append(np.clip(temp, 36.0, 37.5))
        heart_rate.append(np.clip(hr, 60, 90))
        blood_oxygen.append(np.clip(o2, 95, 100))
        labels.append('normal')
    
    # Generate RISKY cases (concerning but not critical)
    for _ in range(risky_count):
        case_type = np.random.choice(['mild_fever', 'low_oxygen', 'irregular_hr', 'multiple_mild'])
        
        if case_type == 'mild_fever':
            temp = np.random.normal(38.2, 0.4)  # Mild fever
            hr = np.random.normal(78, 10)
            o2 = np.random.normal(96, 2)
        elif case_type == 'low_oxygen':
            temp = np.random.normal(37.0, 0.5)
            hr = np.random.normal(75, 12)
            o2 = np.random.normal(93, 1.5)      # Borderline oxygen
        elif case_type == 'irregular_hr':
            temp = np.random.normal(37.2, 0.4)
            hr = np.random.choice([
                np.random.normal(55, 5),        # Bradycardia
                np.random.normal(95, 8)         # Mild tachycardia
            ])
            o2 = np.random.normal(96, 2)
        else:  # multiple_mild
            temp = np.random.normal(37.8, 0.3)  # Slightly high
            hr = np.random.normal(88, 8)        # Slightly high
            o2 = np.random.normal(94, 1.5)      # Slightly low
        
        temperature.append(np.clip(temp, 35.5, 39.0))
        heart_rate.append(np.clip(hr, 45, 105))
        blood_oxygen.append(np.clip(o2, 88, 100))
        labels.append('risky')
    
    # Generate DANGEROUS cases (critical conditions)
    for _ in range(dangerous_count):
        case_type = np.random.choice(['high_fever', 'severe_hypoxia', 'cardiac_event', 'hypothermia', 'multiple_severe'])
        
        if case_type == 'high_fever':
            temp = np.random.normal(39.5, 0.8)  # High fever
            hr = np.random.normal(95, 15)       # Elevated HR due to fever
            o2 = np.random.normal(94, 3)
        elif case_type == 'severe_hypoxia':
            temp = np.random.normal(37.2, 0.6)
            hr = np.random.normal(85, 12)
            o2 = np.random.normal(88, 3)        # Severe hypoxemia
        elif case_type == 'cardiac_event':
            temp = np.random.normal(37.5, 0.5)
            hr = np.random.choice([
                np.random.normal(45, 8),        # Severe bradycardia
                np.random.normal(115, 15)       # Tachycardia
            ])
            o2 = np.random.normal(92, 4)
        elif case_type == 'hypothermia':
            temp = np.random.normal(34.8, 1.0)  # Hypothermia
            hr = np.random.normal(58, 12)       # Slow HR
            o2 = np.random.normal(91, 3)
        else:  # multiple_severe
            temp = np.random.normal(39.2, 0.6)  # High fever
            hr = np.random.normal(108, 12)      # High HR
            o2 = np.random.normal(89, 2)        # Low oxygen
        
        temperature.append(np.clip(temp, 33.0, 42.0))
        heart_rate.append(np.clip(hr, 35, 130))
        blood_oxygen.append(np.clip(o2, 80, 100))
        labels.append('dangerous')
    
    # Create DataFrame
    data = pd.DataFrame({
        'temperature': temperature,
        'heart_rate': heart_rate,
        'blood_oxygen': blood_oxygen,
        'label': labels
    })
    
    # Shuffle the data
    data = data.sample(frac=1, random_state=42).reset_index(drop=True)
    
    return data

def validate_health_logic(row):
    """
    Validate if a data point makes medical sense
    """
    temp, hr, o2, label = row['temperature'], row['heart_rate'], row['blood_oxygen'], row['label']
    
    # Count concerning factors
    danger_score = 0
    
    # Temperature factors
    if temp >= 39.5 or temp <= 35.0:
        danger_score += 3
    elif temp >= 38.0 or temp <= 36.0:
        danger_score += 1
    
    # Heart rate factors
    if hr >= 110 or hr <= 50:
        danger_score += 2
    elif hr >= 95 or hr <= 60:
        danger_score += 1
    
    # Oxygen factors
    if o2 <= 88:
        danger_score += 3
    elif o2 <= 93:
        danger_score += 2
    elif o2 <= 95:
        danger_score += 1
    
    # Predict expected label
    if danger_score >= 4:
        expected = 'dangerous'
    elif danger_score >= 2:
        expected = 'risky'
    else:
        expected = 'normal'
    
    return expected == label

# Generate the improved dataset
print("Generating medically realistic elderly health data...")
improved_data = generate_realistic_health_data(1000)

# Validate the data
validation_results = improved_data.apply(validate_health_logic, axis=1)
accuracy = validation_results.mean()

print(f"\nDataset Summary:")
print(f"Total samples: {len(improved_data)}")
print(f"Label distribution:")
print(improved_data['label'].value_counts())

print(f"\nVital Signs Ranges:")
print(f"Temperature: {improved_data['temperature'].min():.1f} - {improved_data['temperature'].max():.1f}°C")
print(f"Heart Rate: {improved_data['heart_rate'].min():.1f} - {improved_data['heart_rate'].max():.1f} bpm")
print(f"Blood Oxygen: {improved_data['blood_oxygen'].min():.1f} - {improved_data['blood_oxygen'].max():.1f}%")

print(f"\nMedical Logic Consistency: {accuracy:.1%}")

# Save the dataset
improved_data.to_csv('realistic_elderly_health_data.csv', index=False)
print(f"\nDataset saved to 'realistic_elderly_health_data.csv'")

# Show examples from each class
print(f"\nSample cases:")
for label in ['normal', 'risky', 'dangerous']:
    sample = improved_data[improved_data['label'] == label].iloc[0]
    print(f"{label.upper()}: Temp {sample['temperature']:.1f}°C, HR {sample['heart_rate']:.1f} bpm, O2 {sample['blood_oxygen']:.1f}%")