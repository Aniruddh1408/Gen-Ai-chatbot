# ===========================================================================
# This file is the assistant's short-term memory. It saves and recalls the
# back-and-forth of each conversation (kept in Redis, with an on-disk backup) so
# the assistant can make sense of follow-up questions like "what about her?".
# Each community and user gets its own separate history.
# ===========================================================================
"""
Memory Agent — Persistent Session Core using Redis.
Provides high-performance, distributed session history for the AI assistant.
"""
import json
import os
from pathlib import Path
import re

try:
    import redis
except Exception:
    redis = None

from app.llm.client import ask_llm
from app.core.config import REDIS_HOST, REDIS_PORT, REDIS_DB
from app.core.community import LOCAL_DEMO_COMMUNITIES
from app.core.logger import get_logger

logger = get_logger("memory")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


_REPO_ROOT = Path(__file__).resolve().parents[2]
_HISTORY_FILE = Path(
    os.getenv("CHAT_HISTORY_FILE", str(_REPO_ROOT / ".cache" / "kubocare_chat_history.json"))
)
MAX_HISTORY_TURNS = max(1, _env_int("MAX_HISTORY_TURNS", 50))
HISTORY_TTL_SECONDS = max(60, _env_int("HISTORY_TTL_SECONDS", 60 * 60 * 24 * 30))

# ----------------------------
# Redis Persistence Client
# ----------------------------
# Initialize Redis connection
try:
    if redis is None:
        raise RuntimeError("redis package is not installed")

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
    logger.error(f"Redis connection failed: {e}. Falling back to local file history at {_HISTORY_FILE}.")
    _redis_client = None

# Fallback store if Redis is unavailable
_memory_fallback: dict[str, list[dict]] = {}

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


def _valid_history(history) -> list[dict]:
    if not isinstance(history, list):
        return []

    valid_turns: list[dict] = []
    for turn in history:
        if not isinstance(turn, dict):
            continue
        user_text = str(turn.get("user", "")).strip()
        ai_text = str(turn.get("ai", "")).strip()
        if user_text or ai_text:
            valid_turns.append({"user": user_text, "ai": ai_text})
    return valid_turns[-MAX_HISTORY_TURNS:]


def _load_file_store() -> dict[str, list[dict]]:
    try:
        if not _HISTORY_FILE.exists():
            return {}
        with _HISTORY_FILE.open("r", encoding="utf-8") as handle:
            raw_store = json.load(handle)
    except Exception as e:
        logger.error(f"Failed to load local history file: {e}")
        return {}

    if not isinstance(raw_store, dict):
        return {}

    return {
        str(session_id): _valid_history(history)
        for session_id, history in raw_store.items()
    }


def _save_file_store(store: dict[str, list[dict]]) -> None:
    try:
        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_file = _HISTORY_FILE.with_suffix(f"{_HISTORY_FILE.suffix}.tmp")
        with temp_file.open("w", encoding="utf-8") as handle:
            json.dump(store, handle)
        temp_file.replace(_HISTORY_FILE)
    except Exception as e:
        logger.error(f"Failed to save local history file: {e}")


def _get_file_history(session_id: str) -> list[dict]:
    if session_id not in _memory_fallback:
        _memory_fallback.update(_load_file_store())
    return _valid_history(_memory_fallback.get(session_id, []))


def _set_file_history(session_id: str, history: list[dict]) -> None:
    _memory_fallback[session_id] = _valid_history(history)
    store = _load_file_store()
    store[session_id] = _memory_fallback[session_id]
    _save_file_store(store)


def _delete_file_history(session_id: str) -> None:
    _memory_fallback.pop(session_id, None)
    store = _load_file_store()
    if session_id in store:
        store.pop(session_id, None)
        _save_file_store(store)


def get_history(session_id: str) -> list[dict]:
    """Retrieve chat history from Redis (or memory fallback)."""
    key = f"kubo_session:{session_id}"
    
    if _redis_client:
        try:
            data = _redis_client.get(key)
            history = json.loads(data) if data else []
            return _valid_history(history)
        except Exception as e:
            logger.error(f"Failed to fetch from Redis: {e}")
            return _get_file_history(session_id)
    
    return _get_file_history(session_id)

def add_turn(session_id: str, user_msg: str, ai_msg: str):
    """Save a turn to Redis, or to local durable storage when Redis is unavailable."""
    history = get_history(session_id)
    history.append({"user": user_msg, "ai": ai_msg})
    
    # Keep only the last N turns
    history = _valid_history(history)
    
    key = f"kubo_session:{session_id}"
    if _redis_client:
        try:
            _redis_client.setex(key, HISTORY_TTL_SECONDS, json.dumps(history))
            return
        except Exception as e:
            logger.error(f"Failed to save to Redis: {e}")

    _set_file_history(session_id, history)

