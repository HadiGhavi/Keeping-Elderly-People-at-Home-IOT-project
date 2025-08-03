import cherrypy
import requests
import json
from itertools import groupby
class AdminPanel:
    @cherrypy.expose
    def index(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        response = requests.post(
        f"http://localhost:5000/services/",
                json={
                    "adminPanel": {
                        "url": "http://localhost",
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
            data_service=requests.get("http://localhost:5000/services/dataIngestion")
            json_data=data_service.json()
            response = requests.get(json_data["url"] + ":"+ str(json_data["port"])+"/getUserData/"+user_id)
            sensor_data = json.loads(response.json())
            sensor_data.sort(key=lambda x: x['time'])
            # Generate HTML table rows
            table_rows = ""
            for entry in sensor_data:
                table_rows += f"""
                <tr>
                    <td>{entry.get('time')}</td>
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
            data_service=requests.get("http://localhost:5000/services/dataIngestion")
            json_data=data_service.json()
            response = requests.get(json_data["url"] + ":"+ str(json_data["port"])+"/getUserData/"+user_id)
            sensor_data = json.loads(response.json())
            sensor_data.sort(key=lambda x: x['time'])
            return json.dumps(sensor_data).encode('utf-8')
        except Exception as e:
            return f"Error: {str(e)}"
        
cherrypy.config.update({
    "server.socket_host": "0.0.0.0",
    "server.socket_port": 9000,
    "tools.response_headers.on": True,
    "tools.response_headers.headers": [("Content-Type", "text/html")]
})
cherrypy.quickstart(AdminPanel())