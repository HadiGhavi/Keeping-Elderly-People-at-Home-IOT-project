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
    
    @cherrypy.expose
    def reports(self):
        return """
<!DOCTYPE html>
<html>
<head>
    <title>Generate Reports</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; }
        .card { background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .report-option { display: flex; justify-content: space-between; align-items: center; padding: 15px; border: 1px solid #ddd; margin: 10px 0; border-radius: 5px; }
        .btn { background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; border: none; cursor: pointer; }
        .btn:hover { background: #2980b9; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        select, input { width: 200px; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Report Generation</h1>
        <a href="/">← Back to Main Menu</a>
        
        <div class="card">
            <h2>System Reports</h2>
            
            <div class="report-option">
                <div>
                    <h3>Patient Summary Report</h3>
                    <p>Overview of all patients, their assigned doctors, and current status</p>
                </div>
                <a href="/generate_patient_report" class="btn">Generate</a>
            </div>
            
            <div class="report-option">
                <div>
                    <h3>Doctor Workload Report</h3>
                    <p>Statistics on doctor patient assignments and specializations</p>
                </div>
                <a href="/generate_doctor_report" class="btn">Generate</a>
            </div>
            
            <div class="report-option">
                <div>
                    <h3>System Health Report</h3>
                    <p>Overall system status, alerts, and performance metrics</p>
                </div>
                <a href="/generate_system_report" class="btn">Generate</a>
            </div>
        </div>
        
        <div class="card">
            <h2>Custom Reports</h2>
            <form method="get" action="/generate_custom_report">
                <div class="form-group">
                    <label for="report_type">Report Type:</label>
                    <select id="report_type" name="report_type">
                        <option value="patient_health">Patient Health Data</option>
                        <option value="doctor_performance">Doctor Performance</option>
                        <option value="alert_summary">Alert Summary</option>
                        <option value="system_usage">System Usage</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label for="time_range">Time Range:</label>
                    <select id="time_range" name="time_range">
                        <option value="24h">Last 24 Hours</option>
                        <option value="7d">Last 7 Days</option>
                        <option value="30d">Last 30 Days</option>
                        <option value="90d">Last 90 Days</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label for="format">Export Format:</label>
                    <select id="format" name="format">
                        <option value="html">HTML (View in Browser)</option>
                        <option value="json">JSON (Raw Data)</option>
                        <option value="csv">CSV (Spreadsheet)</option>
                    </select>
                </div>
                
                <button type="submit" class="btn">Generate Custom Report</button>
            </form>
        </div>
    </div>
</body>
</html>
        """

    @cherrypy.expose
    def generate_patient_report(self):
        try:
            users_response = requests.get("http://catalog:5001/users", timeout=10)
            users = users_response.json() if users_response.status_code == 200 else []
            
            patients = [user for user in users if user.get('user_type') != 'doctor']
            
            report_rows = ""
            for patient in patients:
                doctor_name = "Unassigned"
                doctor_specialization = "N/A"
                
                if patient.get('doctor_id'):
                    doctor_response = requests.get(f"http://catalog:5001/users/{patient['doctor_id']}", timeout=5)
                    if doctor_response.status_code == 200:
                        doctor = doctor_response.json()
                        doctor_name = doctor.get('full_name', 'Unknown')
                        doctor_specialization = doctor.get('specialization', 'N/A')
                
                sensor_count = len(patient.get('sensors', []))
                
                report_rows += f"""
                <tr>
                    <td>{patient['full_name']}</td>
                    <td>{patient['user_chat_id']}</td>
                    <td>{doctor_name}</td>
                    <td>{doctor_specialization}</td>
                    <td>{sensor_count}</td>
                    <td>Active</td>
                </tr>
                """
            
            return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Patient Summary Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .header {{ background: #2c3e50; color: white; padding: 20px; margin: -20px -20px 20px -20px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-box {{ text-align: center; padding: 15px; background: #ecf0f1; border-radius: 5px; }}
        .print-btn {{ background: #27ae60; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin: 10px 5px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Patient Summary Report</h1>
        <p>Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
    </div>
    
    <div class="stats">
        <div class="stat-box">
            <strong>{len(patients)}</strong><br>Total Patients
        </div>
        <div class="stat-box">
            <strong>{len([p for p in patients if p.get('doctor_id')])}</strong><br>Assigned Patients
        </div>
        <div class="stat-box">
            <strong>{len([p for p in patients if not p.get('doctor_id')])}</strong><br>Unassigned Patients
        </div>
    </div>
    
    <a href="/reports">← Back to Reports</a>
    <a href="javascript:window.print()" class="print-btn">Print Report</a>
    
    <table>
        <thead>
            <tr>
                <th>Patient Name</th>
                <th>Patient ID</th>
                <th>Assigned Doctor</th>
                <th>Doctor Specialization</th>
                <th>Sensors</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>
            {report_rows}
        </tbody>
    </table>
</body>
</html>
            """
        except Exception as e:
            return f"<h1>Report Generation Error</h1><p>{str(e)}</p>"

    @cherrypy.expose
    def generate_doctor_report(self):
        try:
            users_response = requests.get("http://catalog:5001/users", timeout=10)
            users = users_response.json() if users_response.status_code == 200 else []
            
            doctors = [user for user in users if user.get('user_type') == 'doctor']
            
            report_rows = ""
            total_patients = 0
            
            for doctor in doctors:
                patient_count = len(doctor.get('patients', []))
                total_patients += patient_count
                
                # Calculate workload level
                if patient_count == 0:
                    workload = "None"
                elif patient_count <= 2:
                    workload = "Light"
                elif patient_count <= 4:
                    workload = "Moderate"
                else:
                    workload = "Heavy"
                
                report_rows += f"""
                <tr>
                    <td>{doctor['full_name']}</td>
                    <td>{doctor.get('specialization', 'N/A')}</td>
                    <td>{doctor.get('hospital', 'N/A')}</td>
                    <td>{patient_count}</td>
                    <td>{workload}</td>
                    <td>Active</td>
                </tr>
                """
            
            avg_patients = round(total_patients / len(doctors), 1) if doctors else 0
            
            return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Doctor Workload Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .header {{ background: #2c3e50; color: white; padding: 20px; margin: -20px -20px 20px -20px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-box {{ text-align: center; padding: 15px; background: #ecf0f1; border-radius: 5px; }}
        .print-btn {{ background: #27ae60; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin: 10px 5px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Doctor Workload Report</h1>
        <p>Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
    </div>
    
    <div class="stats">
        <div class="stat-box">
            <strong>{len(doctors)}</strong><br>Total Doctors
        </div>
        <div class="stat-box">
            <strong>{total_patients}</strong><br>Total Patients
        </div>
        <div class="stat-box">
            <strong>{avg_patients}</strong><br>Avg Patients/Doctor
        </div>
        <div class="stat-box">
            <strong>{len([d for d in doctors if len(d.get('patients', [])) == 0])}</strong><br>Doctors w/o Patients
        </div>
    </div>
    
    <a href="/reports">← Back to Reports</a>
    <a href="javascript:window.print()" class="print-btn">Print Report</a>
    
    <table>
        <thead>
            <tr>
                <th>Doctor Name</th>
                <th>Specialization</th>
                <th>Hospital/Clinic</th>
                <th>Patient Count</th>
                <th>Workload Level</th>
                <th>Status</th>
            </tr>
        </thead>
        <tbody>
            {report_rows}
        </tbody>
    </table>
</body>
</html>
            """
        except Exception as e:
            return f"<h1>Report Generation Error</h1><p>{str(e)}</p>"

    @cherrypy.expose 
    def generate_system_report(self):
        try:
            users_response = requests.get("http://catalog:5001/users", timeout=10)
            users = users_response.json() if users_response.status_code == 200 else []
            
            total_users = len(users)
            doctors = [u for u in users if u.get('user_type') == 'doctor']
            patients = [u for u in users if u.get('user_type') != 'doctor']
            
            alerts = self._get_recent_alerts()
            critical_alerts = [a for a in alerts if a['severity'] == 'critical']
            
            return f"""
<!DOCTYPE html>
<html>
<head>
    <title>System Health Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #2c3e50; color: white; padding: 20px; margin: -20px -20px 20px -20px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
        .stat-box {{ text-align: center; padding: 20px; background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .stat-number {{ font-size: 2em; font-weight: bold; color: #2c3e50; }}
        .alert {{ background: #e74c3c; color: white; padding: 10px; margin: 5px 0; border-radius: 5px; }}
        .warning {{ background: #f39c12; color: white; padding: 10px; margin: 5px 0; border-radius: 5px; }}
        .success {{ background: #27ae60; color: white; padding: 10px; margin: 5px 0; border-radius: 5px; }}
        .print-btn {{ background: #27ae60; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin: 10px 5px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>System Health Report</h1>
        <p>System Status Overview - Generated on: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
    </div>
    
    <div class="stats">
        <div class="stat-box">
            <div class="stat-number">{total_users}</div>
            <div>Total System Users</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">{len(doctors)}</div>
            <div>Registered Doctors</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">{len(patients)}</div>
            <div>Active Patients</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">{len(critical_alerts)}</div>
            <div>Critical Alerts</div>
        </div>
    </div>
    
    <a href="/reports">← Back to Reports</a>
    <a href="javascript:window.print()" class="print-btn">Print Report</a>
    
    <h2>Recent System Activity</h2>
    <div class="success">System Status: Operational</div>
    <div class="success">Database: Connected</div>
    <div class="success">MQTT Broker: Active</div>
    <div class="warning">Monitoring Service: Normal Load</div>
    
    <h2>Recent Alerts</h2>
    <div class="alert">Critical: {len(critical_alerts)} alerts require attention</div>
    <div class="warning">Warning: {len([a for a in alerts if a['severity'] == 'warning'])} system warnings</div>
    
    <h2>Service Status</h2>
    <ul>
        <li><strong>Catalog Service:</strong> Online</li>
        <li><strong>Database Adapter:</strong> Online</li>
        <li><strong>Data Ingestion:</strong> Online</li>
        <li><strong>Monitor Service:</strong> Online</li>
        <li><strong>Admin Panel:</strong> Online</li>
        <li><strong>Notification Service:</strong> Online</li>
    </ul>
</body>
</html>
            """
        except Exception as e:
            return f"<h1>Report Generation Error</h1><p>{str(e)}</p>"
    @cherrypy.expose
    def sensorInfo(self, user_id, hours=24):
        """Get user sensor data through database adapter with optional time filtering"""
        try:
            # Get database adapter service info from catalog
            adapter_service = requests.get("http://catalog:5001/services/databaseAdapter")
            if adapter_service.status_code != 200:
                return f"<h1>Service Error</h1><p>Could not reach database adapter service</p>"
            
            adapter_info = adapter_service.json()
            adapter_url = adapter_info["url"]
            adapter_port = adapter_info.get("port")
            
            # Build the URL for database adapter
            if adapter_port:
                full_url = f"{adapter_url}:{adapter_port}/read/{user_id}"
            else:
                full_url = f"{adapter_url}/read/{user_id}"
            
            # Add time filtering parameter
            params = {"hours": hours}
            
            # Get data from database adapter
            response = requests.get(full_url, params=params, timeout=15)
            
            if response.status_code != 200:
                return f"<h1>Data Error</h1><p>Failed to retrieve data: HTTP {response.status_code}</p>"
            
            # Parse response
            response_data = response.json()
            
            if not response_data.get("success", True):
                return f"<h1>Database Error</h1><p>{response_data.get('message', 'Unknown error')}</p>"
            
            # Extract the actual data
            if isinstance(response_data, dict) and "data" in response_data:
                sensor_data = response_data["data"]
            else:
                sensor_data = response_data
            
            if not sensor_data:
                return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Patient Health Data - User {user_id}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .nav {{ margin-bottom: 20px; }}
            .nav a {{ background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px; }}
            .no-data {{ text-align: center; padding: 40px; background: #f8f9fa; border-radius: 8px; }}
        </style>
    </head>
    <body>
        <div class="nav">
            <a href="/">← Main Menu</a>
            <a href="/patient_overview">Patient Overview</a>
            <a href="/report/{user_id}">JSON Report</a>
        </div>
        <h1>Health Data for Patient {user_id}</h1>
        <div class="no-data">
            <h3>No health data found</h3>
            <p>No data available for the last {hours} hours</p>
            <p><a href="/sensorInfo/{user_id}?hours=168">Try last 7 days</a> | <a href="/sensorInfo/{user_id}?hours=720">Try last 30 days</a></p>
        </div>
    </body>
    </html>
                """
            
            # Sort data by time (newest first)
            sensor_data.sort(key=lambda x: x.get('time', ''), reverse=True)
            
            # Build table rows
            table_rows = ""
            for entry in sensor_data:
                raw_time = entry.get('time')
                try:
                    # Handle different time formats
                    if isinstance(raw_time, str):
                        # Remove timezone and microseconds for parsing
                        clean_time = raw_time.split('+')[0].split('Z')[0].split('.')[0]
                        dt = datetime.fromisoformat(clean_time)
                        formatted_time = dt.strftime('%B %d, %Y %I:%M %p')
                    else:
                        formatted_time = str(raw_time)
                except (ValueError, AttributeError):
                    formatted_time = str(raw_time)
                
                # Get values with proper defaults
                user_id_val = entry.get('user_id', entry.get('UserId', user_id))
                full_name = entry.get('full_name', entry.get('full_name', 'Unknown'))
                field = entry.get('field', 'N/A')
                value = entry.get('value', 'N/A')
                
                # Add status styling based on field and value
                row_class = ""
                if field == 'state':
                    if value == 'dangerous':
                        row_class = "style='background-color: #ffebee; color: #c62828;'"
                    elif value == 'risky':
                        row_class = "style='background-color: #fff3e0; color: #ef6c00;'"
                    elif value == 'normal':
                        row_class = "style='background-color: #e8f5e8; color: #2e7d32;'"
                
                table_rows += f"""
                <tr {row_class}>
                    <td>{formatted_time}</td>
                    <td>{user_id_val}</td>
                    <td>{full_name}</td>
                    <td>{field}</td>
                    <td>{value}</td>
                </tr>
                """
            
            # Get user info for better display
            try:
                user_response = requests.get(f"http://catalog:5001/users/{user_id}", timeout=5)
                if user_response.status_code == 200:
                    user_info = user_response.json()
                    user_name = user_info.get('full_name', f'User {user_id}')
                    doctor_info = ""
                    if user_info.get('doctor_id'):
                        doctor_response = requests.get(f"http://catalog:5001/users/{user_info['doctor_id']}", timeout=5)
                        if doctor_response.status_code == 200:
                            doctor = doctor_response.json()
                            doctor_info = f"<p><strong>Assigned Doctor:</strong> {doctor.get('full_name', 'Unknown')} ({doctor.get('specialization', 'N/A')})</p>"
                else:
                    user_name = f'User {user_id}'
                    doctor_info = ""
            except:
                user_name = f'User {user_id}'
                doctor_info = ""
            
            # Time range selector
            time_options = ""
            current_hours = int(hours)
            for h, label in [(6, "6 hours"), (24, "24 hours"), (168, "7 days"), (720, "30 days")]:
                selected = "selected" if h == current_hours else ""
                time_options += f'<option value="{h}" {selected}>{label}</option>'
            
            return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Patient Health Data - {user_name}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
            th {{ background-color: #f2f2f2; }}
            .nav {{ margin-bottom: 20px; }}
            .nav a {{ background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-right: 10px; }}
            .info-card {{ background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
            .time-filter {{ margin-bottom: 20px; padding: 15px; background: #e3f2fd; border-radius: 8px; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; margin-bottom: 20px; }}
            .stat {{ text-align: center; padding: 10px; background: white; border-radius: 5px; border: 1px solid #ddd; }}
        </style>
        <script>
            function changeTimeRange() {{
                const select = document.getElementById('timeRange');
                const hours = select.value;
                window.location.href = `/sensorInfo/{user_id}?hours=${{hours}}`;
            }}
        </script>
    </head>
    <body>
        <div class="nav">
            <a href="/">← Main Menu</a>
            <a href="/patient_overview">Patient Overview</a>
            <a href="/report/{user_id}">JSON Report</a>
        </div>
        
        <div class="info-card">
            <h1>Health Data for {user_name}</h1>
            <p><strong>Patient ID:</strong> {user_id}</p>
            {doctor_info}
            <p><strong>Data Records:</strong> {len(sensor_data)} readings in the last {hours} hours</p>
        </div>
        
        <div class="time-filter">
            <label for="timeRange"><strong>Time Range:</strong></label>
            <select id="timeRange" onchange="changeTimeRange()">
                {time_options}
            </select>
        </div>
        
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
        
        <div style="text-align: center; margin-top: 20px; color: #666;">
            <p>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </body>
    </html>
            """
            
        except Exception as e:
            logger.error(f"Error in sensorInfo: {e}")
            import traceback
            traceback.print_exc()
            return f"""
    <h1>Error loading patient data</h1>
    <p>{str(e)}</p>
    <p><a href="/">← Back to Main Menu</a></p>
            """

    @cherrypy.expose
    def report(self, user_id, hours=24):
        """Get user health data as JSON through database adapter"""
        cherrypy.response.headers['Content-Type'] = 'application/json'
        
        try:
            # Get database adapter service info from catalog
            adapter_service = requests.get("http://catalog:5001/services/databaseAdapter", timeout=10)
            if adapter_service.status_code != 200:
                return json.dumps({
                    "success": False,
                    "error": "Could not reach database adapter service",
                    "data": []
                }).encode('utf-8')
            
            adapter_info = adapter_service.json()
            adapter_url = adapter_info["url"]
            adapter_port = adapter_info.get("port")
            
            # Build the URL for database adapter
            if adapter_port:
                full_url = f"{adapter_url}:{adapter_port}/read/{user_id}"
            else:
                full_url = f"{adapter_url}/read/{user_id}"
            
            # Add time filtering parameter
            params = {"hours": hours}
            
            # Get data from database adapter
            response = requests.get(full_url, params=params, timeout=15)
            
            if response.status_code != 200:
                return json.dumps({
                    "success": False,
                    "error": f"Database adapter returned HTTP {response.status_code}",
                    "data": []
                }).encode('utf-8')
            
            # Parse response
            response_data = response.json()
            
            if not response_data.get("success", True):
                return json.dumps({
                    "success": False,
                    "error": response_data.get('message', 'Database adapter error'),
                    "data": []
                }).encode('utf-8')
            
            # Extract the actual data
            if isinstance(response_data, dict) and "data" in response_data:
                sensor_data = response_data["data"]
            else:
                sensor_data = response_data
            
            # Ensure we have a list
            if not isinstance(sensor_data, list):
                sensor_data = []
            
            # Sort data by time (newest first)
            sensor_data.sort(key=lambda x: x.get('time', ''), reverse=True)
            
            # Return structured JSON response
            return json.dumps({
                "success": True,
                "user_id": user_id,
                "hours": hours,
                "count": len(sensor_data),
                "timestamp": datetime.now().isoformat(),
                "data": sensor_data
            }).encode('utf-8')
            
        except Exception as e:
            logger.error(f"Error in report: {e}")
            import traceback
            traceback.print_exc()
            return json.dumps({
                "success": False,
                "error": str(e),
                "data": []
            }).encode('utf-8')

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