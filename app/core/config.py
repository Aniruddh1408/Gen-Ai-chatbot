# ===========================================================================
# This file is the single place all settings live. It reads values from the
# environment (database address, AI server URLs, limits, feature switches) and
# hands them to the rest of the app, with sensible defaults. Change a setting
# here or in the environment instead of hunting through the code.
# ===========================================================================
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
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://10.0.130.10:8001/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "dummy")
LLM_MODEL = os.getenv("LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct-AWQ")
LLM_DATA_TEMPERATURE = float(os.getenv("LLM_DATA_TEMPERATURE", 0.0))
LLM_CHAT_TEMPERATURE = float(os.getenv("LLM_CHAT_TEMPERATURE", 0.2))

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


# --- File uploads / per-session attachments (ephemeral, private) ---
def _env_int_cfg(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float_cfg(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _parse_extensions(raw: str | None, default: str) -> set[str]:
    value = raw if raw is not None else default
    return {
        ext.strip().lower().lstrip(".")
        for ext in value.split(",")
        if ext.strip()
    }


# Max accepted upload size (default 10 MB).
UPLOAD_MAX_BYTES = _env_int_cfg("UPLOAD_MAX_BYTES", 10 * 1024 * 1024)
# Allowed file extensions (no leading dot, lowercase). Images are intentionally
# excluded: the deployed LLM is text-only.
UPLOAD_ALLOWED_EXTENSIONS = _parse_extensions(
    os.getenv("UPLOAD_ALLOWED_EXTENSIONS"), "pdf,docx,txt,md,csv,xlsx"
)
# Uploaded files persist with their chat session (durable, no expiry). Override
# only the on-disk store location if needed.
ATTACHMENT_STORE_FILE = os.getenv("ATTACHMENT_STORE_FILE")
# Caps to keep the small LLM context window safe and storage bounded.
ATTACHMENT_MAX_FILES_PER_SESSION = max(1, _env_int_cfg("ATTACHMENT_MAX_FILES_PER_SESSION", 5))
ATTACHMENT_MAX_CHARS = max(1000, _env_int_cfg("ATTACHMENT_MAX_CHARS", 60000))
# How many of the most relevant chunks to feed the LLM per question.
ATTACHMENT_TOP_K = max(1, _env_int_cfg("ATTACHMENT_TOP_K", 4))
# Minimum cosine similarity for a chunk to count as "relevant"; below this for a
# non-summary question, the chat graph falls through to normal routing.
ATTACHMENT_MIN_SCORE = _env_float_cfg("ATTACHMENT_MIN_SCORE", 0.35)
# Chunking parameters (mirrors scripts/embed_docs.py defaults).
ATTACHMENT_CHUNK_SIZE = max(200, _env_int_cfg("ATTACHMENT_CHUNK_SIZE", 900))
ATTACHMENT_CHUNK_OVERLAP = max(0, _env_int_cfg("ATTACHMENT_CHUNK_OVERLAP", 80))

# --- Connection pool ---
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))


# --- API / CORS ---
def _parse_cors_origins(raw: str | None) -> list[str]:
    """Parse a comma-separated CORS_ALLOW_ORIGINS value; default to wildcard."""
    if not raw:
        return ["*"]
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or ["*"]


def _parse_bool(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


CORS_ALLOW_ORIGINS = _parse_cors_origins(os.getenv("CORS_ALLOW_ORIGINS"))
# Per the CORS spec, credentials cannot be combined with a wildcard origin.
CORS_ALLOW_CREDENTIALS = "*" not in CORS_ALLOW_ORIGINS
# Debug/introspection endpoints are off unless explicitly enabled.
ENABLE_DEBUG_ENDPOINTS = _parse_bool(os.getenv("ENABLE_DEBUG_ENDPOINTS"))
