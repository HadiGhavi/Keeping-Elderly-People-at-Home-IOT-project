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
