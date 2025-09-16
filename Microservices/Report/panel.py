import cherrypy
import requests
import json
from datetime import datetime
from itertools import groupby
class AdminPanel:
    @cherrypy.expose
    def index(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        response = requests.post(
        f"http://catalog:5001/services/",
                json={
                    "adminPanel": {
                        "url": "http://admin_panel",
                        "port": 9000,
                        "endpoints": {
                            "GET /sensorInfo/<userid>": "get user sensor data by id => Html view",
                            "GET /report/<userid>": "get user sensor data by id => json"
                        }
                    }
                }
            )
        return json.dumps({
            "message": "Sensor API",
            "endpoints": {
                "GET /sensorInfo/<userid>": "get user sensor data by id html view",
                "GET /report/<userid>": "get user sensor data by id json result",
            }
        }).encode('utf-8')
         
    @cherrypy.expose
    def sensorInfo(self, user_id):
        try:
            # Get data from InfluxDB via your API
            data_service=requests.get("http://catalog:5001/services/dataIngestion")
            json_data=data_service.json()
            response = requests.get(json_data["url"] + ":"+ str(json_data["port"])+"/getUserData/"+user_id)
            sensor_data = json.loads(response.json())
            sensor_data.sort(key=lambda x: x['time'])
            # Generate HTML table rows
            table_rows = ""
            for entry in sensor_data:
                # Format the timestamp
                raw_time = entry.get('time')
                try:
                    clean_time = raw_time.split('+')[0].split('.')[0]  
                    dt = datetime.fromisoformat(clean_time)
                    formatted_time = dt.strftime('%B %d, %Y %I:%M %p')
                except (ValueError, AttributeError):
                    # Fallback if parsing fails
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
    <title>IoT Dashboard</title>
    <style>
        table {{
            border-collapse: collapse;
            width: 100%;
            margin-bottom: 20px;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: center;
        }}
        th {{
            background-color: #f2f2f2;
        }}
        input[type="number"] {{
            width: 80px;
        }}
    </style>
</head>
<body>
    <h1>IoT Dashboard</h1>
    <h2>Sensor Saved Data</h2>
    <table>
        <thead>
            <tr>
                <th>time</th>
                <th>user_id</th>
                <th>full_name</th>
                <th>field</th>
                <th>value</th>
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
            return f"Error: {str(e)}"

    @cherrypy.expose
    def report(self, user_id):
        try:
            # Get data from InfluxDB via your API
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
        return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Doctor Registration - Health Monitoring System</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }
            .form-group { margin-bottom: 15px; }
            label { display: block; margin-bottom: 5px; font-weight: bold; }
            input, select { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
            .btn { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
            .btn:hover { background: #0056b3; }
            .info { background: #f8f9fa; padding: 15px; border-left: 4px solid #007bff; margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <h1>Doctor Registration</h1>
        <div class="info">
            <p>Register as a healthcare provider to monitor your patients' health data through our system.</p>
        </div>
        
        <form method="post" action="/register_doctor_web">
            <div class="form-group">
                <label for="full_name">Full Name:</label>
                <input type="text" id="full_name" name="full_name" required 
                    placeholder="Dr. John Smith">
            </div>
            
            <div class="form-group">
                <label for="chat_id">Telegram Chat ID:</label>
                <input type="number" id="chat_id" name="chat_id" required 
                    placeholder="Get this from @userinfobot on Telegram">
            </div>
            
            <div class="form-group">
                <label for="specialization">Medical Specialization:</label>
                <select id="specialization" name="specialization" required>
                    <option value="">Select Specialization</option>
                    <option value="General Practice">General Practice</option>
                    <option value="Cardiology">Cardiology</option>
                    <option value="Pediatrics">Pediatrics</option>
                    <option value="Geriatrics">Geriatrics</option>
                    <option value="Internal Medicine">Internal Medicine</option>
                    <option value="Emergency Medicine">Emergency Medicine</option>
                    <option value="Other">Other</option>
                </select>
            </div>
            
            <div class="form-group">
                <label for="hospital">Hospital/Clinic (Optional):</label>
                <input type="text" id="hospital" name="hospital" 
                    placeholder="City General Hospital">
            </div>
            
            <button type="submit" class="btn">Register as Doctor</button>
        </form>
        
        <p><strong>Note:</strong> After registration, you'll receive admin privileges to monitor patients who assign you as their doctor.</p>
    </body>
    </html>
        """

    @cherrypy.expose
    def register_doctor_web(self, full_name, chat_id, specialization, hospital=""):
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
    <head><title>Registration Successful</title></head>
    <body style="font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px;">
        <h2 style="color: green;">Registration Successful!</h2>
        <p><strong>Dr. {full_name}</strong> has been registered successfully.</p>
        <p><strong>Specialization:</strong> {specialization}</p>
        <p>You can now:</p>
        <ul>
            <li>Open Telegram and start a conversation with the health monitoring bot</li>
            <li>Use /menu to access your doctor dashboard</li>
            <li>Monitor patients who assign you as their doctor</li>
        </ul>
        <a href="/doctor_registration" style="color: #007bff;">Register Another Doctor</a>
    </body>
    </html>
                """
            else:
                return f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px;">
        <h2 style="color: red;">Registration Failed</h2>
        <p>Error: {response.text}</p>
        <a href="/doctor_registration">Try Again</a>
    </body>
    </html>
                """
        except Exception as e:
            return f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial; max-width: 600px; margin: 50px auto; padding: 20px;">
        <h2 style="color: red;">Error</h2>
        <p>{str(e)}</p>
        <a href="/doctor_registration">Try Again</a>
    </body>
    </html>
            """
        
cherrypy.config.update({
    "server.socket_host": "0.0.0.0",
    "server.socket_port": 9000,
    "tools.response_headers.on": True,
    "tools.response_headers.headers": [("Content-Type", "text/html")]
})
cherrypy.quickstart(AdminPanel())