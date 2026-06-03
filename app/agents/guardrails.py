"""
Guardrails - input validation and output sanitization.
Uses deterministic keyword and regex rules instead of an LLM for reliability.

# Schema-migration notes
This file was written against the legacy schema's vocabulary (device_status,
DEV1/DEV2 board ids, BP/sugar/steps metrics, ESP32/arduino device terms).
The new production schema has none of those tables/columns. The keyword
lists below have been trimmed where keeping a term would just be noise; a
few legacy items remain only because they're harmless allowlist entries
(a query mentioning "device" will still pass the input guardrail and fall
through to the LLM planner, which then returns whatever the schema allows).

# PHI / cross-resident leak check
This keyword guardrail does not itself verify resident names. That backstop
now lives in app/agents/grounding.py: route_query runs foreign_resident_names()
on every LLM-synthesized SQL answer and declines any that asserts a resident
who isn't in the caller's community roster — catching hallucinated names,
wrong-resident answers, and cross-community leakage regardless of phrasing.
Combined with the authorize_community gate and the SQL validator's mandatory
community_id predicate, that closes the previously-documented output gap.
"""
import re

from app.core.logger import get_logger
from app.retrievers.vector_retriever import has_relevant_documentation

logger = get_logger("guardrails")


# ----------------------------
# Input Guardrail (Keyword-Based)
# ----------------------------
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous\s+)?instructions",
    r"forget\s+(everything|all|previous)",
    r"you\s+are\s+now\s+a\s+",
    r"system\s*prompt",
    r"act\s+as\s+(an?\s+)?admin",
    r"override\s+(safety|security|guardrail)",
    r"reveal\s+(your|the)\s+(prompt|instructions)",
    r"what\s+are\s+your\s+instructions",
    r"disregard\s+(all|previous)",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

_DOMAIN_KEYWORDS = [
    # Core entities the new schema actually has columns for.
    "resident", "residents", "patient", "patients",
    "community", "room", "rooms", "flat", "flats",
    "age", "ages", "name", "names",
    "medical", "history", "histories",
    # Conditions matched by _RESIDENT_TEXT_SEARCH_RULES.
    "hypertension", "diabetes", "pre-diabetes", "prediabetes", "arthritis",
    "asthma", "cardiovascular", "cardiac", "osteoporosis", "thyroid",
    "surgery", "post-surgery", "mobility", "chronic",
    # Care staff / clinical vocabulary.
    "doctor", "clinical", "clinician", "nurse", "staff",
    "escalate", "escalated", "escalation", "handoff", "support",
    "policy", "procedure", "privacy", "sensitive", "hipaa",
    # Vitals / sleep / activity / wellness — backed by Phase C sensor seed.
    "vital", "vitals", "hr", "heart rate", "rr", "respiration",
    "sleep", "slept", "sleeping",
    "activity", "active", "walking", "walked",
    "wellness", "score", "scores", "quality", "duration",
    "incident", "incidents", "alert", "alerts",
    "notification", "notifications", "insight", "insights",
    "fall", "fall risk", "out of bed", "out of room", "movement",
    "ambience", "ambient", "temperature", "humidity",
    # General health framing.
    "health", "healthier", "healthy", "healthiest", "unhealthy",
    "unhealthier", "unhealthiest", "stable", "unstable",
    "critical", "attention", "risk", "risks", "priority", "prioritize",
    "unwell", "well", "better", "worse", "poor", "poorest", "concern", "concerns",
    "hydration", "nutrition", "fever", "cholesterol",
    # Aggregations + comparators the LLM planner sees in queries.
    "average", "avg", "sum", "count", "max", "min", "total", "mean",
    "peak", "lowest", "highest", "above", "below", "over", "under",
    "greater", "fewer", "best", "worst", "most", "least", "top", "bottom",
    "fewest", "longest", "shortest", "oldest", "eldest", "youngest",
    "older", "younger", "last", "latest", "historical",
    # Time framing.
    "yesterday", "today", "last hour", "last week", "month", "year",
    # Conversational verbs.
    "list", "show", "find", "check", "get", "tell", "monitor", "help",
    "care", "needs", "need", "requires", "require", "context", "question",
    "follow", "mean",
    # Output framing.
    "report", "graph", "chart", "metric", "data", "detail", "details",
    "info", "information", "profile", "profiles", "summary",
]
_SHORT_GREETING_TERMS = ["hi", "hello", "hey", "help", "ankit", "i am"]


def _term_pattern(term: str) -> str:
    return rf"(?<!\w){re.escape(term)}(?!\w)"


_DOMAIN_KEYWORDS_RE = re.compile(
    "|".join(_term_pattern(keyword) for keyword in _DOMAIN_KEYWORDS),
    re.IGNORECASE,
)
_SHORT_GREETING_RE = re.compile(
    "|".join(_term_pattern(term) for term in _SHORT_GREETING_TERMS),
    re.IGNORECASE,
)
_ACKNOWLEDGEMENT_WORDS = {
    "ok", "okay", "fine", "alright", "got it", "cool", "understood",
    "thanks", "thank you", "noted", "sure", "yep", "yes",
}
_RESIDENT_LOOKUP_PATTERNS = [
    r"\b(?:give|show|tell|find|get)\b.*\b(?:details?|detail|record|history|information|info)\b.*\b(?:of|for|about)\b\s+[a-z]+(?:\s+[a-z]+){1,2}\b",
    r"\b(?:details?|detail|record|history|information|info)\b\s+(?:of|for)\s+[a-z]+(?:\s+[a-z]+){1,2}\b",
    r"\b(?:tell|show|give)\s+me\s+about\s+[a-z]+(?:\s+[a-z]+){1,2}\b",
    r"\bwho\s+is\s+[a-z]+(?:\s+[a-z]+){1,2}\b",
    r"\b(?:h?ow)\s+old\s+is\s+(?:resident\s+|patient\s+)?[a-z]+(?:\s+[a-z]+){1,2}\b",
    r"\b(?:what\s+is\s+)?(?:the\s+)?age\s+of\s+(?:resident\s+|patient\s+)?[a-z]+(?:\s+[a-z]+){1,2}\b",
    r"\b(?:where\s+(?:does|is))\s+(?:resident\s+|patient\s+)?[a-z]+(?:\s+[a-z]+){1,2}\s+(?:stay|staying|live|living|assigned)\b",
    r"\b(?:what|which)\s+(?:flat|room)(?:\s+(?:number|no))?\s+(?:is|does)\s+(?:resident\s+|patient\s+)?[a-z]+(?:\s+[a-z]+){1,2}(?:\s+(?:in|have|has))?\b",
]
_RESIDENT_LOOKUP_RE = re.compile("|".join(_RESIDENT_LOOKUP_PATTERNS), re.IGNORECASE)