def clear_history(session_id: str):
    """Delete session history."""
    key = f"kubo_session:{session_id}"
    if _redis_client:
        try:
            _redis_client.delete(key)
        except Exception as e:
            logger.error(f"Failed to delete Redis history: {e}")

    _delete_file_history(session_id)

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
    "he", "she", "his", "her", "hers", "him", "it", "its", "this", "same", "that",
}
_NAME_STOPWORDS = {
    "resident", "patient", "residents", "patients", "medical", "history",
    "health", "metrics", "blood", "pressure", "bp", "sleep", "quality", "sugar",
    "level", "step", "count", "latest", "current", "details", "information", "about",
    "room", "flat", "age", "ages", "years", "community", "records",
    "what", "which", "who", "whom", "whose", "where", "when", "why", "how",
    "is", "are", "was", "were", "be", "being", "been", "do", "does", "did",
    "the", "a", "an", "their", "them", "they", "his", "her", "hers", "him",
    "he", "she", "it", "its", "this", "that", "these", "those", "all", "same",
    "and", "or",
    "list", "show", "give", "tell", "get", "me", "please", "on",
    "check", "review", "compare", "confirm", "use", "prioritize",
    "average", "avg", "mean",
    # Device / sensor vocabulary — never a resident name. Without these,
    # "what is the device id in that room?" treats "device id" as a name and
    # the follow-up rewriter wrongly skips it as an explicit profile lookup.
    "device", "devices", "sensor", "sensors", "radar", "id", "ids",
    "status", "monitor", "monitoring", "in",
}

_COLLECTION_FOLLOWUP_METRIC_TERMS = [
    "age", "ages", "old", "flat", "flats", "room", "rooms",
    "medical history", "medical histories", "health history", "histories",
    "medication", "medications", "intake", "prescribed", "treatment",
    "detail", "details", "profile", "profiles", "info", "information",
    "bp", "blood pressure", "sugar", "glucose", "steps", "step count",
    "activity", "sleep score", "sleep quality", "sleep scores",
    "sleep duration", "sleep time", "slept",
]
_NAMED_PROFILE_LOOKUP_TERMS = [
    "detail", "details", "profile", "info", "information", "about",
    "age", "ages", "old", "flat", "room", "medical history",
    "health history", "history", "medication", "medications", "intake",
    "prescribed", "treatment",
]
_CARE_FOLLOWUP_TERMS = [
    "care", "more care", "needs care", "need care", "requires care",
    "priority", "attention", "risk", "healthy", "unhealthy",
]
_METRIC_INTERPRETATION_TERMS = [
    "good", "bad", "normal", "okay", "ok", "fine", "concerning",
    "concern", "low", "high", "better", "worse",
]
_GENERAL_EXPLANATION_START_RE = re.compile(
    r"^\s*(?:what\s+(?:is|are)|explain|define|meaning\s+of|how\s+(?:is|are|does|do)|why\s+(?:is|are|does|do))\b",
    re.IGNORECASE,
)
_GENERAL_EXPLANATION_TERMS = [
    "bp", "blood pressure", "sugar", "glucose", "sleep quality score",
    "sleep score", "sleep duration", "step count", "vitals", "vital signs",
    "hypertension", "diabetes", "pre-diabetes", "prediabetes", "arthritis",
    "asthma", "cardiac", "cardiovascular", "osteoporosis", "thyroid",
    "atorvastatin", "metformin", "amlodipine", "paracetamol", "salbutamol",
    "telmisartan", "levothyroxine", "aspirin", "calcium", "vitamin",
]

_RANKING_OR_SUPERLATIVE_TERMS = [
    "oldest", "eldest", "youngest", "highest", "lowest", "best", "worst",
    "most", "least", "top", "bottom", "fewest", "longest", "shortest",
    "healthiest", "unhealthiest",
]

_AGGREGATE_TERMS = [
    "average", "avg", "mean", "total", "count", "how many", "number of",
]
_KNOWN_COMMUNITY_NAMES = {
    name.lower()
    for name in LOCAL_DEMO_COMMUNITIES.values()
}
_CURRENT_METRIC_TERMS = [
    "current", "latest", "today", "now", "recent",
]

_COLLECTION_AI_MARKERS = [
    "residents in this community:",
    "resident ages:",
    "resident rooms:",
    "resident details:",
    "resident medical histories:",
    "resident prescribed medications:",
    "resident blood pressure readings:",
    "resident sugar levels:",
    "resident step counts:",
    "resident sleep quality scores:",
    "resident sleep durations:",
    "resident health metrics:",
]


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE) is not None


