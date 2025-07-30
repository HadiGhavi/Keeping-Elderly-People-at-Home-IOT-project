import os
import json
import cherrypy

class HumanHealthCatalog:
    def __init__(self, json_file='resource_catalog.json'):
        self.json_file = json_file
        if not os.path.exists(json_file):
            with open(json_file, 'w') as f:
                json.dump({
                    "project_name": "Human Health",
                    "project_owner": ["Hadi"],
                    "users": []
                }, f, indent=4)
    
    def _read_data(self):
        with open(self.json_file, 'r') as f:
            return json.load(f)
    
    def _write_data(self, data):
        with open(self.json_file, 'w') as f:
            json.dump(data, f, indent=4)
    
    @cherrypy.expose
    def index(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return json.dumps({
            "message": "Human Health API",
            "endpoints": {
                "GET /project": "get project info",
                "PUT /project": "update project info",
                 "GET /services/<service_name>": "get service by name",
                "POST /services/": "add new service",
                "GET /users": "Get all users",
                "GET /users/<user_chat_id>": "Get specific user details",
                "POST /users": "Create a new user entry",
                "PUT /users/<user_chat_id>": "Update a user",
                "DELETE /users/<user_chat_id>": "Delete a user",
                "GET /situations/<user_chat_id>": "Get all sensitive situations for a user",
                "POST /situations/<user_chat_id>": "Add sensitive situation to user:risky-normal-dangerous",
                "DELETE /situations/<user_chat_id>/<situation>": "Remove sensitive situation",
                "GET /sensors/<user_chat_id>": "Get all sensors for a user",
                "GET /sensors/<user_chat_id>/<sensor_id>": "Get specific sensor",
                "POST /sensors/<user_chat_id>": "Add sensor to user",
                "PUT /sensors/<user_chat_id>/<sensor_id>": "Update sensor",
                "DELETE /sensors/<user_chat_id>/<sensor_id>": "Remove sensor"
            }
        }).encode('utf-8')
    
    @cherrypy.expose
    def project(self, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        try:
            if cherrypy.request.method == "GET":
                data = self._read_data()
                return json.dumps({
                    "project_name": data["project_name"],
                    "project_owner": data["project_owner"]
                }).encode('utf-8')
            elif cherrypy.request.method == "PUT":
                try:
                    update_data = json.loads(cherrypy.request.body.read().decode('utf-8'))
                except:
                    raise cherrypy.HTTPError(400, "Invalid JSON data")
                
                data = self._read_data()
                
                if "project_name" in update_data:
                    data["project_name"] = update_data["project_name"]
                if "project_owner" in update_data:
                    data["project_owner"] = update_data["project_owner"]
                
                self._write_data(data)
                return json.dumps({"message": "Project updated successfully"}).encode('utf-8')
        except Exception as e:
            raise cherrypy.HTTPError(500, str(e))
    
    @cherrypy.expose
    def services(self, service_name=None,**params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        try:
            if cherrypy.request.method == "GET":
                if service_name:
                    return json.dumps(self._find_service_by_name(service_name)).encode('utf-8')
            elif cherrypy.request.method == "POST":
                try:
                    service_data = json.loads(cherrypy.request.body.read().decode('utf-8'))
                except:
                    raise cherrypy.HTTPError(400, "Invalid JSON data")
                return json.dumps(self._add_service(service_data)).encode('utf-8')
        except Exception as e:
            raise cherrypy.HTTPError(500, str(e))
    

    @cherrypy.expose
    def users(self, user_chat_id=None, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        try:
            if cherrypy.request.method == "GET":
                if user_chat_id:
                    return json.dumps(self._get_user(int(user_chat_id))).encode('utf-8')
                else:
                    return json.dumps(self._get_all_users()).encode('utf-8')
            elif cherrypy.request.method == "POST":
                try:
                    user_data = json.loads(cherrypy.request.body.read().decode('utf-8'))
                except:
                    raise cherrypy.HTTPError(400, "Invalid JSON data")
                return json.dumps(self._create_user(user_data)).encode('utf-8')
            elif cherrypy.request.method == "PUT":
                if not user_chat_id:
                    raise cherrypy.HTTPError(400, "User chat ID is required")
                try:
                    update_data = json.loads(cherrypy.request.body.read().decode('utf-8'))
                except:
                    raise cherrypy.HTTPError(400, "Invalid JSON data")
                return json.dumps(self._update_user(int(user_chat_id), update_data)).encode('utf-8')
            elif cherrypy.request.method == "DELETE":
                if not user_chat_id:
                    raise cherrypy.HTTPError(400, "User chat ID is required")
                return json.dumps(self._delete_user(int(user_chat_id))).encode('utf-8')
        except Exception as e:
            raise cherrypy.HTTPError(500, str(e))
    
    @cherrypy.expose
    def situations(self, user_chat_id=None, situation=None, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        try:
            if cherrypy.request.method == "GET":
                if not user_chat_id:
                    raise cherrypy.HTTPError(400, "User chat ID is required")
                return json.dumps(self._get_user_situations(int(user_chat_id))).encode('utf-8')
            elif cherrypy.request.method == "POST":
                if not user_chat_id:
                    raise cherrypy.HTTPError(400, "User chat ID is required")
                try:
                    situation_data = json.loads(cherrypy.request.body.read().decode('utf-8'))
                except:
                    raise cherrypy.HTTPError(400, "Invalid JSON data")
                return json.dumps(self._add_situation(int(user_chat_id), situation_data)).encode('utf-8')
            elif cherrypy.request.method == "DELETE":
                if not user_chat_id or not situation:
                    raise cherrypy.HTTPError(400, "User chat ID and situation are required")
                return json.dumps(self._remove_situation(int(user_chat_id), situation)).encode('utf-8')
        except Exception as e:
            raise cherrypy.HTTPError(500, str(e))
    
    @cherrypy.expose
    def sensors(self, user_chat_id=None, sensor_id=None, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        try:
            if cherrypy.request.method == "GET":
                if not user_chat_id:
                    raise cherrypy.HTTPError(400, "User chat ID is required")
                if sensor_id:
                    return json.dumps(self._get_sensor(int(user_chat_id), int(sensor_id))).encode('utf-8')
                else:
                    return json.dumps(self._get_user_sensors(int(user_chat_id))).encode('utf-8')
            elif cherrypy.request.method == "POST":
                if not user_chat_id:
                    raise cherrypy.HTTPError(400, "User chat ID is required")
                try:
                    sensor_data = json.loads(cherrypy.request.body.read().decode('utf-8'))
                except:
                    raise cherrypy.HTTPError(400, "Invalid JSON data")
                return json.dumps(self._add_sensor(int(user_chat_id), sensor_data)).encode('utf-8')
            elif cherrypy.request.method == "PUT":
                if not user_chat_id or not sensor_id:
                    raise cherrypy.HTTPError(400, "User chat ID and sensor ID are required")
                try:
                    update_data = json.loads(cherrypy.request.body.read().decode('utf-8'))
                except:
                    raise cherrypy.HTTPError(400, "Invalid JSON data")
                return json.dumps(self._update_sensor(int(user_chat_id), int(sensor_id), update_data)).encode('utf-8')
            elif cherrypy.request.method == "DELETE":
                if not user_chat_id or not sensor_id:
                    raise cherrypy.HTTPError(400, "User chat ID and sensor ID are required")
                return json.dumps(self._delete_sensor(int(user_chat_id), int(sensor_id))).encode('utf-8')
        except Exception as e:
            raise cherrypy.HTTPError(500, str(e))
    
    # Helper methods
  
    def _find_service_by_name(self, servicename):
        data = self._read_data()
        print(data)
        services = data.get("services",{})
        if servicename in services:
            return services[servicename]
     
    def _add_service(self,service_data):
        print(service_data)
        # Validate we have the service name and basic structure
        if not isinstance(service_data, dict):
            raise cherrypy.HTTPError(400, "Service data must be an object")
        
        config = self._read_data()
        
        # Add each service from the posted data
        for service_name, service_config in service_data.items():
            if service_name in config['services']:
                raise cherrypy.HTTPError(400, f"Service {service_name} already exists")
            
            # Validate required fields
            if 'url' not in service_config or 'port' not in service_config:
                raise cherrypy.HTTPError(400, f"Service {service_name} missing required fields (url, port)")
            
            config['services'][service_name] = service_config
        
        self._write_data(config)
        cherrypy.response.status = 201
        return json.dumps({"message": "Services added successfully", "services": service_data}).encode('utf-8')
     
    def _get_all_users(self):
        data = self._read_data()
        return data['users']
    
    def _get_user(self, user_chat_id):
        data = self._read_data()
        for user in data['users']:
            if user['user_chat_id'] == user_chat_id:
                return user
        raise cherrypy.HTTPError(404, "User not found")
    
    def _create_user(self, user_data):
        required_fields = ['user_chat_id', 'full_name']
        if not all(field in user_data for field in required_fields):
            raise cherrypy.HTTPError(400, "Missing required fields (user_chat_id, full_name)")
        
        data = self._read_data()
        user_chat_id = int(user_data['user_chat_id'])
        
        # Check if user already exists
        for user in data['users']:
            if user['user_chat_id'] == user_chat_id:
                raise cherrypy.HTTPError(400, "User already exists")
        
        new_user = {
            "user_chat_id": user_chat_id,
            "full_name": user_data['full_name'],
            "SensitiveSituation": user_data.get('SensitiveSituation', []),
            "sensors": user_data.get('sensors', [])
        }
        
        data['users'].append(new_user)
        self._write_data(data)
        cherrypy.response.status = 201
        return new_user
    
    def _update_user(self, user_chat_id, update_data):
        data = self._read_data()
        updated = False
        
        for user in data['users']:
            if user['user_chat_id'] == user_chat_id:
                if 'full_name' in update_data:
                    user['full_name'] = update_data['full_name']
                if 'SensitiveSituation' in update_data:
                    user['SensitiveSituation'] = update_data['SensitiveSituation']
                if 'sensors' in update_data:
                    user['sensors'] = update_data['sensors']
                updated = True
                break
        
        if not updated:
            raise cherrypy.HTTPError(404, "User not found")
        
        self._write_data(data)
        return self._get_user(user_chat_id)
    
    def _delete_user(self, user_chat_id):
        data = self._read_data()
        initial_length = len(data['users'])
        
        data['users'] = [user for user in data['users'] if user['user_chat_id'] != user_chat_id]
        
        if len(data['users']) == initial_length:
            raise cherrypy.HTTPError(404, "User not found")
        
        self._write_data(data)
        return {"message": "User deleted successfully"}
    
    def _get_user_situations(self, user_chat_id):
        user = self._get_user(user_chat_id)
        return user['SensitiveSituation']
    
    def _add_situation(self, user_chat_id, situation_data):
        if 'situation' not in situation_data:
            raise cherrypy.HTTPError(400, "Missing 'situation' field")
        
        data = self._read_data()
        for user in data['users']:
            if user['user_chat_id'] == user_chat_id:
                if situation_data['situation'] in user['SensitiveSituation']:
                    raise cherrypy.HTTPError(400, "Situation already exists for this user")
                user['SensitiveSituation'].append(situation_data['situation'])
                break
        
        self._write_data(data)
        cherrypy.response.status = 201
        return {"message": "Situation added successfully"}
    
    def _remove_situation(self, user_chat_id, situation):
        data = self._read_data()
        removed = False
        
        for user in data['users']:
            if user['user_chat_id'] == user_chat_id:
                initial_length = len(user['SensitiveSituation'])
                user['SensitiveSituation'] = [s for s in user['SensitiveSituation'] if s != situation]
                if len(user['SensitiveSituation']) < initial_length:
                    removed = True
                break
        
        if not removed:
            raise cherrypy.HTTPError(404, "Situation not found for this user")
        
        self._write_data(data)
        return {"message": "Situation removed successfully"}
    
    def _get_user_sensors(self, user_chat_id):
        user = self._get_user(user_chat_id)
        return user['sensors']
    
    def _get_sensor(self, user_chat_id, sensor_id):
        sensors = self._get_user_sensors(user_chat_id)
        for sensor in sensors:
            if sensor['id'] == sensor_id:
                return sensor
        raise cherrypy.HTTPError(404, "Sensor not found")
    
    def _add_sensor(self, user_chat_id, sensor_data):
        required_fields = ['id', 'name', 'max_level_alert', 'min_level_alert']
        if not all(field in sensor_data for field in required_fields):
            raise cherrypy.HTTPError(400, "Missing required fields (id, name, max_level_alert, min_level_alert)")
        
        data = self._read_data()
        sensor_id = int(sensor_data['id'])
        
        for user in data['users']:
            if user['user_chat_id'] == user_chat_id:
                # Check if sensor ID already exists for this user
                for sensor in user['sensors']:
                    if sensor['id'] == sensor_id:
                        raise cherrypy.HTTPError(400, "Sensor with this ID already exists for this user")
                
                user['sensors'].append({
                    "id": sensor_id,
                    "name": sensor_data['name'],
                    "max_level_alert": sensor_data['max_level_alert'],
                    "min_level_alert": sensor_data['min_level_alert']
                })
                break
        
        self._write_data(data)
        cherrypy.response.status = 201
        return sensor_data
    
    def _update_sensor(self, user_chat_id, sensor_id, update_data):
        data = self._read_data()
        updated = False
        
        for user in data['users']:
            if user['user_chat_id'] == user_chat_id:
                for sensor in user['sensors']:
                    if sensor['id'] == sensor_id:
                        if 'name' in update_data:
                            sensor['name'] = update_data['name']
                        if 'max_level_alert' in update_data:
                            sensor['max_level_alert'] = update_data['max_level_alert']
                        if 'min_level_alert' in update_data:
                            sensor['min_level_alert'] = update_data['min_level_alert']
                        updated = True
                        break
                break
        
        if not updated:
            raise cherrypy.HTTPError(404, "Sensor not found")
        
        self._write_data(data)
        return self._get_sensor(user_chat_id, sensor_id)
    
    def _delete_sensor(self, user_chat_id, sensor_id):
        data = self._read_data()
        deleted = False
        
        for user in data['users']:
            if user['user_chat_id'] == user_chat_id:
                initial_length = len(user['sensors'])
                user['sensors'] = [sensor for sensor in user['sensors'] if sensor['id'] != sensor_id]
                if len(user['sensors']) < initial_length:
                    deleted = True
                break
        
        if not deleted:
            raise cherrypy.HTTPError(404, "Sensor not found")
        
        self._write_data(data)
        return {"message": "Sensor deleted successfully"}

if __name__ == '__main__':
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 5001,
        'tools.encode.on': True,
        'tools.encode.encoding': 'utf-8'
    })
    
    def cors():
        cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"
        cherrypy.response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        cherrypy.response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    
    cherrypy.tools.cors = cherrypy._cptools.HandlerTool(cors)
    
    conf = {
        '/': {
            'tools.cors.on': True,
            'tools.response_headers.on': True,
            'tools.response_headers.headers': [('Content-Type', 'application/json')]
        }
    }
    
    cherrypy.quickstart(HumanHealthCatalog(), '/', conf)