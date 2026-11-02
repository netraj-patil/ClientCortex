import os

from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # ChatGroq reads this from the environment
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
SECRET_KEY = os.getenv("SECRET_KEY")  # Fernet key for saved DB passwords

# Embeddings (injected into Glia). 384 dims matches all-MiniLM-L6-v2.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
VECTOR_DIMS = int(os.getenv("VECTOR_DIMS", "384"))

# Glia cache
DISTANCE_THRESHOLD = float(os.getenv("CACHE_DISTANCE_THRESHOLD", "0.2"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))  # safety net if invalidation misses something

# Generated SQL limits
QUERY_ROW_LIMIT = int(os.getenv("QUERY_ROW_LIMIT", "100"))
QUERY_TIMEOUT_SECONDS = int(os.getenv("QUERY_TIMEOUT_SECONDS", "10"))

# Background change detection for tables that have cached answers
WATCHER_ENABLED = os.getenv("WATCHER_ENABLED", "true").lower() == "true"
WATCHER_INTERVAL_SECONDS = int(os.getenv("WATCHER_INTERVAL_SECONDS", "10"))

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")]
