import random
import time
import math
from datetime import datetime, timedelta
import argparse
import sys
import os

# Add the current directory to path to import your adapter
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from influxdbAdapter import InfluxDBAdapter

class HealthSensorGenerator:
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
        
        # Previous values for smoothing (realistic gradual changes)
        self.last_values = {}
        
        # Activity simulation (affects heart rate and oxygen)
        self.activity_cycle = 0
        
        # Health state simulation
        self.current_health_state = 'normal'
        self.state_change_probability = 0.02  # 2% chance per reading
        
    def _get_time_factor(self, sensor_type, current_time):
        """Calculate time-based variation using circadian patterns"""
        current_hour = current_time.hour
        
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
    
    def _update_health_state(self):
        """Randomly update health state with dangerous > risky > normal priority"""
        if random.random() < self.state_change_probability:
            states = ['normal', 'risky', 'dangerous']
            weights = [0.7, 0.25, 0.05]  # 70% normal, 25% risky, 5% dangerous
            self.current_health_state = random.choices(states, weights=weights)[0]
    
    def _apply_health_state_effects(self, sensor_type, base_value):
        """Modify sensor values based on current health state"""
        if self.current_health_state == 'normal':
            return base_value
        
        elif self.current_health_state == 'risky':
            if sensor_type == 'temp':
                return base_value + random.uniform(0.5, 1.5)  # Mild fever
            elif sensor_type == 'heart_rate':
                return base_value + random.uniform(10, 25)    # Elevated HR
            elif sensor_type == 'oxygen':
                return base_value - random.uniform(2, 4)      # Slightly low oxygen
        
        elif self.current_health_state == 'dangerous':
            if sensor_type == 'temp':
                return base_value + random.uniform(2.0, 3.5)  # High fever
            elif sensor_type == 'heart_rate':
                return base_value + random.uniform(25, 50)    # Very high HR
            elif sensor_type == 'oxygen':
                return base_value - random.uniform(5, 10)     # Low oxygen
        
        return base_value
    
    def read_value(self, sensor_type, current_time):
        """Generate realistic sensor values with natural variations"""
        
        # Update health state occasionally
        self._update_health_state()
        
        # Start with physiologically normal base value
        base_value = self.base_values[sensor_type]
        
        # Add natural random variation
        random_variation = random.gauss(0, self.variation_ranges[sensor_type] / 3)
        
        # Add time-based (circadian) variation
        time_variation = self._get_time_factor(sensor_type, current_time)
        
        # Add activity-based variation
        activity_variation = self._get_activity_factor(sensor_type)
        
        # Apply health state effects
        health_effect = self._apply_health_state_effects(sensor_type, 0)
        
        # Combine all factors
        new_value = base_value + random_variation + time_variation + activity_variation + health_effect
        
        # Apply smoothing for realistic gradual changes
        new_value = self._smooth_value(sensor_type, new_value)
        
        # Apply realistic bounds
        if sensor_type == 'temp':
            new_value = max(34.0, min(43.0, new_value))  # Survivable temperature range
        elif sensor_type == 'heart_rate':
            new_value = max(40, min(200, new_value))     # Realistic heart rate range
        elif sensor_type == 'oxygen':
            new_value = max(75, min(100, new_value))     # Realistic oxygen saturation
        
        # Return as float (matching test.py approach)
        return float(round(new_value, 1))

