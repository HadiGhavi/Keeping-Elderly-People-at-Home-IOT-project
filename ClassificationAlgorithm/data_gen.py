import pandas as pd
import numpy as np

def generate_realistic_health_data(num_samples=10000):
    np.random.seed(42)
    temperature, heart_rate, blood_oxygen, labels = [], [], [], []

    normal_count = int(num_samples * 0.85)
    risky_count = int(num_samples * 0.12)
    dangerous_count = num_samples - normal_count - risky_count

    for _ in range(normal_count):
        temp = np.random.normal(36.8, 0.3)
        hr = np.random.normal(78, 12)
        o2 = np.random.normal(97, 1.5)
        temperature.append(np.clip(temp, 36.0, 37.4))
        heart_rate.append(np.clip(hr, 55, 105))
        blood_oxygen.append(np.clip(o2, 95, 100))
        labels.append('healthy')

    for _ in range(risky_count):
        case_type = np.random.choice(['mild_fever', 'low_oxygen', 'irregular_hr', 'multiple_mild'])
        if case_type == 'mild_fever':
            temp, hr, o2 = np.random.normal(38.5, 0.4), np.random.normal(85, 10), np.random.normal(96, 2)
        elif case_type == 'low_oxygen':
            temp, hr, o2 = np.random.normal(37.0, 0.5), np.random.normal(80, 12), np.random.normal(93, 1.5)
        elif case_type == 'irregular_hr':
            temp, hr, o2 = np.random.normal(37.2, 0.4), np.random.choice([np.random.normal(48, 3), np.random.normal(115, 8)]), np.random.normal(96, 2)
        else:
            temp, hr, o2 = np.random.normal(38.2, 0.3), np.random.normal(110, 8), np.random.normal(94, 1.5)
        temperature.append(np.clip(temp, 35.5, 39.2))
        heart_rate.append(np.clip(hr, 45, 120))
        blood_oxygen.append(np.clip(o2, 88, 100))
        labels.append('risky')

    for _ in range(dangerous_count):
        case_type = np.random.choice(['high_fever', 'severe_hypoxia', 'cardiac_event', 'hypothermia', 'multiple_severe'])
        if case_type == 'high_fever':
            temp, hr, o2 = np.random.normal(39.8, 0.8), np.random.normal(105, 15), np.random.normal(92, 3)
        elif case_type == 'severe_hypoxia':
            temp, hr, o2 = np.random.normal(37.2, 0.6), np.random.normal(85, 12), np.random.normal(87, 3)
        elif case_type == 'cardiac_event':
            temp, hr, o2 = np.random.normal(37.5, 0.5), np.random.choice([np.random.normal(42, 5), np.random.normal(125, 15)]), np.random.normal(90, 4)
        elif case_type == 'hypothermia':
            temp, hr, o2 = np.random.normal(34.5, 1.0), np.random.normal(55, 12), np.random.normal(89, 3)
        else:
            temp, hr, o2 = np.random.normal(39.5, 0.6), np.random.normal(120, 12), np.random.normal(87, 2)
        temperature.append(np.clip(temp, 33.0, 42.0))
        heart_rate.append(np.clip(hr, 35, 140))
        blood_oxygen.append(np.clip(o2, 80, 100))
        labels.append('dangerous')

    data = pd.DataFrame({
        'temperature': temperature,
        'heart_rate': heart_rate,
        'blood_oxygen': blood_oxygen,
        'label': labels
    }).sample(frac=1, random_state=42).reset_index(drop=True)

    return data

def calculate_health_score(row):
    temp = float(row['temperature'])
    hr = float(row['heart_rate'])
    o2 = float(row['blood_oxygen'])

    # Oxygen score
    if o2 >= 97:
        o2_score = 100
    elif o2 >= 95:
        o2_score = 90 - (97 - o2) * 5
    else:
        o2_score = max(0, 90 - (95 - o2) * 10)

    # Temperature score
    if 36 <= temp <= 37:
        temp_score = 100
    else:
        temp_score = max(0, 100 - abs(temp - 36.5) * 30)

    # Heart rate score
    if 60 <= hr <= 100:
        hr_score = 100
    else:
        hr_score = max(0, 100 - abs(hr - 80) * 2)

    total_score = np.clip((o2_score + temp_score + hr_score) / 3, 0, 100)

    if total_score >= 80:
        label = 'healthy'
    elif total_score >= 70:
        label = 'risky'
    else:
        label = 'dangerous'

    return pd.Series({'health_score': total_score, 'predicted_label': label})


print("Generating medically realistic elderly health data...")
improved_data = generate_realistic_health_data(1000)

print("\nCalculating health scores...")
scores = improved_data.apply(calculate_health_score, axis=1)
improved_data = pd.concat([improved_data, scores], axis=1)

print(f"\nDataset Summary:")
print(f"Total samples: {len(improved_data)}")
print(f"Label distribution:")
print(improved_data['predicted_label'].value_counts())

print(f"\nVital Signs Ranges:")
print(f"Temperature: {improved_data['temperature'].min():.1f} - {improved_data['temperature'].max():.1f}°C")
print(f"Heart Rate: {improved_data['heart_rate'].min():.1f} - {improved_data['heart_rate'].max():.1f} bpm")
print(f"Blood Oxygen: {improved_data['blood_oxygen'].min():.1f} - {improved_data['blood_oxygen'].max():.1f}%")

improved_data.to_csv('realistic_elderly_health_data.csv', index=False)
print(f"\nDataset saved to 'realistic_elderly_health_data.csv'")

print(f"\nSample cases:")
for label in ['healthy', 'risky', 'dangerous']:
    sample = improved_data[improved_data['predicted_label'] == label].iloc[0]
    print(f"{label.upper()}: Temp {sample['temperature']:.1f}°C, HR {sample['heart_rate']:.1f} bpm, O2 {sample['blood_oxygen']:.1f}%, Score {sample['health_score']:.1f}")
