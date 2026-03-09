import requests
from typing import Optional, Dict
from Microservices.Common.config import Config


def get_service_url_from_catalog(service_name,catalog_url = None,fallback = None):
    
    if catalog_url is None:
        catalog_url = Config.SERVICES["catalog_url"]
    
    # Check if discovery is enabled
    if not Config.SERVICES.get("enable_discovery", True):
        if fallback:
            print(f"Service discovery disabled, using fallback for {service_name}")
            return fallback
        elif service_name in Config.SERVICES.get("fallbacks", {}):
            return Config.SERVICES["fallbacks"][service_name]
        else:
            raise ValueError(f"Discovery disabled and no fallback for {service_name}")
    
    try:
        timeout = Config.SERVICES.get("discovery_timeout", 5)
        response = requests.get(
            f"{catalog_url}/services/{service_name}", 
            timeout=timeout
        )
        
        if response.status_code == 200:
            info = response.json()
            url = f"{info['url']}:{info['port']}"
            print(f"Discovered {service_name} at: {url}")
            return url
        else:
            print(f"Service {service_name} not found (HTTP {response.status_code})")
            
    except requests.exceptions.Timeout:
        print(f"Timeout discovering {service_name} from catalog")
    except requests.exceptions.ConnectionError:
        print(f"Cannot connect to catalog at {catalog_url}")
    except Exception as e:
        print(f"Failed to discover {service_name}: {e}")
    
    # Use fallback
    if fallback:
        print(f"Using fallback URL for {service_name}: {fallback}")
        return fallback
    elif service_name in Config.SERVICES.get("fallbacks", {}):
        fallback = Config.SERVICES["fallbacks"][service_name]
        print(f"Using config fallback for {service_name}: {fallback}")
        return fallback
    
    raise ValueError(f"Could not discover '{service_name}' and no fallback provided")


def get_service_info_from_catalog(service_name, catalog_url ):
   
    if catalog_url is None:
        catalog_url = Config.SERVICES["catalog_url"]
    
    try:
        timeout = Config.SERVICES.get("discovery_timeout", 5)
        response = requests.get(
            f"{catalog_url}/services/{service_name}", 
            timeout=timeout
        )
        
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Failed to get service info for {service_name}: {e}")
    
    return None


def register_service_with_catalog(service_name,url,port,endpoints,catalog_url = None):
    if catalog_url is None:
        catalog_url = Config.SERVICES["catalog_url"]
    
    service_data = {
        "name": service_name,
        "url": url,
        "port": port
    }
    
    if endpoints:
        service_data["endpoints"] = endpoints
    
    try:
        response = requests.post(
            f"{catalog_url}/services/",
            json=service_data,
            timeout=5
        )
        
        if response.status_code == 201:
            print(f"Successfully registered {service_name} with catalog")
            return True
        else:
            print(f"Registration failed: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"Could not register with catalog: {e}")
        return False


class ServiceRegistry:
    """ Service registry class that caches discovered services"""
    
    def __init__(self, catalog_url = None):
        self.catalog_url = catalog_url or Config.SERVICES["catalog_url"]
        self._cache = {}
    
    def get_service_url(self, service_name, fallback = None):
        if service_name not in self._cache:
            self._cache[service_name] = get_service_url_from_catalog(
                service_name,
                self.catalog_url,
                fallback
            )
        return self._cache[service_name]
    
    def get_service_info(self, service_name) :
        cache_key = f"{service_name}_info"
        if cache_key not in self._cache:
            self._cache[cache_key] = get_service_info_from_catalog(
                service_name,
                self.catalog_url
            )
        return self._cache[cache_key]
    
    def clear_cache(self):
        self._cache = {}
    
    def refresh_service(self, service_name):
        if service_name in self._cache:
            del self._cache[service_name]
        cache_key = f"{service_name}_info"
        if cache_key in self._cache:
            del self._cache[cache_key]