_DOMAIN_QUERY_PATTERNS = [
    r"\bwho\s+(?:slept|walked|fell|fallen)\b",
    r"\bwho\s+(?:needs?|requires?|should\s+get)\b.*\b(?:care|attention|monitoring|support|priority)\b",
    r"\b(?:which|who)\b.*\b(?:healthiest|unhealthiest|oldest|eldest|youngest|longest|shortest)\b",
    # Superlatives + metrics the new schema can actually answer for
    # (hr / rr from vitals, sleep_sessions, wellness_metrics.score).
    r"\b(?:highest|lowest|best|worst|most|least|top|bottom|fewest)\b.*\b(?:hr|heart rate|rr|respiration|sleep|score|duration|wellness)\b",
    r"\b(?:hr|heart rate|rr|respiration|sleep|slept|vitals?|wellness)\b.*\b(?:highest|lowest|best|worst|most|least|average|avg|mean|longest|shortest)\b",
]
_DOMAIN_QUERY_RE = re.compile("|".join(_DOMAIN_QUERY_PATTERNS), re.IGNORECASE)

_GENERAL_MEDICAL_QUESTION_RE = re.compile(
    r"\b(?:what\s+(?:is|are)|explain|define|meaning\s+of|how\s+(?:does|do)|"
    r"how\s+(?:is|are|can|should|to)|why\s+(?:does|do|is|are)|"
    r"side\s+effects?|uses?\s+of|benefits?\s+of|risks?\s+of)\b"
    # The condition list still matches resident_profile.medical_history
    # values; general drug terms are kept as no-ops because the new schema
    # has no medical_intake_prescribed column to look them up in (queries
    # mentioning them fall through to the LLM and get a polite "no data").
    r".*\b(?:arthritis|asthma|cardiac|cardiovascular|cholesterol|diabetes|"
    r"fever|heart|hypertension|osteoporosis|pre-diabetes|prediabetes|stroke|"
    r"symptoms?|thyroid|vitals?|sleep|insomnia|fall|medication|medicine)\b",
    re.IGNORECASE,
)


def input_guardrail(query: str) -> bool:
    """
    Input guardrail.
    1. Block injection attempts.
    2. Allow greetings, acknowledgements, KuboCare domain queries, and general chat.
    3. Let the router decide whether the allowed query should use SQL, RAG, or normal chat.
    """
    if not query or not query.strip():
        return False

    query_lower = query.lower().strip()

    if _INJECTION_RE.search(query_lower):
        logger.info("Query blocked by injection detection", extra={"query": query})
        return False

    if len(query_lower.split()) <= 5 and _SHORT_GREETING_RE.search(query_lower):
        return True

    if query_lower in _ACKNOWLEDGEMENT_WORDS:
        return True

    if _RESIDENT_LOOKUP_RE.search(query_lower):
        return True

    if _GENERAL_MEDICAL_QUESTION_RE.search(query_lower):
        return True

    if _DOMAIN_QUERY_RE.search(query_lower):
        return True

    if _DOMAIN_KEYWORDS_RE.search(query_lower):
        return True

    if has_relevant_documentation(query):
        logger.info("Query allowed by documentation relevance", extra={"query": query})
        return True

    logger.info("Query allowed by general chat fallback", extra={"query": query})
    return True


# ----------------------------
# Output Guardrail
# ----------------------------
_BAD_PHRASES = [
    # Prompt-leak signatures (verbatim opening lines of internal prompts).
    "system_prompt",
    "you are a strict sql planner",
    "forget previous instructions",
    "you are an ai security guard",
    "you are a query rewriter",
    "you are an intention classifier",
    # Backend internal leaks.
    "def handle_sql",
    "psycopg2",
    "ollama",
    # Schema-leak signatures. The community-scope predicate is forced by
    # the SQL validator on every internal query; if it ever surfaces in
    # output, something is leaking the assembled SQL.
    "rm.community_id = %s",
    "resident_profile.dob::date",
]
_BAD_PATTERN = re.compile("|".join(_BAD_PHRASES), re.IGNORECASE)


def output_guardrail(answer_text: str) -> str:
    """Basic output guardrail for prompt leaks and obvious backend internals."""
    if not answer_text or not isinstance(answer_text, str):
        return "No response generated."

    if _BAD_PATTERN.search(answer_text):
        logger.warning("Response blocked by output guardrail", extra={"answer_snippet": answer_text[:200]})
        return "Security Alert: Response blocked by output guardrails."

    if len(answer_text.strip()) < 5:
        return "I could not generate a meaningful response. Please rephrase your question."

    return answer_text
