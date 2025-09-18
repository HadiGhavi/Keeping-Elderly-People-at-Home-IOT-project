from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

class TimeSeriesAdapter(ABC):
    """
    Abstract base class for time-series database adapters.
    This interface makes the platform agnostic of specific database implementations.
    """
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the time-series database.
        Returns True if successful, False otherwise.
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """
        Close connection to the time-series database.
        Returns True if successful, False otherwise.
        """
        pass
    
    @abstractmethod
    def write_data(self, measurement: str, data: Dict[str, Any]) -> tuple[bool, str]:
        """
        Write time-series data to the database.
        
        Args:
            measurement: Name of the measurement/table
            data: Dictionary containing:
                - tags: Dict of tag key-value pairs (indexed fields)
                - fields: Dict of field key-value pairs (data values)
                - timestamp: Optional datetime object
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        pass
    
    @abstractmethod
    def query_data(self, 
                   measurement: str, 
                   filters: Optional[Dict[str, Any]] = None,
                   time_range: Optional[Dict[str, datetime]] = None,
                   fields: Optional[List[str]] = None) -> tuple[bool, Union[List[Dict], str]]:
        """
        Query time-series data from the database.
        
        Args:
            measurement: Name of the measurement/table
            filters: Dictionary of filter conditions (e.g., {"user_id": "123"})
            time_range: Dictionary with 'start' and 'end' datetime objects
            fields: List of specific fields to retrieve
        
        Returns:
            Tuple of (success: bool, data_or_error: Union[List[Dict], str])
        """
        pass
    
    @abstractmethod
    def get_all_users(self) -> tuple[bool, Union[List[Dict], str]]:
        """
        Get all users who have data in the system.
        
        Returns:
            Tuple of (success: bool, data_or_error: Union[List[Dict], str])
            Where data is list of dicts with user info like:
            [{"user_id": "123", "full_name": "John Doe", "record_count": 45, "last_activity": "2024-01-01T10:00:00Z"}]
        """
        pass

    @abstractmethod
    def get_user_data(self, user_id: str, 
                     time_range: Optional[Dict[str, datetime]] = None) -> tuple[bool, Union[List[Dict], str]]:
        """
        Get all sensor data for a specific user.
        
        Args:
            user_id: User identifier
            time_range: Optional time range filter
            
        Returns:
            Tuple of (success: bool, data_or_error: Union[List[Dict], str])
        """
        pass
    
    @abstractmethod
    def delete_user_data(self, user_id: str) -> tuple[bool, str]:
        """
        Delete all data for a specific user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        pass
    
    @abstractmethod
    def get_database_info(self) -> Dict[str, Any]:
        """
        Get information about the database connection and status.
        
        Returns:
            Dictionary with database information
        """
        pass