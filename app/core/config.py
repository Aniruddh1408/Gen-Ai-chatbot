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

# --- Ollama LLM ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")# LLM Parameters
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2:1.5b")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.0))

# Redis Memory Persistence
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

# --- Ollama Embeddings ---
EMBED_MODEL = os.getenv("EMBED_MODEL", "mxbai-embed-large")

# --- Connection pool ---
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))
