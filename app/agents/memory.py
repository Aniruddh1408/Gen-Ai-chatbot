"""
Memory Agent — Persistent Session Core using Redis.
Provides high-performance, distributed session history for the AI assistant.
"""
import json
import redis
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.llm.client import llm
from app.core.config import REDIS_HOST, REDIS_PORT, REDIS_DB
from app.core.logger import get_logger

logger = get_logger("memory")

# ----------------------------
# Redis Persistence Client
# ----------------------------
# Initialize Redis connection
try:
    _redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True # Returns strings instead of bytes
    )
    # Test connection
    _redis_client.ping()
    logger.info(f"Redis connected successfully at {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    logger.error(f"Redis connection failed: {e}. Falling back to in-memory (limited session lifetime).")
    _redis_client = None

# Fallback store if Redis is unavailable
_memory_fallback: dict[str, list[dict]] = {}

MAX_HISTORY_TURNS = 3  # Reduced to save CPU/Heat and keep context focused

def get_history(session_id: str) -> list[dict]:
    """Retrieve chat history from Redis (or memory fallback)."""
    key = f"kubo_session:{session_id}"
    
    if _redis_client:
        try:
            data = _redis_client.get(key)
            history = json.loads(data) if data else []
            return history if isinstance(history, list) else []
        except Exception as e:
            logger.error(f"Failed to fetch from Redis: {e}")
            return []
    
    history = _memory_fallback.get(session_id, [])
    return history if isinstance(history, list) else []

def add_turn(session_id: str, user_msg: str, ai_msg: str):
    """Save a turn to Redis with a TTL (Time To Live)."""
    history = get_history(session_id)
    history.append({"user": user_msg, "ai": ai_msg})
    
    # Keep only the last N turns
    history = history[-MAX_HISTORY_TURNS:]
    
    key = f"kubo_session:{session_id}"
    if _redis_client:
        try:
            # Store as JSON string with a 24-hour expiration
            _redis_client.setex(key, 86400, json.dumps(history))
        except Exception as e:
            logger.error(f"Failed to save to Redis: {e}")
    else:
        _memory_fallback[session_id] = history

def clear_history(session_id: str):
    """Delete session history."""
    key = f"kubo_session:{session_id}"
    if _redis_client:
        _redis_client.delete(key)
    else:
        _memory_fallback.pop(session_id, None)

# ----------------------------
# Query Rewriter Chain
# ----------------------------
_rewrite_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a grammatical query re-writing tool.
You do NOT answer questions. You do NOT apologize. You only output the REWRITTEN QUERY.
Replace pronouns in the New Query with the specific subject from the History Context.
If the New Query is a completely new topic or does not use pronouns, return the New Query exactly as it is.
NEVER answer the question or provide information.

Example:
History: 
User: Tell me about John.
AI: John is 90 years old.
Human: What is his BP?
Output: What is John's BP?
"""),
    ("human", "History:\n{history_text}\n\nNew Query: {new_query}\n\nOutput ONLY the rewritten query:"),
])

_rewrite_chain = _rewrite_prompt | llm | StrOutputParser()

def rewrite_query_with_memory(session_id: str, new_query: str) -> str:
    chat_history = get_history(session_id)
    if not chat_history:
        return new_query

    # OPTIMIZATION: Skip LLM rewrite for very simple greetings or short queries
    # This saves one LLM roundtrip (approx 1-2s on slow hardware)
    q_lower = new_query.lower().strip()
    if len(q_lower.split()) <= 2 and any(w in q_lower for w in ["hi", "hello", "hey", "help", "thanks", "bye"]):
        return new_query

    history_text = "\n".join([f"User: {msg['user']}\nAI: {msg['ai']}" for msg in chat_history])

    try:
        rewritten = _rewrite_chain.invoke({
            "history_text": history_text,
            "new_query": new_query,
        }).strip()
        logger.info(f"Query Refined: {rewritten}")
        return rewritten if rewritten else new_query
    except Exception as e:
        logger.error(f"Rewrite failed: {e}")
        return new_query
