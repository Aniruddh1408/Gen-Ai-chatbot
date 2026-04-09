"""
Centralized configuration for the GenAI IoT Assistant.
All environment-specific settings are managed here.
"""
import os

# --- Database ---
DB_NAME = os.getenv("DB_NAME", "genai_db")
DB_USER = os.getenv("DB_USER", "genai_reader")
DB_PASS = os.getenv("DB_PASS", "7012")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

# --- Ollama LLM ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2:1.5b")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))

# --- Ollama Embeddings ---
EMBED_MODEL = os.getenv("EMBED_MODEL", "mxbai-embed-large")

# --- Connection pool ---
DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "1"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))