class InfluxDBPopulator:
    def __init__(self, config):
        """Initialize with InfluxDB configuration using your existing adapter"""
        self.adapter = InfluxDBAdapter(config)
        self.sensor_generator = HealthSensorGenerator()
        
    def connect(self):
        """Connect to InfluxDB using your adapter"""
        return self.adapter.connect()
        
    def disconnect(self):
        """Disconnect from InfluxDB"""
        return self.adapter.disconnect()
        
    def _write_combined_data(self, user_id, full_name, timestamp):
        """Write all vital signs as separate fields in one measurement (like test.py)"""
        
        # Generate all vital signs
        temp = self.sensor_generator.read_value('temp', timestamp)
        heart_rate = self.sensor_generator.read_value('heart_rate', timestamp)
        oxygen = self.sensor_generator.read_value('oxygen', timestamp)
        health_state = self.sensor_generator.current_health_state
        
        # Create single data point with all vitals as fields 
        data = {
            "tags": {
                "UserId": str(user_id),
                "full_name": full_name
            },
            "fields": {
                "temp": float(temp),
                "heart_rate": float(heart_rate), 
                "oxygen": float(oxygen),
                "state": health_state  # String field for health state
            },
            "timestamp": timestamp
        }
        
        return self.adapter.write_data("value", data)
    
    def generate_historical_data(self, hours_back=24, interval_minutes=1, user_id="user_001", full_name="Test User"):
        """Generate historical data for the specified time range"""
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours_back)
        current_time = start_time
        
        print(f"Generating data for user {user_id} ({full_name}) from {start_time} to {end_time}")
        print(f"Interval: {interval_minutes} minutes")
        
        success_count = 0
        error_count = 0
        total_expected = int((hours_back * 60) / interval_minutes)
        
        while current_time < end_time:
            # Write combined data point (all vitals + state in one record)
            success, message = self._write_combined_data(user_id, full_name, current_time)
            
            if success:
                success_count += 1
            else:
                error_count += 1
                print(f"Error writing data at {current_time}: {message}")
            
            # Progress indicator every 10% completion
            progress = success_count + error_count
            if progress % max(1, total_expected // 10) == 0:
                percent = (progress / total_expected) * 100
                print(f"Progress: {progress}/{total_expected} ({percent:.1f}%) - Success: {success_count}, Errors: {error_count}")
            
            current_time += timedelta(minutes=interval_minutes)
        
        print(f"\nData generation complete!")
        print(f"Total records: {success_count + error_count}")
        print(f"Successful writes: {success_count}")
        print(f"Failed writes: {error_count}")
        print(f"Success rate: {(success_count/(success_count + error_count)*100):.1f}%")
        
        # Show some sample data
        self._show_sample_data(user_id)
    
    def generate_realtime_data(self, user_id="user_001", full_name="Test User", interval_seconds=10):
        """Generate real-time data continuously"""
        
        print(f"Starting real-time data generation for user {user_id} ({full_name})")
        print(f"Interval: {interval_seconds}s")
        print("Press Ctrl+C to stop")
        
        try:
            while True:
                current_time = datetime.utcnow()
                
                # Write combined data point
                success, message = self._write_combined_data(user_id, full_name, current_time)
                
                # Get the current values for display
                temp = self.sensor_generator.last_values.get('temp', 'N/A')
                heart_rate = self.sensor_generator.last_values.get('heart_rate', 'N/A')
                oxygen = self.sensor_generator.last_values.get('oxygen', 'N/A')
                state = self.sensor_generator.current_health_state
                
                # Show status
                status = "✓" if success else "✗"
                print(f"{status} {current_time.strftime('%H:%M:%S')}: Temp={temp}°C, HR={heart_rate}bpm, O2={oxygen}%, State={state}")
                
                if not success:
                    print(f"  Error: {message}")
                
                time.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            print("\nStopped data generation")
    
    def _show_sample_data(self, user_id):
        """Show sample data that was written"""
        print(f"\nSample data for user {user_id}:")
        
        time_range = {
            'start': datetime.utcnow() - timedelta(hours=1),
            'end': datetime.utcnow()
        }
        
        success, data = self.adapter.get_user_data(user_id, time_range)
        
        if success and data:
            print(f"Found {len(data)} records in the last hour")
            
            # Show latest record
            if data:
                latest = data[-1]
                print(f"Latest record: {latest}")
                
        else:
            print(f"No data found or error: {data}")
    
    def generate_multiple_users(self, users_config, hours_back=24, interval_minutes=5):
        """Generate data for multiple users"""
        print(f"Generating data for {len(users_config)} users")
        
        for i, user_config in enumerate(users_config):
            user_id = user_config.get('user_id', f'user_{i+1:03d}')
            full_name = user_config.get('full_name', f'Test User {user_id}')
            
            print(f"\nGenerating data for user {i+1}/{len(users_config)}: {user_id} ({full_name})")
            
            # Reset sensor generator for each user to get different patterns
            self.sensor_generator = HealthSensorGenerator()
            
            self.generate_historical_data(
                hours_back=hours_back,
                interval_minutes=interval_minutes,
                user_id=user_id,
                full_name=full_name
            )

def main():
    parser = argparse.ArgumentParser(description='Generate health sensor data for InfluxDB using simplified approach')
    parser.add_argument('--host', required=True, help='InfluxDB URL (e.g., http://localhost:8086)')
    parser.add_argument('--token', required=True, help='InfluxDB token')
    parser.add_argument('--org', required=True, help='InfluxDB organization')
    parser.add_argument('--bucket', required=True, help='InfluxDB bucket')
    parser.add_argument('--mode', choices=['historical', 'realtime', 'both-users'], required=True,
                       help='Data generation mode')
    parser.add_argument('--hours-back', type=int, default=24, 
                       help='Hours of historical data to generate (for historical mode)')
    parser.add_argument('--interval-minutes', type=float, default=1.0,
                       help='Interval in minutes for historical data')
    parser.add_argument('--interval-seconds', type=int, default=10,
                       help='Interval in seconds for real-time data')
    parser.add_argument('--user-choice', choices=['riccardo', 'hadi', 'both'], default='both',
                       help='Which user to generate data for')
    
    args = parser.parse_args()
    
    # Hardcoded users from your specification
    HARDCODED_USERS = [
        {
            "user_chat_id": 548805315,
            "full_name": "Riccardo Fida",
            "sensors": [
                {"id": 1, "name": "temp"},
                {"id": 2, "name": "oxygen"},
                {"id": 3, "name": "heart_rate"}
            ],
            "doctor_id": None,
            "user_type": "patient"
        },
        {
            "user_chat_id": 6378242947,
            "full_name": "<Hadi>",
            "sensors": [
                {"id": 1, "name": "temp"},
                {"id": 2, "name": "oxygen"},
                {"id": 3, "name": "heart_rate"}
            ],
            "doctor_id": None,
            "user_type": "patient"
        }
    ]
    
    # Create configuration for your adapter
    config = {
        'host': args.host,
        'token': args.token,
        'org': args.org,
        'bucket': args.bucket
    }
    
    # Create populator instance
    populator = InfluxDBPopulator(config)
    
    # Connect to InfluxDB
    print("Connecting to InfluxDB...")
    if not populator.connect():
        print("Failed to connect to InfluxDB")
        return
    print("✓ Connected to InfluxDB")
    
    # Select users based on choice
    selected_users = []
    if args.user_choice == 'riccardo':
        selected_users = [HARDCODED_USERS[0]]
    elif args.user_choice == 'hadi':
        selected_users = [HARDCODED_USERS[1]]
    else:  # both
        selected_users = HARDCODED_USERS
    
    print(f"Selected users: {[user['full_name'] for user in selected_users]}")
    
    try:
        if args.mode == 'historical':
            # Generate for first selected user only
            user = selected_users[0]
            print(f"\nGenerating historical data for: {user['full_name']} (ID: {user['user_chat_id']})")
            
            populator.generate_historical_data(
                hours_back=args.hours_back,
                interval_minutes=args.interval_minutes,
                user_id=str(user['user_chat_id']),
                full_name=user['full_name']
            )
            
        elif args.mode == 'realtime':
            # Generate for first selected user only
            user = selected_users[0]
            print(f"\nGenerating real-time data for: {user['full_name']} (ID: {user['user_chat_id']})")
            
            populator.generate_realtime_data(
                user_id=str(user['user_chat_id']),
                full_name=user['full_name'],
                interval_seconds=args.interval_seconds
            )
            
        elif args.mode == 'both-users':
            # Generate historical data for both hardcoded users
            print(f"\nGenerating data for both hardcoded users")
            
            users_config = []
            for user in selected_users:
                users_config.append({
                    'user_id': str(user['user_chat_id']),
                    'full_name': user['full_name']
                })
                print(f"  - {user['full_name']} (ID: {user['user_chat_id']})")
            
            populator.generate_multiple_users(
                users_config=users_config,
                hours_back=args.hours_back,
                interval_minutes=args.interval_minutes
            )
            
    finally:
        populator.disconnect()
        print("🔌 Disconnected from InfluxDB")

if __name__ == "__main__":
    main()