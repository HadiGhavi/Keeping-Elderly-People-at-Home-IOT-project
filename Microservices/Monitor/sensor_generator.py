import random
import time
import math
from datetime import datetime

class GenerateSensor:
    def __init__(self):
        # Base physiological values for healthy adults
        self.base_values = {
            'temp': 36.5,        # Normal body temperature in Celsius
            'heart_rate': 75,    # Normal resting heart rate
            'oxygen': 98         # Normal oxygen saturation
        }
        
        # Natural variation ranges (realistic fluctuations)
        self.variation_ranges = {
            'temp': 1.0,         # ±1°C variation
            'heart_rate': 15,    # ±15 BPM variation
            'oxygen': 2          # ±2% variation
        }
        
        # Time-based patterns (circadian rhythms, activity cycles)
        self.time_factors = {
            'temp': 0.5,         # Temperature varies throughout day
            'heart_rate': 10,    # Heart rate varies with activity
            'oxygen': 1          # Oxygen less time-dependent
        }
        
        # Previous values for smoothing (realistic gradual changes)
        self.last_values = {}
        
        # Activity simulation (affects heart rate and oxygen)
        self.activity_cycle = 0
        
    def _get_time_factor(self, sensor_type):
        """Calculate time-based variation using circadian patterns"""
        current_hour = datetime.now().hour
        
        if sensor_type == 'temp':
            # Body temperature lowest around 4-6 AM, highest around 6-8 PM
            temp_cycle = math.sin((current_hour - 6) * math.pi / 12)
            return temp_cycle * 0.3  # ±0.3°C circadian variation
            
        elif sensor_type == 'heart_rate':
            # Heart rate lower during night, higher during day
            hr_cycle = math.sin((current_hour - 6) * math.pi / 12)
            return hr_cycle * 5  # ±5 BPM circadian variation
            
        return 0
    
    def _get_activity_factor(self, sensor_type):
        """Simulate random activity that affects vitals"""
        # Increment activity cycle for simulation
        self.activity_cycle += random.uniform(-0.1, 0.2)
        self.activity_cycle = max(0, min(1, self.activity_cycle))  # Keep between 0-1
        
        if sensor_type == 'heart_rate':
            # Activity increases heart rate
            return self.activity_cycle * 25  # Up to +25 BPM during activity
            
        elif sensor_type == 'oxygen':
            # Light activity might slightly decrease oxygen
            return -self.activity_cycle * 1  # Up to -1% during activity
            
        elif sensor_type == 'temp':
            # Activity slightly increases temperature
            return self.activity_cycle * 0.2  # Up to +0.2°C during activity
            
        return 0
    
    def _smooth_value(self, sensor_type, new_value):
        """Apply smoothing to prevent unrealistic jumps"""
        if sensor_type not in self.last_values:
            self.last_values[sensor_type] = new_value
            return new_value
        
        # Smoothing factor (how much change is allowed per reading)
        smoothing_factors = {
            'temp': 0.1,         # Temperature changes slowly
            'heart_rate': 3,     # Heart rate can change more quickly
            'oxygen': 0.5        # Oxygen changes moderately
        }
        
        max_change = smoothing_factors.get(sensor_type, 1)
        last_value = self.last_values[sensor_type]
        
        # Limit the change from last reading
        if abs(new_value - last_value) > max_change:
            if new_value > last_value:
                new_value = last_value + max_change
            else:
                new_value = last_value - max_change
        
        self.last_values[sensor_type] = new_value
        return new_value
    
    def _detect_sensor_type(self, min_value, max_value):
        """Automatically detect sensor type based on ranges"""
        avg_value = (min_value + max_value) / 2
        
        if 30 <= avg_value <= 45:
            return 'temp'
        elif 50 <= avg_value <= 120:
            return 'heart_rate'
        elif 85 <= avg_value <= 100:
            return 'oxygen'
        else:
            # Default to generic sensor
            return 'generic'
    
    def read_value(self, min_value, max_value, sensor_name=None):
        """Generate realistic sensor values with natural variations"""
        
        # Detect sensor type if not provided
        if sensor_name:
            # Extract sensor type from name
            if 'temp' in sensor_name.lower():
                sensor_type = 'temp'
            elif 'heart' in sensor_name.lower() or 'pulse' in sensor_name.lower():
                sensor_type = 'heart_rate'
            elif 'oxygen' in sensor_name.lower() or 'spo2' in sensor_name.lower():
                sensor_type = 'oxygen'
            else:
                sensor_type = 'generic'
        else:
            sensor_type = self._detect_sensor_type(min_value, max_value)
    
        print(f"Detected sensor type: {sensor_type}")

        if sensor_type == 'generic':
            # For unknown sensors, use simple random generation
            return round(random.uniform(min_value, max_value), 1)
        
        # Start with physiologically normal base value
        base_value = self.base_values[sensor_type]
        
        # Add natural random variation
        random_variation = random.gauss(0, self.variation_ranges[sensor_type] / 3)
        
        # Add time-based (circadian) variation
        time_variation = self._get_time_factor(sensor_type)
        
        # Add activity-based variation
        activity_variation = self._get_activity_factor(sensor_type)
        
        # Combine all factors
        new_value = base_value + random_variation + time_variation + activity_variation
        
        # Apply smoothing for realistic gradual changes
        new_value = self._smooth_value(sensor_type, new_value)
        
        # Apply realistic bounds
        if sensor_type == 'temp':
            new_value = max(34.0, min(42.0, new_value))  # Survivable temperature range
        elif sensor_type == 'heart_rate':
            new_value = max(40, min(180, new_value))     # Realistic heart rate range
        elif sensor_type == 'oxygen':
            new_value = max(80, min(100, new_value))     # Realistic oxygen saturation
        
        # Occasionally generate concerning values for testing alerts
        if random.random() < 0.05:  # 5% chance of concerning reading
            if sensor_type == 'temp':
                if random.choice([True, False]):
                    new_value = random.uniform(38.5, 40.0)  # Fever
                else:
                    new_value = random.uniform(35.0, 36.0)  # Hypothermia
            elif sensor_type == 'heart_rate':
                if random.choice([True, False]):
                    new_value = random.uniform(100, 140)    # Tachycardia
                else:
                    new_value = random.uniform(45, 55)      # Bradycardia
            elif sensor_type == 'oxygen':
                new_value = random.uniform(88, 94)          # Low oxygen
        
        # Round appropriately and return
        if sensor_type == 'heart_rate':
            return int(round(new_value))
        else:
            return round(new_value, 1)

# For testing and demonstration
if __name__ == "__main__":
    sensor = GenerateSensor()
    
    print("Realistic Health Sensor Simulation")
    print("=" * 40)
    
    for i in range(10):
        temp = sensor.read_value(35, 40, "temp")
        hr = sensor.read_value(60, 100, "heart_rate") 
        oxygen = sensor.read_value(90, 100, "oxygen")
        
        print(f"Reading {i+1}: Temp: {temp}°C, HR: {hr} BPM, O2: {oxygen}%")
        time.sleep(1)