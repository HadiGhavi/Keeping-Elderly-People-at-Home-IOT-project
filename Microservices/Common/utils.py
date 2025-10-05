"""
Service Discovery Utilities
Shared module for discovering microservices from the catalog
"""

import requests
from typing import Optional, Dict
from Microservices.Common.config import Config


def get_service_url_from_catalog(service_name: str, 
                                   catalog_url: str = None, 
                                   fallback: str = None) -> str:
    """
    Get service URL from catalog with fallback
    
    Args:
        service_name: Name of service to discover (e.g., "databaseAdapter")
        catalog_url: Catalog service URL (defaults to Config value)
        fallback: Fallback URL if discovery fails
        
    Returns:
        Service URL string (e.g., "http://database_adapter:3000")
        
    Raises:
        ValueError: If service not found and no fallback provided
    """
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


def get_service_info_from_catalog(service_name: str, 
                                    catalog_url: str = None) -> Optional[Dict]:
    """
    Get full service info from catalog (returns the whole service object)
    
    Args:
        service_name: Name of service to discover
        catalog_url: Catalog service URL (defaults to Config value)
        
    Returns:
        dict with url, port, endpoints, topics, etc. or None if not found
    """
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


def register_service_with_catalog(service_name: str,
                                    url: str,
                                    port: int,
                                    endpoints: Dict = None,
                                    catalog_url: str = None) -> bool:
    """
    Register this service with the catalog
    
    Args:
        service_name: Name of this service
        url: URL where this service is accessible
        port: Port this service runs on
        endpoints: Dictionary of endpoints this service provides
        catalog_url: Catalog service URL
        
    Returns:
        True if registration successful, False otherwise
    """
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
    """
    Service registry class that caches discovered services
    """
    
    def __init__(self, catalog_url: str = None):
        self.catalog_url = catalog_url or Config.SERVICES["catalog_url"]
        self._cache = {}
    
    def get_service_url(self, service_name: str, fallback: str = None) -> str:
        """Get service URL with caching"""
        if service_name not in self._cache:
            self._cache[service_name] = get_service_url_from_catalog(
                service_name,
                self.catalog_url,
                fallback
            )
        return self._cache[service_name]
    
    def get_service_info(self, service_name: str) -> Optional[Dict]:
        """Get full service info with caching"""
        cache_key = f"{service_name}_info"
        if cache_key not in self._cache:
            self._cache[cache_key] = get_service_info_from_catalog(
                service_name,
                self.catalog_url
            )
        return self._cache[cache_key]
    
    def clear_cache(self):
        """Clear the service cache (useful for testing or if services change)"""
        self._cache = {}
    
    def refresh_service(self, service_name: str):
        """Refresh a specific service in the cache"""
        if service_name in self._cache:
            del self._cache[service_name]
        cache_key = f"{service_name}_info"
        if cache_key in self._cache:
            del self._cache[cache_key]