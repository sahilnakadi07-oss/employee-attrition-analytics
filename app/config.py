import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
class Config:
    # Set SECRET_KEY in the environment before deploying.
    SECRET_KEY = os.environ.get("SECRET_KEY") or os.urandom(32)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Enable SESSION_COOKIE_SECURE=1 behind HTTPS in production.
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    DATABASE = str(BASE_DIR / "instance" / "hr_analytics.db")
    DATASET = str(BASE_DIR / "data" / "hr_attrition_dataset.csv")
    UPLOAD_FOLDER = str(BASE_DIR / "uploads")
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
