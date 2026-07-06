import os

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
UPLOAD_DIR = "uploads"
TEMP_IDS_DIR = os.path.join(UPLOAD_DIR, "temp_ids")
IDCARD_SAVE_DIR = os.path.join(UPLOAD_DIR, "idcards")

os.makedirs(TEMP_IDS_DIR, exist_ok=True)
os.makedirs(IDCARD_SAVE_DIR, exist_ok=True)
