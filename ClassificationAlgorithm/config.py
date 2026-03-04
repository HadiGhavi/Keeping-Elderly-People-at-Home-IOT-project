import os
from pathlib import Path

class Config:
    # Use current directory if environment variable is not set
    BASE_DIR = Path(os.getenv("BASE_DIR", Path(__file__).parent))
    CLASSIFICATION = {
        "TRAINMODEL": str(BASE_DIR / "trained_model.pkl"),
        "SAMPLEPATH": str(BASE_DIR / "time_series_health_data.csv"),
    }
