# config.py
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable is not set! Create a .env file.")

    MONGO_URI = os.environ.get('MONGO_URI')
    if not MONGO_URI:
        raise ValueError("MONGO_URI environment variable is not set! Create a .env file.")

    # Session config
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = 3600

    # Paths
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    IMAGE_FOLDER = os.path.join(BASE_DIR, 'static', 'images')
    RECORDING_FOLDER = os.path.join(BASE_DIR, 'static', 'recordings')
    MAX_VIDEO_SIZE = 200 * 1024 * 1024

    # AI Config
    YOLO_MODEL = 'yolov8n.pt'
    # FIXED: raised from 0.40 - this was letting through a lot of weak,
    # noisy detections that fed straight into false anomaly alerts
    # downstream. yolo_model.py now actually reads this value (it used to
    # ignore Config and hardcode 0.40 regardless of what was set here).
    CONFIDENCE_THRESHOLD = 0.50
    ANOMALY_SCORE_THRESHOLD = 0.60