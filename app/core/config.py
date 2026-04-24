"""
Centralized configuration for the GenAI IoT Assistant.
All environment-specific settings are managed here.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Database ---
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

# --- Generation LLM (vLLM / OpenAI-compatible) ---
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://10.0.130.10:8000/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "dummy")
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct-AWQ")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.0))

def _parse_optional_timeout(raw_value: str | None) -> int | None:
    """Return None to disable request timeouts for local generation."""
    if raw_value is None:
        return None

    cleaned = raw_value.strip().lower()
    if cleaned in {"", "none", "null", "off", "disable", "disabled", "0"}:
        return None

    parsed = int(cleaned)
    return parsed if parsed > 0 else None


LLM_TIMEOUT_SECONDS = _parse_optional_timeout(os.getenv("LLM_TIMEOUT_SECONDS"))
LLM_NUM_CTX = int(os.getenv("LLM_NUM_CTX", "2048"))
LLM_KEEP_ALIVE = os.getenv("LLM_KEEP_ALIVE", "10m")

# Redis Memory Persistence
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

# --- Ollama Embeddings ---
EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "mxbai-embed-large")

# --- Connection pool ---
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))
