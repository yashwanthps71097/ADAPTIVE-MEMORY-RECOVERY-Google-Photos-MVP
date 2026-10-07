import os
from pathlib import Path
from dotenv import load_dotenv

# Base Directory paths
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Storage & Data Paths
DATA_DIR = BASE_DIR / "data"
RAW_PHOTOS_DIR = DATA_DIR / "raw_photos"
THUMBNAILS_DIR = DATA_DIR / "thumbnails"
SQLITE_DB_PATH = DATA_DIR / "photos.db"
QDRANT_STORAGE_PATH = DATA_DIR / "qdrant_db"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
RAW_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
QDRANT_STORAGE_PATH.mkdir(parents=True, exist_ok=True)

# Groq API Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
GROQ_FALLBACK_MODELS = ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]

# Server Configuration
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))

# Vector DB & Embeddings Configuration
COLLECTION_NAME = "photo_collection"
VECTOR_DIMENSION = 512

# Spatio-Temporal Clustering Configuration (ST-DBSCAN)
ST_DISTANCE_KM_THRESHOLD = 5.0      # <= 5 km
ST_TIME_HOURS_THRESHOLD = 48.0      # <= 48 hours
ST_MIN_SAMPLES = 2
