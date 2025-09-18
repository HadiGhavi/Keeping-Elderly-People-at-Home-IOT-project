import cherrypy
import requests
import json
from datetime import datetime, timedelta
from itertools import groupby

class AdminPanel:
    @cherrypy.expose
    def index(self):
        cherrypy.response.headers['Content-Type'] = 'text/html'
        return """
<!DOCTYPE html>
<html>
<head>
    <title>Health Monitoring Admin Panel</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .header { background: #2c3e50; color: white; padding: 20px; margin: -20px -20px 20px -20px; }
        .nav { display: flex; gap: 20px; margin-bottom: 20px; }
        .nav a { background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }
        .nav a:hover { background: #2980b9; }
        .card { background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }
        .stat-box { text-align: center; padding: 20px; background: #ecf0f1; border-radius: 8px; }
        .stat-number { font-size: 2em; font-weight: bold; color: #2c3e50; }
        .alert { background: #e74c3c; color: white; padding: 15px; border-radius: 5px; margin: 10px 0; }
        .success { background: #27ae60; color: white; padding: 15px; border-radius: 5px; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Health Monitoring System - Admin Panel</h1>
        <p>Centralized management for healthcare providers and system monitoring</p>
    </div>
    
    <div class="nav">
        <a href="/dashboard">Dashboard</a>
        <a href="/doctor_registration">Register Doctor</a>
        <a href="/manage_doctors">Manage Doctors</a>
        <a href="/system_alerts">System Alerts</a>
        <a href="/patient_overview">Patient Overview</a>
        <a href="/reports">Generate Reports</a>
    </div>
    
    <div class="card">
        <h2>Quick Actions</h2>
        <div class="nav">
            <a href="/emergency_alerts">Emergency Alerts</a>
            <a href="/backup_data">Backup Data</a>
            <a href="/system_status">System Status</a>
        </div>
    </div>
</body>
</html>
        """

    @cherrypy.expose
    def dashboard(self):
        try:
            # Get system statistics
            users_response = requests.get("http://catalog:5001/users", timeout=10)
            doctors_response = requests.get("http://catalog:5001/doctors", timeout=10)
            
            total_users = len(users_response.json()) if users_response.status_code == 200 else 0
            total_doctors = len(doctors_response.json()) if doctors_response.status_code == 200 else 0
            
            # Get recent alerts (mock data for now)
            recent_alerts = self._get_recent_alerts()
            
            alerts_html = ""
            for alert in recent_alerts[:5]:
                alert_class = "alert" if alert['severity'] == 'critical' else "success"
                alerts_html += f'<div class="{alert_class}">{alert["message"]} - {alert["time"]}</div>'
            
            return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Admin Dashboard</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .stat-box {{ text-align: center; padding: 20px; background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .stat-number {{ font-size: 2em; font-weight: bold; color: #2c3e50; }}
        .card {{ background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .alert {{ background: #e74c3c; color: white; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .success {{ background: #27ae60; color: white; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .nav a {{ background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px; }}
    </style>
</head>
<body>
    <h1>System Dashboard</h1>
    <a href="/">← Back to Main Menu</a>
    
    <div class="stats">
        <div class="stat-box">
            <div class="stat-number">{total_users}</div>
            <div>Total Users</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">{total_doctors}</div>
            <div>Registered Doctors</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">{len(recent_alerts)}</div>
            <div>Recent Alerts</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">Online</div>
            <div>System Status</div>
        </div>
    </div>
    
    <div class="card">
        <h2>Recent System Alerts</h2>
        {alerts_html}
        <a href="/system_alerts">View All Alerts</a>
    </div>
    
    <div class="card">
        <h2>Quick Actions</h2>
        <a href="/emergency_alerts">Check Emergency Cases</a>
        <a href="/patient_overview">Patient Overview</a>
        <a href="/manage_doctors">Manage Doctors</a>
    </div>
</body>
</html>
            """
        except Exception as e:
            return f"<h1>Dashboard Error</h1><p>{str(e)}</p>"

    @cherrypy.expose
    def manage_doctors(self):
        try:
            # Get all doctors from the catalog
            response = requests.get("http://catalog:5001/doctors", timeout=10)
            doctors = response.json() if response.status_code == 200 else []
            
            doctor_rows = ""
            for doctor in doctors:
                # Get patient count for each doctor
                patients_response = requests.get(f"http://catalog:5001/doctors/{doctor['user_chat_id']}", timeout=10)
                patients = patients_response.json() if patients_response.status_code == 200 else []
                patient_count = len(patients)
                
                doctor_rows += f"""
                <tr>
                    <td>{doctor['full_name']}</td>
                    <td>{doctor.get('specialization', 'N/A')}</td>
                    <td>{doctor.get('hospital', 'N/A')}</td>
                    <td>{patient_count}</td>
                    <td>{doctor['user_chat_id']}</td>
                    <td>
                        <a href="/view_doctor_patients/{doctor['user_chat_id']}" style="color: #3498db;">View Patients</a> |
                        <a href="/doctor_stats/{doctor['user_chat_id']}" style="color: #27ae60;">Statistics</a>
                    </td>
                </tr>
                """
            
            return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Manage Doctors</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .btn {{ background: #3498db; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; }}
    </style>
</head>
<body>
    <h1>Doctor Management</h1>
    <a href="/">← Back to Main Menu</a>
    
    <div style="margin: 20px 0;">
        <a href="/doctor_registration" class="btn">Register New Doctor</a>
        <a href="/doctor_analytics" class="btn">Doctor Analytics</a>
    </div>
    
    <table>
        <thead>
            <tr>
                <th>Doctor Name</th>
                <th>Specialization</th>
                <th>Hospital</th>
                <th>Patient Count</th>
                <th>Chat ID</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {doctor_rows}
        </tbody>
    </table>
</body>
</html>
            """
        except Exception as e:
            return f"<h1>Error</h1><p>{str(e)}</p>"

    @cherrypy.expose
    def view_doctor_patients(self, doctor_id):
        try:
            # Get doctor info
            doctor_response = requests.get(f"http://catalog:5001/users/{doctor_id}", timeout=10)
            doctor = doctor_response.json() if doctor_response.status_code == 200 else {}
            
            # Get doctor's patients
            patients_response = requests.get(f"http://catalog:5001/doctors/{doctor_id}", timeout=10)
            patients = patients_response.json() if patients_response.status_code == 200 else []
            
            patient_rows = ""
            for patient in patients:
                # Get recent health status (you'll need to implement this based on your data structure)
                status = "Unknown"  # Placeholder
                last_reading = "N/A"  # Placeholder
                
                patient_rows += f"""
                <tr>
                    <td>{patient['full_name']}</td>
                    <td>{patient['user_chat_id']}</td>
                    <td>{status}</td>
                    <td>{last_reading}</td>
                    <td>
                        <a href="/sensorInfo/{patient['user_chat_id']}" style="color: #3498db;">View Data</a> |
                        <a href="/report/{patient['user_chat_id']}" style="color: #27ae60;">JSON Report</a>
                    </td>
                </tr>
                """
            
            return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Dr. {doctor.get('full_name', 'Unknown')}'s Patients</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <h1>Dr. {doctor.get('full_name', 'Unknown')}'s Patients</h1>
    <p><strong>Specialization:</strong> {doctor.get('specialization', 'N/A')}</p>
    <p><strong>Hospital:</strong> {doctor.get('hospital', 'N/A')}</p>
    
    <a href="/manage_doctors">← Back to Doctor Management</a>
    
    <table>
        <thead>
            <tr>
                <th>Patient Name</th>
                <th>Patient ID</th>
                <th>Health Status</th>
                <th>Last Reading</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {patient_rows}
        </tbody>
    </table>
</body>
</html>
            """
        except Exception as e:
            return f"<h1>Error</h1><p>{str(e)}</p>"

    @cherrypy.expose
    def patient_overview(self):
        try:
            # Get all users
            users_response = requests.get("http://catalog:5001/users", timeout=10)
            users = users_response.json() if users_response.status_code == 200 else []
            
            patient_rows = ""
            for user in users:
                if user.get('user_type') != 'doctor':  # Only show patients
                    doctor_name = "Unassigned"
                    if user.get('doctor_id'):
                        doctor_response = requests.get(f"http://catalog:5001/users/{user['doctor_id']}", timeout=5)
                        if doctor_response.status_code == 200:
                            doctor = doctor_response.json()
                            doctor_name = doctor.get('full_name', 'Unknown')
                    
                    patient_rows += f"""
                    <tr>
                        <td>{user['full_name']}</td>
                        <td>{user['user_chat_id']}</td>
                        <td>{doctor_name}</td>
                        <td>
                            <a href="/sensorInfo/{user['user_chat_id']}" style="color: #3498db;">View Health Data</a> |
                            <a href="/report/{user['user_chat_id']}" style="color: #27ae60;">JSON Report</a>
                        </td>
                    </tr>
                    """
            
            return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Patient Overview</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <h1>Patient Overview</h1>
    <a href="/">← Back to Main Menu</a>
    
    <table>
        <thead>
            <tr>
                <th>Patient Name</th>
                <th>Patient ID</th>
                <th>Assigned Doctor</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {patient_rows}
        </tbody>
    </table>
</body>
</html>
            """
        except Exception as e:
            return f"<h1>Error</h1><p>{str(e)}</p>"

    @cherrypy.expose
    def system_alerts(self):
        alerts = self._get_recent_alerts()
        
        alert_rows = ""
        for alert in alerts:
            severity_color = "#e74c3c" if alert['severity'] == 'critical' else "#f39c12" if alert['severity'] == 'warning' else "#27ae60"
            alert_rows += f"""
            <tr style="background-color: {severity_color}20;">
                <td>{alert['time']}</td>
                <td style="color: {severity_color}; font-weight: bold;">{alert['severity'].upper()}</td>
                <td>{alert['message']}</td>
                <td>{alert['source']}</td>
            </tr>
            """
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>System Alerts</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <h1>System Alerts</h1>
    <a href="/">← Back to Main Menu</a>
    
    <table>
        <thead>
            <tr>
                <th>Time</th>
                <th>Severity</th>
                <th>Message</th>
                <th>Source</th>
            </tr>
        </thead>
        <tbody>
            {alert_rows}
        </tbody>
    </table>
</body>
</html>
        """

    @cherrypy.expose
    def emergency_alerts(self):
        # This would check for patients in critical condition
        return """
<!DOCTYPE html>
<html>
<head>
    <title>Emergency Alerts</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .emergency { background: #e74c3c; color: white; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .warning { background: #f39c12; color: white; padding: 15px; margin: 10px 0; border-radius: 5px; }
    </style>
</head>
<body>
    <h1>🚨 Emergency Health Alerts</h1>
    <a href="/">← Back to Main Menu</a>
    
    <div class="emergency">
        <strong>CRITICAL:</strong> Patient ID 12345 - Temperature 40.2°C - Immediate attention required
        <br><small>Last updated: 2 minutes ago</small>
    </div>
    
    <div class="warning">
        <strong>WARNING:</strong> Patient ID 67890 - Heart rate 110 BPM - Monitor closely
        <br><small>Last updated: 5 minutes ago</small>
    </div>
    
    <p><em>This is a demo view. In production, this would show real-time critical health alerts.</em></p>
</body>
</html>
        """

    def _get_recent_alerts(self):
        # Mock alert data - in production, this would come from your monitoring system
        return [
            {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "severity": "critical",
                "message": "Patient vital signs exceeded dangerous threshold",
                "source": "Monitoring System"
            },
            {
                "time": (datetime.now() - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M"),
                "severity": "warning", 
                "message": "Database connection slow response time",
                "source": "Database Monitor"
            },
            {
                "time": (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"),
                "severity": "info",
                "message": "New doctor registration approved",
                "source": "Admin Panel"
            }
        ]

    # Keep your existing methods
    @cherrypy.expose
    def sensorInfo(self, user_id):
        # Your existing implementation
        try:
            data_service=requests.get("http://catalog:5001/services/dataIngestion")
            json_data=data_service.json()
            response = requests.get(json_data["url"] + ":"+ str(json_data["port"])+"/getUserData/"+user_id)
            sensor_data = json.loads(response.json())
            sensor_data.sort(key=lambda x: x['time'])
            
            table_rows = ""
            for entry in sensor_data:
                raw_time = entry.get('time')
                try:
                    clean_time = raw_time.split('+')[0].split('.')[0]  
                    dt = datetime.fromisoformat(clean_time)
                    formatted_time = dt.strftime('%B %d, %Y %I:%M %p')
                except (ValueError, AttributeError):
                    formatted_time = raw_time
                table_rows += f"""
                <tr>
                    <td>{formatted_time}</td>
                    <td>{entry.get('user_id')}</td>
                    <td>{entry.get('full_name')}</td>
                    <td>{entry.get('field')}</td>
                    <td>{entry.get('value')}</td>
                </tr>
                """
            
            return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Patient Health Data - User {user_id}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
        th {{ background-color: #f2f2f2; }}
        .nav {{ margin-bottom: 20px; }}
        .nav a {{ background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px; }}
    </style>
</head>
<body>
    <div class="nav">
        <a href="/">← Main Menu</a>
        <a href="/patient_overview">Patient Overview</a>
        <a href="/report/{user_id}">JSON Report</a>
    </div>
    
    <h1>Health Data for Patient {user_id}</h1>
    <table>
        <thead>
            <tr>
                <th>Time</th>
                <th>User ID</th>
                <th>Full Name</th>
                <th>Metric</th>
                <th>Value</th>
            </tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>
</body>
</html>
            """
        except Exception as e:
            return f"<h1>Error loading patient data</h1><p>{str(e)}</p>"

    @cherrypy.expose
    def report(self, user_id):
        # Your existing implementation
        try:
            data_service=requests.get("http://catalog:5001/services/dataIngestion")
            json_data=data_service.json()
            response = requests.get(json_data["url"] + ":"+ str(json_data["port"])+"/getUserData/"+user_id)
            sensor_data = json.loads(response.json())
            sensor_data.sort(key=lambda x: x['time'])
            return json.dumps(sensor_data).encode('utf-8')
        except Exception as e:
            return f"Error: {str(e)}"

    @cherrypy.expose
    def doctor_registration(self):
        # Your existing implementation with enhanced styling
        return """
<!DOCTYPE html>
<html>
<head>
    <title>Doctor Registration - Health Monitoring System</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; background: #f8f9fa; }
        .container { background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-weight: bold; color: #333; }
        input, select { width: 100%; padding: 12px; border: 2px solid #ddd; border-radius: 6px; font-size: 16px; }
        input:focus, select:focus { border-color: #3498db; outline: none; }
        .btn { background: #3498db; color: white; padding: 12px 30px; border: none; border-radius: 6px; cursor: pointer; font-size: 16px; width: 100%; }
        .btn:hover { background: #2980b9; }
        .info { background: #e3f2fd; padding: 20px; border-left: 4px solid #2196f3; margin-bottom: 25px; border-radius: 4px; }
        .nav { text-align: center; margin-bottom: 20px; }
        .nav a { color: #3498db; text-decoration: none; }
    </style>
</head>
<body>
    <div class="nav">
        <a href="/">← Back to Admin Panel</a>
    </div>
    
    <div class="container">
        <h1>Doctor Registration</h1>
        <div class="info">
            <p><strong>Healthcare Provider Registration</strong></p>
            <p>Register as a healthcare provider to monitor your patients' health data through our comprehensive monitoring system.</p>
        </div>
        
        <form method="post" action="/register_doctor_web">
            <div class="form-group">
                <label for="full_name">Full Name:</label>
                <input type="text" id="full_name" name="full_name" required 
                    placeholder="Dr. Sarah Johnson">
            </div>
            
            <div class="form-group">
                <label for="chat_id">Telegram Chat ID:</label>
                <input type="number" id="chat_id" name="chat_id" required 
                    placeholder="Get this from @userinfobot on Telegram">
                <small style="color: #666;">To find your Chat ID: Message @userinfobot on Telegram</small>
            </div>
            
            <div class="form-group">
                <label for="specialization">Medical Specialization:</label>
                <select id="specialization" name="specialization" required>
                    <option value="">Select Your Specialization</option>
                    <option value="General Practice">General Practice</option>
                    <option value="Cardiology">Cardiology</option>
                    <option value="Pediatrics">Pediatrics</option>
                    <option value="Geriatrics">Geriatrics</option>
                    <option value="Internal Medicine">Internal Medicine</option>
                    <option value="Emergency Medicine">Emergency Medicine</option>
                    <option value="Pulmonology">Pulmonology</option>
                    <option value="Endocrinology">Endocrinology</option>
                    <option value="Neurology">Neurology</option>
                    <option value="Other">Other</option>
                </select>
            </div>
            
            <div class="form-group">
                <label for="hospital">Hospital/Clinic/Practice:</label>
                <input type="text" id="hospital" name="hospital" 
                    placeholder="City General Hospital">
                <small style="color: #666;">Optional - Your workplace or practice name</small>
            </div>
            
            <button type="submit" class="btn">Register as Healthcare Provider</button>
        </form>
        
        <div style="margin-top: 25px; padding: 15px; background: #fff3cd; border-radius: 5px;">
            <p><strong>After Registration:</strong></p>
            <ul style="margin: 10px 0; padding-left: 20px;">
                <li>You'll receive admin privileges for assigned patients</li>
                <li>Access real-time health monitoring data</li>
                <li>Receive automatic alerts for critical conditions</li>
                <li>Generate comprehensive health reports</li>
            </ul>
        </div>
    </div>
</body>
</html>
        """

    @cherrypy.expose
    def register_doctor_web(self, full_name, chat_id, specialization, hospital=""):
        # Your existing implementation with enhanced success page
        try:
            doctor_data = {
                "user_chat_id": int(chat_id),
                "full_name": full_name,
                "specialization": specialization,
                "hospital": hospital
            }
            
            response = requests.post("http://catalog:5001/doctors", json=doctor_data)
            if response.status_code in [200, 201]:
                return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Registration Successful</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; background: #f8f9fa; }}
        .container {{ background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .success {{ background: #d4edda; color: #155724; padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #28a745; }}
        .nav a {{ background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="success">
            <h2>✅ Registration Successful!</h2>
            <p><strong>Dr. {full_name}</strong> has been successfully registered in the system.</p>
        </div>
        
        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <h3>Registration Details:</h3>
            <p><strong>Name:</strong> {full_name}</p>
            <p><strong>Specialization:</strong> {specialization}</p>
            <p><strong>Hospital/Clinic:</strong> {hospital or 'Not specified'}</p>
            <p><strong>Telegram ID:</strong> {chat_id}</p>
        </div>
        
        <div style="background: #e3f2fd; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <h3>Next Steps:</h3>
            <ol>
                <li>Open Telegram and find the health monitoring bot</li>
                <li>Start a conversation and use <code>/menu</code> to access your doctor dashboard</li>
                <li>Patients can now assign you as their doctor</li>
                <li>You'll receive automatic alerts for patients in critical condition</li>
                <li>Access comprehensive health monitoring and reporting tools</li>
            </ol>
        </div>
        
        <div style="text-align: center;">
            <a href="/doctor_registration" class="nav">Register Another Doctor</a>
            <a href="/manage_doctors" class="nav">View All Doctors</a>
            <a href="/" class="nav">Back to Admin Panel</a>
        </div>
    </div>
</body>
</html>
                """
            else:
                return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Registration Failed</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; background: #f8f9fa; }}
        .container {{ background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .error {{ background: #f8d7da; color: #721c24; padding: 20px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #dc3545; }}
        .nav a {{ background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="error">
            <h2>❌ Registration Failed</h2>
            <p><strong>Error:</strong> {response.text}</p>
            <p>This usually happens when:</p>
            <ul>
                <li>The Chat ID is already registered</li>
                <li>Invalid Chat ID format</li>
                <li>Server connection issues</li>
            </ul>
        </div>
        
        <div style="text-align: center;">
            <a href="/doctor_registration" class="nav">Try Again</a>
        </div>
    </div>
</body>
</html>
                """
        except Exception as e:
            return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Registration Error</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; background: #f8f9fa; }}
        .container {{ background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .error {{ background: #f8d7da; color: #721c24; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .nav a {{ background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="error">
            <h2>System Error</h2>
            <p>{str(e)}</p>
        </div>
        <div style="text-align: center;">
            <a href="/doctor_registration" class="nav">Try Again</a>
        </div>
    </div>
</body>
</html>
            """


if __name__ == "__main__":
    # Register the service
    response = requests.post(
        f"http://catalog:5001/services/",
        json={
            "adminPanel": {
                "url": "http://admin_panel",
                "port": 9000,
                "endpoints": {
                    "GET /": "Admin panel home page",
                    "GET /dashboard": "System dashboard with statistics",
                    "GET /doctor_registration": "Doctor registration form",
                    "POST /register_doctor_web": "Process doctor registration",
                    "GET /manage_doctors": "View and manage all doctors",
                    "GET /view_doctor_patients/<doctor_id>": "View patients for specific doctor",
                    "GET /patient_overview": "Overview of all patients",
                    "GET /system_alerts": "View system alerts and notifications",
                    "GET /emergency_alerts": "View emergency health alerts",
                    "GET /sensorInfo/<userid>": "get user sensor data by id => Html view",
                    "GET /report/<userid>": "get user sensor data by id => json"
                }
            }
        }
    )
    
    cherrypy.config.update({
        "server.socket_host": "0.0.0.0",
        "server.socket_port": 9000,
        "tools.response_headers.on": True,
        "tools.response_headers.headers": [("Content-Type", "text/html")]
    })
    cherrypy.quickstart(AdminPanel())