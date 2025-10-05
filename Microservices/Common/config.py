import os
from pathlib import Path

class Config:
    BASE_DIR = Path(os.getenv("BASE_DIR", "/app/ClassificationAlgorithm"))
    CLASSIFICATION = {
        "TRAINMODEL": str(BASE_DIR / "trained_model.pkl"),
        "SAMPLEPATH": str(BASE_DIR / "elderly_health_data.csv"),
    }
    
    DATABASE = {
        "active_adapter": os.getenv("DATABASE_ADAPTER", "influxdb"),
        "adapters": {
            "influxdb": {
                "host": os.getenv("INFLUXDB_HOST", "https://eu-central-1-1.aws.cloud2.influxdata.com"),
                "token": os.getenv("INFLUXDB_TOKEN", "WaCTN7nEqIMjNSsl-Yzry1iz6Os2F4xskPWrdrA5JQe49JmxT0MiUtOgvAHtz94cTkVolVrcplxYXfaYxqPf-g=="),
                "org": os.getenv("INFLUXDB_ORG", "Dev Team"),
                "bucket": os.getenv("INFLUXDB_BUCKET", "iot_health")
            }
        }
    }
    SERVICES = {
        "catalog_url": os.getenv("CATALOG_URL", "http://catalog:5001"),
        "enable_discovery": os.getenv("ENABLE_SERVICE_DISCOVERY", "true").lower() == "true",
        "discovery_timeout": int(os.getenv("SERVICE_DISCOVERY_TIMEOUT", "5")),
        
        # Fallback URLs if catalog is unavailable
        "fallbacks": {
            "catalog": "http://catalog:5001",
            "databaseAdapter": "http://database_adapter:3000",
            "notification": "http://notification:1500",
            "mqtt": "broker.hivemq.com:1883",
            "sensor": "http://monitor:3500",
            "adminPanel": "http://admin_panel:9000"
        }
    }

    TELEGRAM_TOKEN = "6605276431:AAHoPhbbqSSPR7z1VS56c7Cddp34xzvT2Og"

    ADMIN_USERS = {
        "6378242947": "admin_password_1",
        "548805315": "admin_password_3"
    }

    