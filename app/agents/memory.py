"""
Memory Agent — Persistent Session Core using Redis.
Provides high-performance, distributed session history for the AI assistant.
"""
import json
import redis
import re
from app.llm.client import ask_llm
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
ACKNOWLEDGEMENT_WORDS = [
    "ok", "okay", "ohk", "oh okay", "fine", "alright", "got it", "cool", "understood",
    "thanks", "thank you", "noted", "sure", "yep", "yes", "no", "nah", "gotcha"
]
_LIGHTWEIGHT_AI_PHRASES = {
    "it was my pleasure to help. please feel free to ask anything else.",
    "hello. ask about residents, health metrics, or device issues.",
    "ask about resident metrics, summaries, charts, or device troubleshooting.",
}
_SHORT_CHAT_RE = re.compile(
    r"\b(?:hi|hello|hey|help|bye|ok|okay|ohk|oh\ okay|fine|alright|got\ it|cool|understood|"
    r"thanks|thank\ you|noted|sure|yep|yes|no|nah|gotcha)\b",
    re.IGNORECASE,
)

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

_REWRITE_SYSTEM_PROMPT = """You are a query re-writing tool.
You do NOT answer questions. You do NOT apologize. You only output the REWRITTEN QUERY.

Rules:
1. Replace pronouns in the New Query with the specific subject from the History Context.
2. If the New Query is a short continuation request such as "elaborate", "tell me more", "expand", "go deeper", or "explain more", rewrite it into a standalone query about the most recent topic in the History Context.
3. If the New Query is a completely new topic unrelated to the History Context, return the New Query exactly as it is.
4. NEVER answer the question or provide information.

Example 1:
History:
User: Tell me about John.
AI: John is 90 years old.
New Query: What is his BP?
Output: What is John's BP?

Example 2:
History:
User: What is IoT?
AI: IoT stands for Internet of Things.
New Query: elaborate
Output: Explain IoT in more detail.
"""

_FOLLOW_UP_MARKERS = {
    "he", "she", "they", "them", "their", "theirs", "his", "her", "hers",
    "it", "its", "that", "those", "these", "same", "former", "latter",
    "also", "too", "again", "more", "another", "compare", "comparison",
    "elaborate", "expand", "continue", "clarify", "detail", "details",
    "deeper",
}

_FOLLOW_UP_PHRASES = [
    "what about",
    "how about",
    "show more",
    "tell me more",
    "explain more",
    "more detail",
    "more details",
    "in more detail",
    "go deeper",
    "expand on that",
    "expand on this",
    "how so",
    "go on",
    "elaborate on that",
    "elaborate on this",
    "continue that",
    "continue this",
    "same person",
    "same resident",
    "same device",
    "that resident",
    "that device",
]

_FOLLOW_UP_SOLO_WORDS = {
    "elaborate", "expand", "continue", "clarify", "details", "detail",
    "deeper", "why", "how", "more", "again", "another", "compare", "comparison",
}


def _is_acknowledgement(text: str) -> bool:
    return text.lower().strip() in ACKNOWLEDGEMENT_WORDS


def _is_lightweight_ai_turn(text: str) -> bool:
    normalized = text.lower().strip()
    return normalized in _LIGHTWEIGHT_AI_PHRASES or normalized.startswith("error:")


def _get_recent_meaningful_history(chat_history: list[dict], limit: int = 2) -> list[dict]:
    selected: list[dict] = []
    for turn in reversed(chat_history):
        user_text = str(turn.get("user", "")).strip()
        ai_text = str(turn.get("ai", "")).strip()
        if not user_text or not ai_text:
            continue
        if _is_acknowledgement(user_text):
            continue
        if _is_lightweight_ai_turn(ai_text):
            continue
        selected.append(turn)
        if len(selected) >= limit:
            break
    return list(reversed(selected))


def _needs_history_rewrite(new_query: str) -> bool:
    q_lower = new_query.lower().strip()
    if not q_lower:
        return False

    if q_lower in _FOLLOW_UP_SOLO_WORDS:
        return True

    if any(phrase in q_lower for phrase in _FOLLOW_UP_PHRASES):
        return True

    words = {word.strip(".,?!") for word in q_lower.split()}
    return any(word in words for word in _FOLLOW_UP_MARKERS)

def rewrite_query_with_memory(session_id: str, new_query: str) -> str:
    chat_history = get_history(session_id)
    if not chat_history:
        return new_query

    # Skip rewriting conversational acknowledgements and greetings.
    q_lower = new_query.lower().strip()
    if len(q_lower.split()) <= 3 and _SHORT_CHAT_RE.search(q_lower):
        return new_query

    if not _needs_history_rewrite(new_query):
        return new_query

    if q_lower in {"why", "why?", "how", "how?"}:
        latest_turn = chat_history[-1]
        latest_ai = str(latest_turn.get("ai", "")).strip()
        latest_user = str(latest_turn.get("user", "")).strip()
        if not latest_ai or _is_lightweight_ai_turn(latest_ai) or _is_acknowledgement(latest_user):
            return new_query
        history_scope = [latest_turn]
    else:
        history_scope = _get_recent_meaningful_history(chat_history, limit=2)
        if not history_scope:
            return new_query

    history_text = "\n".join([f"User: {msg['user']}\nAI: {msg['ai']}" for msg in history_scope])

    try:
        rewritten = ask_llm(
            f"History:\n{history_text}\n\nNew Query: {new_query}\n\nOutput ONLY the rewritten query:",
            system_prompt=_REWRITE_SYSTEM_PROMPT,
        ).strip()
        logger.info(f"Query Refined: {rewritten}")
        return rewritten if rewritten else new_query
    except Exception as e:
        logger.error(f"Rewrite failed: {e}")
        return new_query
