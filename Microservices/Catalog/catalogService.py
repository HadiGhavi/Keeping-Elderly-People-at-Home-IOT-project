import os
import json
import cherrypy
from datetime import datetime

class HumanHealthCatalog:
    def __init__(self, json_file='resource_catalog.json'):
        self.json_file = json_file
        if not os.path.exists(json_file):
            with open(json_file, 'w') as f:
                json.dump({
                    "project_name": "Human Health",
                    "project_owner": ["Hadi"],
                    "device_types": ["temp", "heart_rate", "oxygen"],
                    "devices": [],
                    "users": [],
                    "services": []
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
                "GET /device_types": "Get available device types (temp, heart_rate, oxygen)",
                "GET /devices": "Get all registered devices",
                "GET /devices/<device_id>": "Get specific device",
                "POST /devices": "Register a new device (requires: id, type)",
                "PUT /devices/<device_id>": "Update device last_update",
                "DELETE /devices/<device_id>": "Delete a device",
                "GET /users": "Get all users",
                "GET /users/<user_chat_id>": "Get specific user details",
                "POST /users": "Create a new user entry",
                "PUT /users/<user_chat_id>": "Update a user",
                "DELETE /users/<user_chat_id>": "Delete a user",
                "GET /user_devices/<user_chat_id>": "Get all devices assigned to user",
                "POST /user_devices/<user_chat_id>": "Assign device to user (requires: device_id)",
                "DELETE /user_devices/<user_chat_id>/<device_id>": "Remove device from user",
                "GET /doctors": "Get all doctors",
                "GET /doctors/<doctor_id>": "Get patients for a specific doctor",
                "POST /doctors": "Register a new doctor",
                "POST /assign_patient": "Assign a patient to a doctor"
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
    def services(self, service_name=None, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        try:
            if cherrypy.request.method == "GET":
                if service_name:
                    return json.dumps(self._find_service_by_name(service_name)).encode('utf-8')
                else:
                    data = self._read_data()
                    return json.dumps(data.get("services", [])).encode('utf-8')
            elif cherrypy.request.method == "POST":
                try:
                    service_data = json.loads(cherrypy.request.body.read().decode('utf-8'))
                except:
                    raise cherrypy.HTTPError(400, "Invalid JSON data")
                return json.dumps(self._add_service(service_data)).encode('utf-8')
        except Exception as e:
            raise cherrypy.HTTPError(500, str(e))
    
    @cherrypy.expose
    def device_types(self, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        try:
            if cherrypy.request.method == "GET":
                data = self._read_data()
                return json.dumps(data.get("device_types", [])).encode('utf-8')
        except Exception as e:
            raise cherrypy.HTTPError(500, str(e))
    
    @cherrypy.expose
    def devices(self, device_id=None, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        try:
            if cherrypy.request.method == "GET":
                if device_id:
                    return json.dumps(self._get_device(device_id)).encode('utf-8')
                else:
                    data = self._read_data()
                    return json.dumps(data.get("devices", [])).encode('utf-8')
            elif cherrypy.request.method == "POST":
                try:
                    device_data = json.loads(cherrypy.request.body.read().decode('utf-8'))
                except:
                    raise cherrypy.HTTPError(400, "Invalid JSON data")
                return json.dumps(self._register_device(device_data)).encode('utf-8')
            elif cherrypy.request.method == "PUT":
                if not device_id:
                    raise cherrypy.HTTPError(400, "Device ID is required")
                try:
                    update_data = json.loads(cherrypy.request.body.read().decode('utf-8'))
                except:
                    raise cherrypy.HTTPError(400, "Invalid JSON data")
                return json.dumps(self._update_device(device_id, update_data)).encode('utf-8')
            elif cherrypy.request.method == "DELETE":
                if not device_id:
                    raise cherrypy.HTTPError(400, "Device ID is required")
                return json.dumps(self._delete_device(device_id)).encode('utf-8')
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
    def user_devices(self, user_chat_id=None, device_id=None, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        try:
            if cherrypy.request.method == "GET":
                if not user_chat_id:
                    raise cherrypy.HTTPError(400, "User chat ID is required")
                return json.dumps(self._get_user_devices(int(user_chat_id))).encode('utf-8')
            elif cherrypy.request.method == "POST":
                if not user_chat_id:
                    raise cherrypy.HTTPError(400, "User chat ID is required")
                try:
                    data = json.loads(cherrypy.request.body.read().decode('utf-8'))
                    device_id = data.get('device_id')
                    if not device_id:
                        raise cherrypy.HTTPError(400, "device_id is required in request body")
                except:
                    raise cherrypy.HTTPError(400, "Invalid JSON data")
                return json.dumps(self._assign_device_to_user(int(user_chat_id), device_id)).encode('utf-8')
            elif cherrypy.request.method == "DELETE":
                if not user_chat_id or not device_id:
                    raise cherrypy.HTTPError(400, "User chat ID and device ID are required")
                return json.dumps(self._remove_device_from_user(int(user_chat_id), device_id)).encode('utf-8')
        except Exception as e:
            raise cherrypy.HTTPError(500, str(e))

    @cherrypy.expose
    def doctors(self, doctor_id=None, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        try:
            if cherrypy.request.method == "GET":
                if doctor_id:
                    return json.dumps(self._get_doctor_patients(int(doctor_id))).encode('utf-8')
                else:
                    return json.dumps(self._get_all_doctors()).encode('utf-8')
            elif cherrypy.request.method == "POST":
                doctor_data = json.loads(cherrypy.request.body.read().decode('utf-8'))
                return json.dumps(self._register_doctor(doctor_data)).encode('utf-8')
        except Exception as e:
            raise cherrypy.HTTPError(500, str(e))

    @cherrypy.expose
    def assign_patient(self, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        try:
            if cherrypy.request.method == "POST":
                assignment_data = json.loads(cherrypy.request.body.read().decode('utf-8'))
                return json.dumps(self._assign_patient_to_doctor(
                    assignment_data['patient_id'], 
                    assignment_data['doctor_id']
                )).encode('utf-8')
        except Exception as e:
            raise cherrypy.HTTPError(500, str(e))
           
    # Helper methods - SERVICE MANAGEMENT
  
    def _find_service_by_name(self, servicename):
        """Find a service by name in the services list"""
        data = self._read_data()
        services = data.get("services", [])
        
        for service in services:
            if service.get("name") == servicename:
                return service
        
        raise cherrypy.HTTPError(404, f"Service '{servicename}' not found")
     
    def _add_service(self, service_data):
        """Add a new service to the services list"""
        if not isinstance(service_data, dict):
            raise cherrypy.HTTPError(400, "Service data must be an object")
        
        required_fields = ['name', 'url', 'port']
        if not all(field in service_data for field in required_fields):
            raise cherrypy.HTTPError(400, f"Missing required fields: {required_fields}")
        
        config = self._read_data()
        
        if 'services' not in config:
            config['services'] = []
        
        for service in config['services']:
            if service.get('name') == service_data['name']:
                raise cherrypy.HTTPError(400, f"Service '{service_data['name']}' already exists")
        
        config['services'].append(service_data)
        
        self._write_data(config)
        cherrypy.response.status = 201
        return {"message": "Service added successfully", "service": service_data}
    
    # Helper methods - DEVICE MANAGEMENT
    
    def _get_device(self, device_id):
        """Get a specific device by ID"""
        data = self._read_data()
        for device in data.get('devices', []):
            if device['id'] == device_id:
                return device
        raise cherrypy.HTTPError(404, "Device not found")
    
    def _register_device(self, device_data):
        """Register a new device in the global devices list"""
        required_fields = ['id', 'type']
        if not all(field in device_data for field in required_fields):
            raise cherrypy.HTTPError(400, "Missing required fields (id, type)")
        
        data = self._read_data()
        
        # Validate device type
        if device_data['type'] not in data.get('device_types', []):
            raise cherrypy.HTTPError(400, f"Invalid device type. Must be one of: {data.get('device_types', [])}")
        
        # Check if device ID already exists
        for device in data.get('devices', []):
            if device['id'] == device_data['id']:
                raise cherrypy.HTTPError(400, "Device ID already exists")
        
        new_device = {
            "id": device_data['id'],
            "type": device_data['type'],
            "last_update": datetime.utcnow().isoformat() + 'Z'
        }
        
        if 'devices' not in data:
            data['devices'] = []
        
        data['devices'].append(new_device)
        self._write_data(data)
        cherrypy.response.status = 201
        return new_device
    
    def _update_device(self, device_id, update_data):
        """Update device information (mainly last_update timestamp)"""
        data = self._read_data()
        
        for device in data.get('devices', []):
            if device['id'] == device_id:
                if 'last_update' in update_data:
                    device['last_update'] = update_data['last_update']
                else:
                    device['last_update'] = datetime.utcnow().isoformat() + 'Z'
                
                self._write_data(data)
                return device
        
        raise cherrypy.HTTPError(404, "Device not found")
    
    def _delete_device(self, device_id):
        """Delete a device from global list and remove from all users"""
        data = self._read_data()
        initial_length = len(data.get('devices', []))
        
        # Remove device from global list
        data['devices'] = [d for d in data.get('devices', []) if d['id'] != device_id]
        
        if len(data.get('devices', [])) == initial_length:
            raise cherrypy.HTTPError(404, "Device not found")
        
        # Remove device from all users
        for user in data.get('users', []):
            if 'devices' in user and device_id in user['devices']:
                user['devices'].remove(device_id)
        
        self._write_data(data)
        return {"message": "Device deleted successfully"}
    
    # Helper methods - USER MANAGEMENT
     
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
            "devices": [],  # Empty device list - user will register their own
            "doctor_id": None,  
            "user_type": "patient"  
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
                if 'devices' in update_data:
                    user['devices'] = update_data['devices']
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
    
    # Helper methods - USER-DEVICE RELATIONSHIP
    
    def _get_user_devices(self, user_chat_id):
        """Get full device objects for all devices assigned to a user"""
        user = self._get_user(user_chat_id)
        device_ids = user.get('devices', [])
        
        data = self._read_data()
        user_devices = []
        
        for device_id in device_ids:
            for device in data.get('devices', []):
                if device['id'] == device_id:
                    user_devices.append(device)
                    break
        
        return user_devices
    
    def _assign_device_to_user(self, user_chat_id, device_id):
        """Assign an existing device to a user"""
        data = self._read_data()
        
        # Check if device exists
        device_exists = any(d['id'] == device_id for d in data.get('devices', []))
        if not device_exists:
            raise cherrypy.HTTPError(404, "Device not found")
        
        # Find user and assign device
        for user in data.get('users', []):
            if user['user_chat_id'] == user_chat_id:
                if 'devices' not in user:
                    user['devices'] = []
                
                if device_id in user['devices']:
                    raise cherrypy.HTTPError(400, "Device already assigned to this user")
                
                user['devices'].append(device_id)
                self._write_data(data)
                return {"message": "Device assigned successfully", "device_id": device_id}
        
        raise cherrypy.HTTPError(404, "User not found")
    
    def _remove_device_from_user(self, user_chat_id, device_id):
        """Remove a device assignment from a user"""
        data = self._read_data()
        
        for user in data.get('users', []):
            if user['user_chat_id'] == user_chat_id:
                if 'devices' not in user or device_id not in user['devices']:
                    raise cherrypy.HTTPError(404, "Device not assigned to this user")
                
                user['devices'].remove(device_id)
                self._write_data(data)
                return {"message": "Device removed from user"}
        
        raise cherrypy.HTTPError(404, "User not found")
    
    # Helper methods - DOCTOR MANAGEMENT
    
    def _register_doctor(self, doctor_data):
        required_fields = ['user_chat_id', 'full_name', 'specialization']
        if not all(field in doctor_data for field in required_fields):
            raise cherrypy.HTTPError(400, "Missing required fields")
        
        data = self._read_data()
        doctor_chat_id = int(doctor_data['user_chat_id'])
        
        # Check if already exists
        for user in data['users']:
            if user['user_chat_id'] == doctor_chat_id:
                if user.get('user_type') == 'doctor':
                    raise cherrypy.HTTPError(400, "Doctor already registered")
                else:
                    # Convert existing patient to doctor
                    user['user_type'] = 'doctor'
                    user['specialization'] = doctor_data['specialization']
                    user['hospital'] = doctor_data.get('hospital', '')
                    # Remove patient-specific fields and add doctor fields
                    user.pop('devices', None)
                    user.pop('doctor_id', None)
                    user['patients'] = []
                    self._write_data(data)
                    return user
        
        # Create new doctor
        new_doctor = {
            "user_chat_id": doctor_chat_id,
            "full_name": doctor_data['full_name'],
            "user_type": "doctor",
            "specialization": doctor_data['specialization'],
            "hospital": doctor_data.get('hospital', ''),
            "patients": []
        }
        
        data['users'].append(new_doctor)
        self._write_data(data)
        cherrypy.response.status = 201
        return new_doctor
    
    def _get_all_doctors(self):
        data = self._read_data()
        doctors = [user for user in data['users'] if user.get('user_type') == 'doctor']
        return doctors

    def _get_doctor_patients(self, doctor_id):
        data = self._read_data()
        
        # Find the doctor
        doctor = None
        for user in data['users']:
            if user['user_chat_id'] == doctor_id and user.get('user_type') == 'doctor':
                doctor = user
                break
        
        if not doctor:
            return []
        
        # Get patient details
        patients = []
        patient_ids = doctor.get('patients', [])
        
        for user in data['users']:
            if user['user_chat_id'] in patient_ids:
                patients.append(user)
        
        return patients

    def _assign_patient_to_doctor(self, patient_id, doctor_id):
        data = self._read_data()
        
        # Verify doctor exists
        doctor = None
        for user in data['users']:
            if user['user_chat_id'] == doctor_id and user.get('user_type') == 'doctor':
                doctor = user
                break
        
        if not doctor:
            raise cherrypy.HTTPError(404, "Doctor not found")
        
        # Find and update patient
        patient_found = False
        for user in data['users']:
            if user['user_chat_id'] == patient_id and user.get('user_type') != 'doctor':
                # Remove from previous doctor's list
                old_doctor_id = user.get('doctor_id')
                if old_doctor_id:
                    for old_doc in data['users']:
                        if (old_doc['user_chat_id'] == old_doctor_id and 
                            old_doc.get('user_type') == 'doctor'):
                            if patient_id in old_doc.get('patients', []):
                                old_doc['patients'].remove(patient_id)
                            break
                
                # Assign to new doctor
                user['doctor_id'] = doctor_id
                
                # Add to doctor's list
                if patient_id not in doctor.get('patients', []):
                    if 'patients' not in doctor:
                        doctor['patients'] = []
                    doctor['patients'].append(patient_id)
                
                patient_found = True
                break
        
        if not patient_found:
            raise cherrypy.HTTPError(404, "Patient not found")
        
        self._write_data(data)
        return {"message": "Patient assigned to doctor successfully"}

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