def _contains_any_term(text: str, terms: list[str]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _mentions_current_community_reference(text: str) -> bool:
    q_lower = text.lower()
    return any(
        phrase in q_lower
        for phrase in [
            "this community",
            "current community",
            "selected community",
            "viewing community",
        ]
    )


def _is_known_community_name(candidate: str) -> bool:
    return candidate.lower().strip(" .,?!") in _KNOWN_COMMUNITY_NAMES


def _turn_mentions_resident_collection(turn: dict) -> bool:
    user_text = str(turn.get("user", "")).lower()
    ai_text = str(turn.get("ai", "")).lower()
    if any(term in user_text for term in ["residents", "patients", "list of resident", "list of patient"]):
        return True
    return any(marker in ai_text for marker in _COLLECTION_AI_MARKERS)


def _history_mentions_resident_collection(chat_history: list[dict]) -> bool:
    recent_history = _get_recent_meaningful_history(chat_history, limit=2)
    for turn in recent_history:
        if _turn_mentions_resident_collection(turn):
            return True
    return False


def _has_specific_name_in_query(query: str) -> bool:
    if _candidate_names_from_text(query):
        return True

    # Lowercase/manual typing variant: "devendra patil bp" or "leela varma sleep".
    q_lower = query.lower()
    metric_tail = (
        r"bp|blood pressure|sugar|glucose|steps?|step count|sleep|slept|"
        r"sleep score|sleep quality|sleep duration|age|room|flat|"
        r"medical history|medication|prescribed|details?"
    )
    for match in re.finditer(
        rf"\b(?:what\s+is|what's|how\s+old\s+is|where\s+(?:does|is))\s+"
        rf"([a-z]+\s+[a-z]+(?:\s+[a-z]+)?)(?:'s)?\s+(?:{metric_tail})\b",
        q_lower,
    ):
        if _is_plausible_resident_name(match.group(1)):
            return True

    for match in re.finditer(rf"\b([a-z]+\s+[a-z]+(?:\s+[a-z]+)?)\s+(?:{metric_tail})\b", q_lower):
        if _is_plausible_resident_name(match.group(1)):
            return True

    profile_tail = (
        r"details?|profile|info|information|age|old|room|flat|"
        r"medical history|health history|history|medication|prescribed|intake|treatment"
    )
    fragment_patterns = [
        rf"\b(?:give|show|display|get|tell)\b(?:\s+me)?(?:\s+the)?\s+(?:{profile_tail})\s+"
        rf"(?:of|for|about)\s+(?:resident\s+|patient\s+)?([a-z]+)\b",
        rf"\b(?:{profile_tail})\s+(?:of|for|about)\s+(?:resident\s+|patient\s+)?([a-z]+)\b",
        rf"\b(?:what\s+is|what's|how\s+old\s+is|where\s+(?:does|is))\s+"
        rf"(?:resident\s+|patient\s+)?([a-z]+)(?:'s)?\s+(?:{metric_tail})\b",
        rf"\b([a-z]+)\s+(?:{profile_tail})\b",
    ]
    for pattern in fragment_patterns:
        match = re.search(pattern, q_lower)
        if match and _is_plausible_resident_name_fragment(match.group(1)):
            return True
    return False


def _is_ranking_or_superlative_query(q_lower: str) -> bool:
    return _contains_any_term(q_lower, _RANKING_OR_SUPERLATIVE_TERMS)


def _metric_from_query(q_lower: str) -> str | None:
    if _contains_any_term(q_lower, ["health metrics", "all metrics", "vitals", "vital signs"]):
        return "all_metrics"
    if _contains_any_term(q_lower, ["bp", "blood pressure"]):
        return "bp"
    if _contains_any_term(q_lower, ["sugar", "glucose"]):
        return "sugar"
    if _contains_any_term(q_lower, ["steps", "step count", "activity", "walked", "walking"]):
        return "steps"
    if _contains_any_term(q_lower, ["sleep duration", "sleep time", "slept"]):
        return "sleep_duration"
    if _contains_any_term(q_lower, ["sleep score", "sleep quality", "sleep scores"]):
        return "sleep_quality"
    if _contains_term(q_lower, "sleep"):
        return "sleep"
    return None


def _ranking_direction(q_lower: str) -> str | None:
    if _contains_any_term(q_lower, ["lowest", "least", "fewest", "worst", "bottom", "shortest"]):
        return "ASC"
    if _contains_any_term(q_lower, ["highest", "most", "top", "best", "longest"]):
        return "DESC"
    return None


def _ranking_query_for_metric(metric: str, direction: str) -> str | None:
    high = direction == "DESC"
    if metric == "bp":
        return f"Who has the {'highest' if high else 'lowest'} blood pressure in this community?"
    if metric == "sugar":
        return f"Who has the {'highest' if high else 'lowest'} sugar level in this community?"
    if metric == "steps":
        return f"Who walked the {'most' if high else 'fewest'} steps in this community?"
    if metric == "sleep_duration":
        return f"Who slept the {'longest' if high else 'shortest'} in this community?"
    if metric == "sleep_quality":
        return f"Who has the {'best' if high else 'worst'} sleep quality score in this community?"
    return None


def _average_query_for_metric(metric: str) -> str | None:
    if metric == "bp":
        return "What is the average blood pressure in this community?"
    if metric == "sugar":
        return "What is the average sugar level in this community?"
    if metric == "steps":
        return "What is the average step count in this community?"
    if metric == "sleep_duration":
        return "What is the average sleep duration in this community?"
    if metric == "sleep_quality":
        return "What is the average sleep quality score in this community?"
    return None


def _collection_query_for_metric(metric: str) -> str | None:
    if metric == "all_metrics":
        return "What are the health metrics of residents in this community?"
    if metric == "bp":
        return "What are the blood pressure readings of residents in this community?"
    if metric == "sugar":
        return "What are the sugar levels of residents in this community?"
    if metric == "steps":
        return "What are the step counts of residents in this community?"
    if metric == "sleep_duration":
        return "What are the sleep durations of residents in this community?"
    if metric == "sleep_quality":
        return "What are the sleep quality scores of residents in this community?"
    if metric == "sleep":
        return "What are the sleep metrics of residents in this community?"
    return None


# Ranking / care phrasings produce a SMALL named set ("top 3 ... most care",
# "oldest 5") whose specific names we DO want to capture for an "among them"
# follow-up. Only a FULL roster list ("list all residents") should be skipped.
_NAMED_SET_RANKING_TERMS = (
    "top", "most", "least", "highest", "lowest", "oldest", "youngest",
    "eldest", "best", "worst", "care", "priority", "risk", "fewest",
    "concerning", "stable",
)


def _latest_resident_name_set(chat_history: list[dict]) -> list[str]:
    recent_history = _get_recent_meaningful_history(chat_history, limit=2)
    for turn in reversed(recent_history):
        user_text = str(turn.get("user", "")).lower()
        ai_text = str(turn.get("ai", "")).lower()
        if "residents in this community:" in ai_text:
            continue
        # Skip a full-roster list request, but NOT a ranked/care subset — those
        # name the specific residents the user is now asking "among them" about.
        is_full_list_request = re.search(
            r"\b(?:all|list|show|display|get|give)\b.*\b(?:residents|patients)\b",
            user_text,
        ) and not any(term in user_text for term in _NAMED_SET_RANKING_TERMS)
        if is_full_list_request:
            continue
        combined_text = f"{turn.get('user', '')}\n{turn.get('ai', '')}"
        candidates = _candidate_names_from_text(combined_text)
        if len(candidates) >= 2:
            return candidates
    return []


def _join_resident_names(names: list[str]) -> str:
    if len(names) <= 1:
        return names[0] if names else ""
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def _metric_phrase(metric: str) -> str | None:
    if metric == "all_metrics":
        return "health metrics"
    if metric == "bp":
        return "blood pressure"
    if metric == "sugar":
        return "sugar level"
    if metric == "steps":
        return "step count"
    if metric == "sleep_duration":
        return "sleep duration"
    if metric == "sleep_quality":
        return "sleep quality score"
    if metric == "sleep":
        return "sleep metrics"
    return None


def _is_named_set_followup(q_lower: str, words: set[str]) -> bool:
    if words.intersection({"these", "those", "them", "their", "theirs"}):
        return True
    return any(
        phrase in q_lower
        for phrase in [
            "among these",
            "among those",
            "among them",
            "of these",
            "of those",
            "from these",
            "from those",
            "between them",
        ]
    )


def _rewrite_named_set_followup(new_query: str, chat_history: list[dict]) -> str | None:
    q_lower = new_query.lower().strip()
    words = {word.strip(".,?!") for word in q_lower.split()}
    if not _is_named_set_followup(q_lower, words):
        return None

    resident_names = _latest_resident_name_set(chat_history)
    if len(resident_names) < 2:
        return None

    joined_names = _join_resident_names(resident_names)

    if re.search(r"\b(?:oldest|eldest|older|elder)\b", q_lower):
        return f"Who is older among {joined_names}?"
    if re.search(r"\b(?:youngest|younger)\b", q_lower):
        return f"Who is younger among {joined_names}?"

    if _contains_any_term(q_lower, _CARE_FOLLOWUP_TERMS):
        if _contains_any_term(
            q_lower,
            ["least", "less", "lowest", "fewest", "minimal", "most stable", "healthiest", "best health"],
        ):
            return f"Which of {joined_names} needs the least care?"
        return f"Which of {joined_names} needs more care?"

    metric = _metric_from_query(q_lower)
    metric_text = _metric_phrase(metric) if metric else None
    if metric_text:
        direction = _ranking_direction(q_lower)
        if direction == "DESC":
            return f"Which of {joined_names} has higher {metric_text}?"
        if direction == "ASC":
            return f"Which of {joined_names} has lower {metric_text}?"
        return f"What is the {metric_text} of {joined_names}?"

    if _contains_any_term(q_lower, ["age", "ages", "old"]):
        return f"What are the ages of {joined_names}?"
    if _contains_any_term(q_lower, ["flat", "flats", "room", "rooms"]):
        return f"What are the room numbers of {joined_names}?"
    if _contains_any_term(q_lower, ["medical history", "medical histories", "health history", "histories"]):
        return f"What are the medical histories of {joined_names}?"
    if _contains_any_term(q_lower, ["medication", "medications", "intake", "prescribed", "treatment"]):
        return f"What are the prescribed medications of {joined_names}?"
    if _contains_any_term(q_lower, ["detail", "details", "profile", "profiles", "info", "information"]):
        return f"Give details of {joined_names}."

    return None


def _named_metric_query(resident_name: str, metric: str) -> str | None:
    if metric == "all_metrics":
        return f"What are {resident_name}'s health metrics?"
    if metric == "bp":
        return f"What is {resident_name}'s blood pressure?"
    if metric == "sugar":
        return f"What is {resident_name}'s sugar level?"
    if metric == "steps":
        return f"What is {resident_name}'s step count?"
    if metric == "sleep_duration":
        return f"What is {resident_name}'s sleep duration?"
    if metric == "sleep_quality":
        return f"What is {resident_name}'s sleep quality score?"
    if metric == "sleep":
        return f"What are {resident_name}'s sleep metrics?"
    return None


def _named_average_metric_query(resident_name: str, metric: str) -> str | None:
    if metric == "bp":
        return f"What is {resident_name}'s average blood pressure?"
    if metric == "sugar":
        return f"What is {resident_name}'s average sugar level?"
    if metric == "steps":
        return f"What is {resident_name}'s average step count?"
    if metric == "sleep_duration":
        return f"What is {resident_name}'s average sleep duration?"
    if metric == "sleep_quality":
        return f"What is {resident_name}'s average sleep quality score?"
    return None


def _named_metric_interpretation_query(resident_name: str, metric: str) -> str | None:
    if metric == "bp":
        return f"Is {resident_name}'s blood pressure good or bad?"
    if metric == "sugar":
        return f"Is {resident_name}'s sugar level good or bad?"
    if metric == "steps":
        return f"Is {resident_name}'s step count good or bad?"
    if metric == "sleep_duration":
        return f"Is {resident_name}'s sleep duration good or bad?"
    if metric == "sleep_quality":
        return f"Is {resident_name}'s sleep quality score good or bad?"
    if metric == "sleep":
        return f"Are {resident_name}'s sleep metrics good or bad?"
    return None


def _named_average_metric_interpretation_query(resident_name: str, metric: str) -> str | None:
    if metric == "bp":
        return f"Is {resident_name}'s average blood pressure good or bad?"
    if metric == "sugar":
        return f"Is {resident_name}'s average sugar level good or bad?"
    if metric == "steps":
        return f"Is {resident_name}'s average step count good or bad?"
    if metric == "sleep_duration":
        return f"Is {resident_name}'s average sleep duration good or bad?"
    if metric == "sleep_quality":
        return f"Is {resident_name}'s average sleep quality score good or bad?"
    return None


def _latest_single_resident_metric(chat_history: list[dict]) -> str | None:
    recent_history = _get_recent_meaningful_history(chat_history, limit=2)
    for turn in reversed(recent_history):
        combined_text = f"{turn.get('user', '')}\n{turn.get('ai', '')}".lower()
        metric = _metric_from_query(combined_text)
        if metric:
            return metric
    return None


def _is_metric_followup(q_lower: str, words: set[str]) -> bool:
    if _has_specific_name_in_query(q_lower):
        return False
    if _is_ranking_or_superlative_query(q_lower):
        return False
    if _contains_any_term(q_lower, _AGGREGATE_TERMS):
        return False
    if q_lower.startswith(("who ", "which ")):
        return False
    if q_lower.startswith(("show ", "list ", "display ", "give ", "get ")):
        return False
    if not _metric_from_query(q_lower):
        return False
    if words.intersection(_SINGLE_RESIDENT_FOLLOWUP_WORDS):
        return True
    if any(phrase in q_lower for phrase in _FOLLOW_UP_PHRASES):
        return True
    return len(words) <= 4


def _is_explicit_resident_id_lookup(q_lower: str) -> bool:
    if not re.search(r"\b(?:resident|patient)\b", q_lower):
        return False
    return re.search(r"\b(?:id|number|no\.?|#)\s*(?:is\s*)?\d+\b", q_lower) is not None


def _is_explicit_named_profile_lookup(query: str) -> bool:
    q_lower = query.lower().strip()
    if not _has_specific_name_in_query(query):
        return False
    return _contains_any_term(q_lower, _NAMED_PROFILE_LOOKUP_TERMS)


def _is_self_contained_explanation_query(new_query: str) -> bool:
    q_lower = new_query.lower().strip()
    if not _GENERAL_EXPLANATION_START_RE.search(q_lower):
        return False
    if _has_specific_name_in_query(new_query):
        return False
    if re.search(r"\b(?:he|she|his|her|hers|him|they|them|their|theirs|this resident|that resident|same resident)\b", q_lower):
        return False
    return _contains_any_term(q_lower, _GENERAL_EXPLANATION_TERMS)


def _rewrite_metric_followup_from_recent_context(new_query: str, chat_history: list[dict]) -> str | None:
    q_lower = new_query.lower().strip()
    words = {word.strip(".,?!") for word in q_lower.split()}
    if not _is_metric_followup(q_lower, words):
        return None

    metric = _metric_from_query(q_lower)
    if not metric:
        return None

    has_single_resident_reference = bool(words.intersection(_SINGLE_RESIDENT_FOLLOWUP_WORDS))
    recent_history = _get_recent_meaningful_history(chat_history, limit=2)
    for turn in reversed(recent_history):
        previous_user = str(turn.get("user", "")).lower()
        previous_ai = str(turn.get("ai", "")).lower()
        previous_context = f"{previous_user}\n{previous_ai}"

        if _turn_mentions_resident_collection(turn):
            if has_single_resident_reference:
                continue
            return _collection_query_for_metric(metric)

        if _is_ranking_or_superlative_query(previous_context):
            direction = _ranking_direction(previous_context)
            if direction:
                return _ranking_query_for_metric(metric, direction)

        if (
            _contains_any_term(previous_user, _AGGREGATE_TERMS)
            and not has_single_resident_reference
            and not _contains_any_term(q_lower, _CURRENT_METRIC_TERMS)
        ):
            return _average_query_for_metric(metric)

        previous_candidates = _candidate_names_from_text(f"{turn.get('user', '')}\n{turn.get('ai', '')}")
        if len(previous_candidates) == 1:
            return _named_metric_query(previous_candidates[0], metric)

    return None


def _is_elliptical_collection_followup(q_lower: str, words: set[str]) -> bool:
    if _is_ranking_or_superlative_query(q_lower):
        return False

    if _contains_any_term(q_lower, _AGGREGATE_TERMS):
        return False

    if q_lower.startswith(("who ", "which ")):
        return False

    if any(phrase in q_lower for phrase in _FOLLOW_UP_PHRASES):
        return True

    has_metric_term = any(term in q_lower for term in _COLLECTION_FOLLOWUP_METRIC_TERMS)
    if not has_metric_term:
        return False

    # Short fragments after a resident list: "ages?", "bp readings?", "what about sugar?"
    return len(words) <= 5


def _rewrite_resident_collection_followup(new_query: str, chat_history: list[dict]) -> str | None:
    q_lower = new_query.lower().strip()
    words = {word.strip(".,?!") for word in q_lower.split()}
    has_plural_reference = bool(words.intersection(_PLURAL_RESIDENT_FOLLOWUP_WORDS))
    has_single_resident_reference = bool(words.intersection(_SINGLE_RESIDENT_FOLLOWUP_WORDS))
    has_collection_context = _history_mentions_resident_collection(chat_history)
    if _has_specific_name_in_query(new_query):
        return None
    if has_single_resident_reference:
        return None
    if _is_ranking_or_superlative_query(q_lower):
        return None
    if not has_plural_reference and not (
        has_collection_context and _is_elliptical_collection_followup(q_lower, words)
    ):
        return None

    if re.search(r"\b(?:oldest|eldest|senior[-\s]?most)\b", q_lower):
        return "Who is the oldest resident in this community?"
    if re.search(r"\byoungest\b", q_lower):
        return "Who is the youngest resident in this community?"
    if _contains_any_term(q_lower, ["age", "ages", "old"]):
        return "What are the ages of residents in this community?"
    if _contains_any_term(q_lower, ["flat", "flats", "room", "rooms"]):
        return "What are the room numbers of residents in this community?"
    if _contains_any_term(q_lower, ["medical history", "medical histories", "health history", "histories"]):
        return "What are the medical histories of residents in this community?"
    if _contains_any_term(q_lower, ["medication", "medications", "intake", "prescribed", "treatment"]):
        return "What are the prescribed medications of residents in this community?"
    if _contains_any_term(q_lower, ["detail", "details", "profile", "profiles", "info", "information"]):
        return "Give the details of residents in this community."
    if _contains_any_term(q_lower, ["bp", "blood pressure"]):
        return "What are the blood pressure readings of residents in this community?"
    if _contains_any_term(q_lower, ["sugar", "glucose"]):
        return "What are the sugar levels of residents in this community?"
    if _contains_any_term(q_lower, ["steps", "step count", "activity"]):
        return "What are the step counts of residents in this community?"
    if _contains_any_term(q_lower, ["sleep score", "sleep quality", "sleep scores"]):
        return "What are the sleep quality scores of residents in this community?"
    if _contains_any_term(q_lower, ["sleep duration", "sleep time", "slept"]):
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


def _is_plausible_resident_name_fragment(candidate: str) -> bool:
    words = [word.strip(" .,?!():'\"").lower() for word in candidate.split()]
    words = [word for word in words if word]
    if len(words) != 1:
        return False
    word = words[0]
    if len(word) < 2 or word in _NAME_STOPWORDS:
        return False
    return True


# Prepositions / articles / time words that a greedy capture can sweep onto a
# name's edges (e.g. "for Lakshmi Krishnan in the last week" -> "Lakshmi
# Krishnan In"). Trimmed from BOTH ends before the plausibility check.
# Deliberately EXCLUDES list separators like "and"/"or": a capture such as
# "priya leela and" must stay rejected (it's a list of first names, not one
# person), so we leave the separator in place for _is_plausible_resident_name
# to reject rather than salvaging a bogus "Priya Leela".
_EDGE_TRIM_WORDS = {
    "in", "at", "to", "by", "from", "of", "for", "about",
    "the", "a", "an", "is", "was", "are", "were",
    "last", "this", "next", "recent", "recently", "now", "today",
    "yesterday", "week", "weeks", "day", "days", "month", "months",
    "year", "years", "need", "needs", "more", "care", "fall", "falls",
    "had", "have", "has", "doing", "still", "currently",
}


def _trim_edge_words(candidate: str) -> str:
    """Drop leading/trailing function words a greedy capture pulled in."""
    tokens = candidate.split()

    def is_edge(token: str) -> bool:
        return token.lower().strip(" .,?!'\"") in _EDGE_TRIM_WORDS

    while tokens and is_edge(tokens[0]):
        tokens.pop(0)
    while tokens and is_edge(tokens[-1]):
        tokens.pop()
    return " ".join(tokens)


def _candidate_names_from_text(text: str) -> list[str]:
    candidates: list[str] = []

    capitalized_patterns = [
        r"\bName:\s*([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){1,2})\b",
        r"\b([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){1,2})(?=[ \t]+\(|'s\b|[ \t]+is\b|[ \t]+-)",
        # Bulleted/numbered ranking or care-list rows: "- Anil Sharma, age 86 —
        # score 6", "1. Mary Johnson — 84 years". Capture the name when it is
        # followed by a comma, a dash (-, –, —), "(", or " age".
        r"^\s*(?:[-*]|\d+\.)\s+([A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+){1,2})"
        r"(?=,|[ \t]+[—–-]|[ \t]+\(|[ \t]+age\b)",
    ]
    lower_patterns = [
        r"\b(?:about|of|for|is)[ \t]+([a-z]+(?:[ \t]+[a-z]+){1,2})\b",
        r"\b([a-z]+(?:[ \t]+[a-z]+){1,2})'s\b",
    ]

    for line in text.splitlines():
        for pattern in capitalized_patterns:
            candidates.extend(
                _trim_edge_words(match.group(1)).title()
                for match in re.finditer(pattern, line)
            )

        text_lower = line.lower()
        for pattern in lower_patterns:
            candidates.extend(
                _trim_edge_words(match.group(1)).title()
                for match in re.finditer(pattern, text_lower)
            )

    unique: list[str] = []
    for candidate in candidates:
        if _is_plausible_resident_name(candidate) and not _is_known_community_name(candidate) and candidate not in unique:
            unique.append(candidate)
    return unique


# "any other resident", "anyone else", "another patient" — a follow-up that
# asks about residents OTHER THAN the one currently in focus. We resolve the
# focus resident from history and rewrite to an explicit "other than <Name>"
# form so the SQL handler can exclude them instead of re-listing the same row.
_OTHER_RESIDENT_RE = re.compile(
    r"\b(?:any\s+)?other\s+(?:resident|patient)s?\b"
    r"|\banother\s+(?:resident|patient)\b"
    r"|\b(?:any\s*one|anyone|anybody|some\s*one|someone|somebody)\s+else\b"
    r"|\bwho\s+else\b"
    r"|\brest\s+of\s+the\s+(?:residents|patients)\b",
    re.IGNORECASE,
)
_WHO_ELSE_RE = re.compile(r"\bwho\s+else\b", re.IGNORECASE)
_OTHER_RESIDENT_REPLACEMENTS = [
    (r"\bany\s+other\s+(resident|patient)s\b", r"any \1s other than {name}"),
    (r"\bany\s+other\s+(resident|patient)\b", r"any \1 other than {name}"),
    (r"\bother\s+(resident|patient)s\b", r"\1s other than {name}"),
    (r"\bother\s+(resident|patient)\b", r"\1 other than {name}"),
    (r"\banother\s+(resident|patient)\b", r"a \1 other than {name}"),
    (r"\b(?:any\s*one|anyone|anybody|some\s*one|someone|somebody)\s+else\b",
     "any resident other than {name}"),
    (r"\brest\s+of\s+the\s+(residents|patients)\b", r"\1 other than {name}"),
]


# "the device in that room", "who is in this room" — a follow-up that points
# back at a room mentioned in the previous turn. We resolve the resident in
# focus and rewrite "that/this room" to "<focus>'s room" so the device/room
# handlers can resolve it without depending on the LLM.
# Only demonstratives ("that room" / "this room" / "the same room"). Pronoun
# forms like "his room" are already handled by _rewrite_single_resident_followup.
_THAT_ROOM_RE = re.compile(r"\b(?:that|this|the\s+same)\s+room\b", re.IGNORECASE)


def _rewrite_that_room_followup(new_query: str, chat_history: list[dict]) -> str | None:
    if not _THAT_ROOM_RE.search(new_query):
        return None
    focus = _latest_single_resident_name(chat_history)
    if not focus:
        return None
    return _THAT_ROOM_RE.sub(f"{focus}'s room", new_query, count=1)


def _rewrite_exclusion_followup(new_query: str, chat_history: list[dict]) -> str | None:
    """Rewrite an "other / who else" follow-up into an explicit
    "... other than <names> ..." form using the resident(s) from recent history.

    The exclusion target is the FULL set the previous turn named — so after a
    care list ("Anil, Kamala, Sunita"), "who else needs care?" excludes all
    three and surfaces the next residents. Falls back to the single resident in
    focus (e.g. after one fall answer). Returns None when there's nobody to
    exclude (the query then runs community-wide as before)."""
    if not _OTHER_RESIDENT_RE.search(new_query.lower()):
        return None

    # Prefer the full named set (ranked/care list); else the single focus.
    targets = _latest_resident_name_set(chat_history)
    if len(targets) < 2:
        single = _latest_single_resident_name(chat_history)
        targets = [single] if single else []
    if not targets:
        return None

    joined = _join_resident_names(targets)

    # "who else needs the most care?" -> "who needs the most care other than
    # Anil Sharma, Kamala Iyengar, and Sunita Rao?" — keep the verb phrase
    # intact (so SQL intent detection still fires) and append the exclusion.
    if _WHO_ELSE_RE.search(new_query):
        base = _WHO_ELSE_RE.sub("who", new_query, count=1).strip().rstrip("?.!").strip()
        return f"{base} other than {joined}?"

    for pattern, template in _OTHER_RESIDENT_REPLACEMENTS:
        rewritten = re.sub(
            pattern, template.format(name=joined), new_query, count=1, flags=re.IGNORECASE
        )
        if rewritten != new_query:
            return rewritten
    return None


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

    if _contains_any_term(q_lower, _CARE_FOLLOWUP_TERMS):
        return f"Does {resident_name} need more care?"

    if _contains_any_term(q_lower, _AGGREGATE_TERMS):
        metric = _metric_from_query(q_lower) or _latest_single_resident_metric(chat_history)
        average_query = _named_average_metric_query(resident_name, metric) if metric else None
        if average_query:
            return average_query

    if _contains_any_term(q_lower, _METRIC_INTERPRETATION_TERMS):
        metric = _metric_from_query(q_lower) or _latest_single_resident_metric(chat_history)
        recent_history = _get_recent_meaningful_history(chat_history, limit=1)
        previous_user = str(recent_history[-1].get("user", "")).lower() if recent_history else ""
        previous_ai = str(recent_history[-1].get("ai", "")).lower() if recent_history else ""
        previous_was_average = _contains_any_term(f"{previous_user}\n{previous_ai}", _AGGREGATE_TERMS)
        interpretation_query = (
            _named_average_metric_interpretation_query(resident_name, metric)
            if metric and previous_was_average
            else _named_metric_interpretation_query(resident_name, metric) if metric else None
        )
        if interpretation_query:
            return interpretation_query

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

    if _mentions_current_community_reference(new_query):
        return new_query

    if _is_explicit_resident_id_lookup(q_lower):
        return new_query

    if _is_explicit_named_profile_lookup(new_query):
        return new_query

    # Self-contained education questions can contain "it" inside the same
    # sentence ("what is BP and how is it measured?"). Do not treat that as a
    # memory follow-up to the previous resident.
    if _is_self_contained_explanation_query(new_query):
        return new_query

    deterministic_rewrite = _rewrite_exclusion_followup(new_query, chat_history)
    if deterministic_rewrite:
        logger.info(f"Query Refined deterministically: {deterministic_rewrite}")
        return deterministic_rewrite

    deterministic_rewrite = _rewrite_that_room_followup(new_query, chat_history)
    if deterministic_rewrite:
        logger.info(f"Query Refined deterministically: {deterministic_rewrite}")
        return deterministic_rewrite

    deterministic_rewrite = _rewrite_named_set_followup(new_query, chat_history)
    if deterministic_rewrite:
        logger.info(f"Query Refined deterministically: {deterministic_rewrite}")
        return deterministic_rewrite

    deterministic_rewrite = _rewrite_metric_followup_from_recent_context(new_query, chat_history)
    if deterministic_rewrite:
        logger.info(f"Query Refined deterministically: {deterministic_rewrite}")
        return deterministic_rewrite

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
