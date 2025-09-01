import os
from pathlib import Path

class Config:
    BASE_DIR = Path(os.getenv("BASE_DIR", "/app/ClassificationAlgorithm"))
    CLASSIFICATION = {
        "TRAINMODEL": str(BASE_DIR / "trained_model.pkl"),
        "SAMPLEPATH": str(BASE_DIR / "elderly_health_data.csv"),
    }
