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

_PLURAL_RESIDENT_FOLLOWUP_WORDS = {
    "they", "them", "their", "theirs", "these", "those",
}
_SINGLE_RESIDENT_FOLLOWUP_WORDS = {
    "he", "she", "his", "her", "hers", "him", "same", "that",
}
_NAME_STOPWORDS = {
    "resident", "patient", "residents", "patients", "medical", "history",
    "health", "metrics", "blood", "pressure", "sleep", "quality", "sugar",
    "level", "step", "count", "latest", "details", "information", "about",
    "room", "flat", "age", "ages", "years", "community", "records",
}


def _history_mentions_resident_collection(chat_history: list[dict]) -> bool:
    recent_history = _get_recent_meaningful_history(chat_history, limit=2)
    for turn in recent_history:
        user_text = str(turn.get("user", "")).lower()
        ai_text = str(turn.get("ai", "")).lower()
        if any(term in user_text for term in ["residents", "patients", "list of resident", "list of patient"]):
            return True
        if "residents in this community" in ai_text:
            return True
    return False


def _rewrite_resident_collection_followup(new_query: str, chat_history: list[dict]) -> str | None:
    q_lower = new_query.lower().strip()
    words = {word.strip(".,?!") for word in q_lower.split()}
    if not words.intersection(_PLURAL_RESIDENT_FOLLOWUP_WORDS):
        return None

    if any(term in q_lower for term in ["age", "ages", "old"]):
        return "What are the ages of residents in this community?"
    if any(term in q_lower for term in ["flat", "flats", "room", "rooms"]):
        return "What are the room numbers of residents in this community?"
    if any(term in q_lower for term in ["medical history", "medical histories", "health history", "histories"]):
        return "What are the medical histories of residents in this community?"
    if any(term in q_lower for term in ["medication", "medications", "intake", "prescribed", "treatment"]):
        return "What are the prescribed medications of residents in this community?"
    if any(term in q_lower for term in ["detail", "details", "profile", "profiles", "info", "information"]):
        return "Give the details of residents in this community."
    if any(term in q_lower for term in ["bp", "blood pressure"]):
        return "What are the blood pressure readings of residents in this community?"
    if any(term in q_lower for term in ["sugar", "glucose"]):
        return "What are the sugar levels of residents in this community?"
    if any(term in q_lower for term in ["steps", "step count", "activity"]):
        return "What are the step counts of residents in this community?"
    if any(term in q_lower for term in ["sleep score", "sleep quality", "sleep scores"]):
        return "What are the sleep quality scores of residents in this community?"
    if any(term in q_lower for term in ["sleep duration", "sleep time", "slept"]):
        return "What are the sleep durations of residents in this community?"

    return None


def _is_plausible_resident_name(candidate: str) -> bool:
    words = [word.strip(" .,?!():'\"").lower() for word in candidate.split()]
    words = [word for word in words if word]
    if len(words) < 2:
        return False
    if any(word in _NAME_STOPWORDS for word in words):
        return False
    return True


def _candidate_names_from_text(text: str) -> list[str]:
    candidates: list[str] = []

    capitalized_patterns = [
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})(?=\s+\(|'s\b|\s+is\b|\s+-)",
    ]
    lower_patterns = [
        r"\b(?:about|of|for|is)\s+([a-z]+(?:\s+[a-z]+){1,2})\b",
        r"\b([a-z]+(?:\s+[a-z]+){1,2})'s\b",
    ]

    for pattern in capitalized_patterns:
        candidates.extend(match.group(1).strip().title() for match in re.finditer(pattern, text))

    text_lower = text.lower()
    for pattern in lower_patterns:
        candidates.extend(match.group(1).strip().title() for match in re.finditer(pattern, text_lower))

    unique: list[str] = []
    for candidate in candidates:
        if _is_plausible_resident_name(candidate) and candidate not in unique:
            unique.append(candidate)
    return unique


def _latest_single_resident_name(chat_history: list[dict]) -> str | None:
    recent_history = _get_recent_meaningful_history(chat_history, limit=2)
    for turn in reversed(recent_history):
        combined_text = f"{turn.get('user', '')}\n{turn.get('ai', '')}"
        candidates = _candidate_names_from_text(combined_text)
        if len(candidates) == 1:
            return candidates[0]
    return None


def _rewrite_single_resident_followup(new_query: str, chat_history: list[dict]) -> str | None:
    q_lower = new_query.lower().strip()
    words = {word.strip(".,?!") for word in q_lower.split()}
    if not words.intersection(_SINGLE_RESIDENT_FOLLOWUP_WORDS) and "that resident" not in q_lower and "same resident" not in q_lower:
        return None

    resident_name = _latest_single_resident_name(chat_history)
    if not resident_name:
        return None

    if any(term in q_lower for term in ["health metrics", "all metrics", "vitals", "vital signs"]):
        return f"What are {resident_name}'s health metrics?"
    if any(term in q_lower for term in ["bp", "blood pressure"]):
        return f"What is {resident_name}'s blood pressure?"
    if any(term in q_lower for term in ["sugar", "glucose"]):
        return f"What is {resident_name}'s sugar level?"
    if any(term in q_lower for term in ["steps", "step count", "activity"]):
        return f"What is {resident_name}'s step count?"
    if any(term in q_lower for term in ["sleep duration", "sleep time", "slept"]):
        return f"What is {resident_name}'s sleep duration?"
    if any(term in q_lower for term in ["sleep score", "sleep quality", "sleep"]):
        return f"What is {resident_name}'s sleep quality score?"
    if any(term in q_lower for term in ["age", "ages", "old"]):
        return f"What is the age of {resident_name}?"
    if any(term in q_lower for term in ["flat", "room"]):
        return f"What is the room number of {resident_name}?"
    if any(term in q_lower for term in ["medical history", "health history", "history"]):
        return f"What is the medical history of {resident_name}?"
    if any(term in q_lower for term in ["medication", "medications", "intake", "prescribed", "treatment"]):
        return f"What is the prescribed medication of {resident_name}?"
    if any(term in q_lower for term in ["detail", "details", "profile", "info", "information"]):
        return f"Give the details of {resident_name}."

    return None


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

    deterministic_rewrite = _rewrite_resident_collection_followup(new_query, chat_history)
    if deterministic_rewrite:
        logger.info(f"Query Refined deterministically: {deterministic_rewrite}")
        return deterministic_rewrite

    deterministic_rewrite = _rewrite_single_resident_followup(new_query, chat_history)
    if deterministic_rewrite:
        logger.info(f"Query Refined deterministically: {deterministic_rewrite}")
        return deterministic_rewrite

    # This is already specific enough for the SQL care-assessment macro.
    care_phrases = [
        "more care",
        "less care",
        "more acre",
        "less acre",
        "needs care",
        "need care",
        "requires care",
        "require care",
        "requires more acre",
        "requires less acre",
        "overall health",
        "most healthy",
        "healthiest",
        "not healthy",
        "unhealthy",
        "most unhealthy",
        "least healthy",
        "best health",
        "worst health",
        "poorest health",
        "poor health",
        "most stable",
        "least stable",
        "other residents",
        "other patients",
    ]
    if any(phrase in q_lower for phrase in care_phrases):
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
