"""
Guardrails - input validation and output sanitization.
Uses deterministic keyword and regex rules instead of an LLM for reliability.
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
    "device", "sensor", "board", "dev1", "dev2", "dev3", "dev4", "dev5",
    "iot", "hardware", "firmware", "ota", "wifi", "router", "gateway",
    "microcontroller", "esp32", "arduino", "raspberry", "node", "unit",
    "active", "offline", "online", "connected", "connection",
    "resident", "residents", "patient", "patients", "flat", "flats", "age", "ages", "room", "rooms",
    "medical", "history", "histories", "prescribed", "intake", "medication", "medications",
    "doctor", "clinical", "clinician", "nurse", "staff",
    "escalate", "escalated", "escalation", "handoff", "support", "operator",
    "policy", "procedure", "privacy", "security", "sensitive", "hipaa",
    "health", "healthier", "healthy", "healthiest", "unhealthy", "unhealthier", "unhealthiest", "stable", "unstable",
    "report", "bp", "blood pressure",
    "systolic", "diastolic", "sugar", "glucose", "steps", "sleep", "analytics",
    "quality", "duration", "patient", "score", "scores", "vital", "vitals",
    "critical", "attention", "risk", "priority", "prioritize",
    "signal", "uptime", "cpu", "temperature", "moisture", "battery",
    "humidity", "pressure", "voltage", "current", "power", "energy",
    "average", "avg", "sum", "count", "max", "min", "total", "mean",
    "peak", "lowest", "highest", "last", "latest", "historical",
    "location", "zone", "floor", "building", "area", "site", "warehouse",
    "flashing", "error", "reset", "recalibrate", "calibrat", "blink",
    "sleep mode", "e-404", "red light", "green light", "trouble", "broken",
    "fix", "issue", "problem", "fault", "diagnostic", "status",
    "metric", "data", "detail", "details", "info", "information", "profile", "profiles",
    "query", "table", "report", "analytics", "graph", "chart",
    "yesterday", "today", "last hour", "last week", "month", "year",
    "list", "show", "find", "check", "get", "tell", "monitor", "help",
    "care", "context", "question", "follow", "mean",
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


def input_guardrail(query: str) -> bool:
    """
    Input guardrail.
    1. Block injection attempts.
    2. Allow greetings and acknowledgements.
    3. Allow resident lookups phrased with names.
    4. Allow recognized domain keywords.
    5. Block everything else.
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

    if _DOMAIN_KEYWORDS_RE.search(query_lower):
        return True

    if has_relevant_documentation(query):
        logger.info("Query allowed by documentation relevance", extra={"query": query})
        return True

    logger.info("Query blocked: no domain keywords detected", extra={"query": query})
    return False


# ----------------------------
# Output Guardrail
# ----------------------------
_BAD_PHRASES = [
    "system_prompt",
    "you are a strict sql planner",
    "forget previous instructions",
    "you are an ai security guard",
    "you are a query rewriter",
    "you are an intention classifier",
    "select.*from.*device_status",
    "def handle_sql",
    "psycopg2",
    "ollama",
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
