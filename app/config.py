import os

# D6: 统一配置常量，main.py 和 ocr_handler.py 均引用此处，避免重复定义
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
DB_PATH = 'peixun.db'
UPLOAD_DIR = 'uploads'
TEMP_IDS_DIR = os.path.join(UPLOAD_DIR, 'temp_ids')
IDCARD_SAVE_DIR = os.path.join(UPLOAD_DIR, 'idcards')
CARDS_DIR = os.path.join(UPLOAD_DIR, 'cards')

os.makedirs(TEMP_IDS_DIR, exist_ok=True)
os.makedirs(IDCARD_SAVE_DIR, exist_ok=True)
os.makedirs(CARDS_DIR, exist_ok=True)
