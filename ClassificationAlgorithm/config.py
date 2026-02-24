import os
from pathlib import Path

class Config:
    BASE_DIR = Path(os.getenv("BASE_DIR", "/ClassificationAlgorithm"))
    CLASSIFICATION = {
        "TRAINMODEL": str(BASE_DIR / "trained_model.pkl"),
        "SAMPLEPATH": str(BASE_DIR / "time_series_health_data.csv"),
    }
