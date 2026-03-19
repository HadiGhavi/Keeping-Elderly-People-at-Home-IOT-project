import os
import json
import cherrypy
import threading
from datetime import datetime

class HumanHealthCatalog:
    exposed = True  # Required for MethodDispatcher

    def __init__(self, json_file='resource_catalog.json'):
        self.json_file = json_file
        # CRITICAL: RLock allows the same thread to acquire the lock multiple times 
        # (useful for nested helper calls) but blocks other threads.
        self.lock = threading.RLock() 

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
        # Must be called inside a lock
        try:
            with open(self.json_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "project_name": "Human Health",
                "device_types": ["temp", "heart_rate", "oxygen"],
                "devices": [], "users": [], "services": []
            }
    
    def _write_data(self, data):
        # Must be called inside a lock
        with open(self.json_file, 'w') as f:
            json.dump(data, f, indent=4)

    # -------------------------------------------------------
    # HTTP VERB HANDLERS (MethodDispatcher Structure)
    # -------------------------------------------------------

    def GET(self, *uri, **params):
        
        # Handle Root (GET /)
        if not uri:
            return json.dumps({
                "message": "Human Health API (MethodDispatcher)",
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

        command = uri[0]

        with self.lock:  # Lock entire GET transaction
            if command == 'project':
                data = self._read_data()
                return json.dumps({
                    "project_name": data.get("project_name", ""),
                    "project_owner": data.get("project_owner", [])
                }).encode('utf-8')

            elif command == 'services':
                name = uri[1] if len(uri) > 1 else None
                if name:
                    return json.dumps(self._find_service_by_name(name)).encode('utf-8')
                return json.dumps(self._read_data().get("services", [])).encode('utf-8')

            elif command == 'device_types':
                return json.dumps(self._read_data().get("device_types", [])).encode('utf-8')

            elif command == 'devices':
                dev_id = uri[1] if len(uri) > 1 else None
                if dev_id:
                    return json.dumps(self._get_device(dev_id)).encode('utf-8')
                return json.dumps(self._read_data().get("devices", [])).encode('utf-8')

            elif command == 'users':
                chat_id = uri[1] if len(uri) > 1 else None
                if chat_id:
                    return json.dumps(self._get_user(chat_id)).encode('utf-8')
                return json.dumps(self._get_all_users()).encode('utf-8')

            elif command == 'user_devices':
                chat_id = uri[1] if len(uri) > 1 else None
                if not chat_id:
                    raise cherrypy.HTTPError(400, "User chat ID required")
                return json.dumps(self._get_user_devices(chat_id)).encode('utf-8')

            elif command == 'doctors':
                doc_id = uri[1] if len(uri) > 1 else None
                if doc_id:
                    return json.dumps(self._get_doctor_patients(doc_id)).encode('utf-8')
                return json.dumps(self._get_all_doctors()).encode('utf-8')

        raise cherrypy.HTTPError(404, "Endpoint not found")

    def POST(self, *uri, **params):
        if not uri:
            raise cherrypy.HTTPError(400, "Command missing")
        
        command = uri[0]
        
        # Read body once
        try:
            body_data = json.loads(cherrypy.request.body.read().decode('utf-8'))
        except:
            raise cherrypy.HTTPError(400, "Invalid JSON body")

        with self.lock:  # Lock entire POST transaction
            if command == 'services':
                return json.dumps(self._add_service(body_data)).encode('utf-8')
            
            elif command == 'devices':
                return json.dumps(self._register_device(body_data)).encode('utf-8')
            
            elif command == 'users':
                return json.dumps(self._create_user(body_data)).encode('utf-8')
            
            elif command == 'user_devices':
                # POST /user_devices/<chat_id>
                chat_id = uri[1] if len(uri) > 1 else None
                if not chat_id:
                    raise cherrypy.HTTPError(400, "User chat ID required in URL")
                
                device_id = body_data.get('device_id')
                if not device_id:
                    raise cherrypy.HTTPError(400, "device_id required in body")
                
                return json.dumps(self._assign_device_to_user(chat_id, device_id)).encode('utf-8')
            
            elif command == 'doctors':
                return json.dumps(self._register_doctor(body_data)).encode('utf-8')
            
            elif command == 'assign_patient':
                return json.dumps(self._assign_patient_to_doctor(
                    body_data.get('patient_id'), 
                    body_data.get('doctor_id')
                )).encode('utf-8')

        raise cherrypy.HTTPError(404, "Endpoint not found")

    def PUT(self, *uri, **params):
        if not uri:
            raise cherrypy.HTTPError(400, "Command missing")

        command = uri[0]
        
        try:
            update_data = json.loads(cherrypy.request.body.read().decode('utf-8'))
        except:
            raise cherrypy.HTTPError(400, "Invalid JSON body")

        with self.lock:
            if command == 'project':
                data = self._read_data()
                if "project_name" in update_data:
                    data["project_name"] = update_data["project_name"]
                if "project_owner" in update_data:
                    data["project_owner"] = update_data["project_owner"]
                self._write_data(data)
                return json.dumps({"message": "Project updated"}).encode('utf-8')
            
            elif command == 'devices':
                dev_id = uri[1] if len(uri) > 1 else None
                if not dev_id:
                    raise cherrypy.HTTPError(400, "Device ID required")
                return json.dumps(self._update_device(dev_id, update_data)).encode('utf-8')

            elif command == 'users':
                chat_id = uri[1] if len(uri) > 1 else None
                if not chat_id:
                    raise cherrypy.HTTPError(400, "User chat ID required")
                return json.dumps(self._update_user(chat_id, update_data)).encode('utf-8')

        raise cherrypy.HTTPError(404, "Endpoint not found")

    def DELETE(self, *uri, **params):
        if not uri:
            raise cherrypy.HTTPError(400, "Command missing")
        
        command = uri[0]

        with self.lock:
            if command == 'devices':
                dev_id = uri[1] if len(uri) > 1 else None
                if not dev_id:
                    raise cherrypy.HTTPError(400, "Device ID required")
                return json.dumps(self._delete_device(dev_id)).encode('utf-8')

            elif command == 'users':
                chat_id = uri[1] if len(uri) > 1 else None
                if not chat_id:
                    raise cherrypy.HTTPError(400, "User chat ID required")
                return json.dumps(self._delete_user(chat_id)).encode('utf-8')

            elif command == 'user_devices':
                # DELETE /user_devices/<chat_id>/<device_id>
                chat_id = uri[1] if len(uri) > 1 else None
                dev_id = uri[2] if len(uri) > 2 else None
                
                if not chat_id or not dev_id:
                    raise cherrypy.HTTPError(400, "User ID and Device ID required")
                return json.dumps(self._remove_device_from_user(chat_id, dev_id)).encode('utf-8')

        raise cherrypy.HTTPError(404, "Endpoint not found")

    # -------------------------------------------------------
    # HELPER METHODS (Must be called inside a lock)
    # -------------------------------------------------------
  
    def _find_service_by_name(self, servicename):
        data = self._read_data()
        for service in data.get("services", []):
            if service.get("name") == servicename:
                return service
        raise cherrypy.HTTPError(404, f"Service '{servicename}' not found")
     
    def _add_service(self, service_data):
        if not isinstance(service_data, dict):
            raise cherrypy.HTTPError(400, "Service data must be an object")
        
        config = self._read_data()
        if 'services' not in config:
            config['services'] = []
        for service in config['services']:
            if service.get('name') == service_data['name']:
                # Update existing if needed, or raise error. Let's update.
                service.update(service_data)
                self._write_data(config)
                return {"message": "Service updated", "service": service_data}
        
        config['services'].append(service_data)
        self._write_data(config)
        return {"message": "Service added", "service": service_data}
    
    def _get_device(self, device_id):
        data = self._read_data()
        for device in data.get('devices', []):
            if str(device['id']) == str(device_id):
                return device
        raise cherrypy.HTTPError(404, "Device not found")
    
    def _register_device(self, device_data):
        required = ['id', 'type']
        if not all(k in device_data for k in required):
            raise cherrypy.HTTPError(400, "Missing id or type")
        
        data = self._read_data()
        if device_data['type'] not in data.get('device_types', []):
            raise cherrypy.HTTPError(400, "Invalid device type")
        
        for device in data.get('devices', []):
            if str(device['id']) == str(device_data['id']):
                raise cherrypy.HTTPError(400, "Device ID exists")
        
        new_device = {
            "id": device_data['id'],
            "type": device_data['type'],
            "last_update": datetime.utcnow().isoformat() + 'Z'
        }
        data['devices'].append(new_device)
        self._write_data(data)
        return new_device
    
    def _update_device(self, device_id, update_data):
        data = self._read_data()
        for device in data.get('devices', []):
            if str(device['id']) == str(device_id):
                if 'last_update' in update_data:
                    device['last_update'] = update_data['last_update']
                else:
                    device['last_update'] = datetime.utcnow().isoformat() + 'Z'
                self._write_data(data)
                return device
        raise cherrypy.HTTPError(404, "Device not found")
    
    def _delete_device(self, device_id):
        data = self._read_data()
        initial_len = len(data.get('devices', []))
        data['devices'] = [d for d in data.get('devices', []) if str(d['id']) != str(device_id)]
        
        if len(data['devices']) == initial_len:
            raise cherrypy.HTTPError(404, "Device not found")
            
        # Clean up user assignments
        for user in data.get('users', []):
            if 'devices' in user:
                user['devices'] = [d for d in user['devices'] if str(d) != str(device_id)]
        
        self._write_data(data)
        return {"message": "Device deleted"}
     
    def _get_all_users(self):
        return self._read_data()['users']
    
    def _get_user(self, user_chat_id):
        data = self._read_data()
        for user in data['users']:
            if str(user['user_chat_id']) == str(user_chat_id):
                return user
        raise cherrypy.HTTPError(404, "User not found")
    
    def _create_user(self, user_data):
        required = ['user_chat_id', 'full_name']
        if not all(k in user_data for k in required):
            raise cherrypy.HTTPError(400, "Missing user_chat_id or full_name")
        
        data = self._read_data()
        chat_id = user_data['user_chat_id']
        
        # Check duplicate
        for user in data['users']:
            if str(user['user_chat_id']) == str(chat_id):
                raise cherrypy.HTTPError(400, "User already exists")
        
        new_user = {
            "user_chat_id": chat_id,
            "full_name": user_data['full_name'],
            "devices": [],
            "doctor_id": None,
            "user_type": "patient"
        }
        data['users'].append(new_user)
        self._write_data(data)
        return new_user

    def _update_user(self, user_chat_id, update_data):
        data = self._read_data()
        updated = False
        for user in data['users']:
            if str(user['user_chat_id']) == str(user_chat_id):
                if 'full_name' in update_data:
                    user['full_name'] = update_data['full_name']
                updated = True
                break
        
        if not updated:
            raise cherrypy.HTTPError(404, "User not found")
        self._write_data(data)
        return self._get_user(user_chat_id)
    
    def _delete_user(self, user_chat_id):
        data = self._read_data()
        initial_len = len(data['users'])
        data['users'] = [u for u in data['users'] if str(u['user_chat_id']) != str(user_chat_id)]
        
        if len(data['users']) == initial_len:
            raise cherrypy.HTTPError(404, "User not found")
        self._write_data(data)
        return {"message": "User deleted"}
    
    def _get_user_devices(self, user_chat_id):
        user = self._get_user(user_chat_id)
        device_ids = user.get('devices', [])
        data = self._read_data()
        
        user_devices = []
        for did in device_ids:
            for d in data.get('devices', []):
                if str(d['id']) == str(did):
                    user_devices.append(d)
        return user_devices
    
    def _assign_device_to_user(self, user_chat_id, device_id):
        data = self._read_data()
        
        # Check device existence
        if not any(str(d['id']) == str(device_id) for d in data.get('devices', [])):
            raise cherrypy.HTTPError(404, "Device not found")
            
        for user in data.get('users', []):
            if str(user['user_chat_id']) == str(user_chat_id):
                if 'devices' not in user: user['devices'] = []
                
                if any(str(d) == str(device_id) for d in user['devices']):
                    raise cherrypy.HTTPError(400, "Already assigned")
                
                user['devices'].append(device_id)
                self._write_data(data)
                return {"message": "Assigned"}
        
        raise cherrypy.HTTPError(404, "User not found")
    
    def _remove_device_from_user(self, user_chat_id, device_id):
        data = self._read_data()
        for user in data.get('users', []):
            if str(user['user_chat_id']) == str(user_chat_id):
                if 'devices' not in user:
                    raise cherrypy.HTTPError(404, "No devices assigned")
                
                orig_len = len(user['devices'])
                user['devices'] = [d for d in user['devices'] if str(d) != str(device_id)]
                
                if len(user['devices']) == orig_len:
                    raise cherrypy.HTTPError(404, "Device not assigned to user")
                    
                self._write_data(data)
                return {"message": "Removed"}
        raise cherrypy.HTTPError(404, "User not found")

    def _register_doctor(self, doctor_data):
        required = ['user_chat_id', 'full_name', 'specialization']
        if not all(k in doctor_data for k in required):
            raise cherrypy.HTTPError(400, "Missing fields")
            
        data = self._read_data()
        did = doctor_data['user_chat_id']
        
        for user in data['users']:
            if str(user['user_chat_id']) == str(did):
                if user.get('user_type') == 'doctor':
                    raise cherrypy.HTTPError(400, "Doctor already registered")
                else:
                    user['user_type'] = 'doctor'
                    user['specialization'] = doctor_data['specialization']
                    user['hospital'] = doctor_data.get('hospital', '')
                    user['patients'] = []
                    user.pop('devices', None)
                    user.pop('doctor_id', None)
                    self._write_data(data)
                    return user
        
        new_doc = {
            "user_chat_id": did,
            "full_name": doctor_data['full_name'],
            "user_type": "doctor",
            "specialization": doctor_data['specialization'],
            "hospital": doctor_data.get('hospital', ''),
            "patients": []
        }
        data['users'].append(new_doc)
        self._write_data(data)
        return new_doc

    def _get_all_doctors(self):
        return [u for u in self._read_data()['users'] if u.get('user_type') == 'doctor']

    def _get_doctor_patients(self, doctor_id):
        data = self._read_data()
        doc = next((u for u in data['users'] if str(u['user_chat_id']) == str(doctor_id) and u.get('user_type') == 'doctor'), None)
        if not doc: return []
        
        pids = [str(p) for p in doc.get('patients', [])]
        return [u for u in data['users'] if str(u['user_chat_id']) in pids]

    def _assign_patient_to_doctor(self, patient_id, doctor_id):
        data = self._read_data()
        
        doc = next((u for u in data['users'] if str(u['user_chat_id']) == str(doctor_id) and u.get('user_type') == 'doctor'), None)
        if not doc: raise cherrypy.HTTPError(404, "Doctor not found")
        
        pat_found = False
        for user in data['users']:
            if str(user['user_chat_id']) == str(patient_id) and user.get('user_type') != 'doctor':
                # Remove from old doctor
                old_id = user.get('doctor_id')
                if old_id:
                    old_doc = next((d for d in data['users'] if str(d['user_chat_id']) == str(old_id)), None)
                    if old_doc and 'patients' in old_doc:
                        old_doc['patients'] = [p for p in old_doc['patients'] if str(p) != str(patient_id)]
                
                user['doctor_id'] = doctor_id
                if 'patients' not in doc: doc['patients'] = []
                if not any(str(p) == str(patient_id) for p in doc['patients']):
                    doc['patients'].append(patient_id)
                
                pat_found = True
                break
        
        if not pat_found: raise cherrypy.HTTPError(404, "Patient not found")
        
        self._write_data(data)
        return {"message": "Assigned"}

if __name__ == '__main__':
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 5001
    })
 
    # Use MethodDispatcher to map GET/POST/PUT/DELETE methods
    conf = {
        '/': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.response_headers.on': True,
            'tools.response_headers.headers': [('Content-Type', 'application/json')]
        }
    }
    
    cherrypy.quickstart(HumanHealthCatalog(), '/', conf)