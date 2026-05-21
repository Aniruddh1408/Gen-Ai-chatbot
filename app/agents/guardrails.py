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
    "device", "devices", "sensor", "sensors", "board", "boards", "telemetry",
    "dev1", "dev2", "dev3", "dev4", "dev5",
    "iot", "hardware", "firmware", "ota", "wifi", "router", "gateway",
    "microcontroller", "esp32", "arduino", "raspberry", "node", "unit",
    "active", "offline", "online", "connected", "connection",
    "resident", "residents", "patient", "patients", "flat", "flats", "age", "ages", "room", "rooms",
    "medical", "history", "histories", "prescribed", "intake", "medication", "medications",
    "hypertension", "diabetes", "pre-diabetes", "prediabetes", "arthritis", "asthma",
    "cardiovascular", "cardiac", "osteoporosis", "thyroid", "surgery", "post-surgery",
    "mobility", "chronic", "metformin", "amlodipine", "paracetamol", "salbutamol",
    "atorvastatin", "aspirin", "calcium", "vitamin", "telmisartan", "levothyroxine",
    "multivitamin",
    "doctor", "clinical", "clinician", "nurse", "staff",
    "escalate", "escalated", "escalation", "handoff", "support", "operator",
    "policy", "procedure", "privacy", "security", "sensitive", "hipaa",
    "wellness", "handover", "shift handoff", "fall", "fall risk",
    "hydration", "nutrition", "stale", "timestamp", "freshness",
    "duplicate", "conflicting", "manual entry", "traceability",
    "health", "healthier", "healthy", "healthiest", "unhealthy", "unhealthier", "unhealthiest", "stable", "unstable",
    "report", "bp", "blood pressure",
    "systolic", "diastolic", "sugar", "glucose", "step", "steps", "walked", "walking",
    "sleep", "slept", "analytics",
    "quality", "duration", "patient", "score", "scores", "vital", "vitals",
    "critical", "attention", "risk", "risks", "priority", "prioritize",
    "unwell", "well", "better", "worse", "poor", "poorest", "concern", "concerns",
    "signal", "uptime", "cpu", "temperature", "moisture", "battery",
    "humidity", "pressure", "voltage", "current", "power", "energy",
    "average", "avg", "sum", "count", "max", "min", "total", "mean",
    "peak", "lowest", "highest", "above", "below", "over", "under", "greater", "fewer",
    "best", "worst", "most", "least", "top", "bottom",
    "fewest", "longest", "shortest", "oldest", "eldest", "youngest", "older",
    "younger", "last", "latest", "historical",
    "location", "zone", "floor", "building", "area", "site", "warehouse",
    "flashing", "error", "reset", "recalibrate", "calibrat", "blink",
    "sleep mode", "e-404", "red light", "green light", "trouble", "broken",
    "fix", "issue", "problem", "fault", "diagnostic", "status",
    "metric", "data", "detail", "details", "info", "information", "profile", "profiles",
    "query", "table", "report", "analytics", "graph", "chart",
    "yesterday", "today", "last hour", "last week", "month", "year",
    "list", "show", "find", "check", "get", "tell", "monitor", "help",
    "care", "needs", "need", "requires", "require", "context", "question", "follow", "mean",
    "antibiotic", "cholesterol", "fever", "heart", "insulin", "medicine",
    "stroke", "symptom", "symptoms", "tablet",
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
    r"\bwho\s+(?:slept|walked)\b",
    r"\bwho\s+(?:needs?|requires?|should\s+get)\b.*\b(?:care|attention|monitoring|support|priority)\b",
    r"\b(?:which|who)\b.*\b(?:healthiest|unhealthiest|oldest|eldest|youngest|longest|shortest)\b",
    r"\b(?:highest|lowest|best|worst|most|least|top|bottom|fewest)\b.*\b(?:bp|blood pressure|sugar|glucose|steps?|sleep|score|duration|uptime|signal|cpu)\b",
    r"\b(?:bp|blood pressure|sugar|glucose|steps?|sleep|slept|vitals?)\b.*\b(?:highest|lowest|best|worst|most|least|average|avg|mean|longest|shortest)\b",
    r"\bdev[0-9]+\b",
]
_DOMAIN_QUERY_RE = re.compile("|".join(_DOMAIN_QUERY_PATTERNS), re.IGNORECASE)

_GENERAL_MEDICAL_QUESTION_RE = re.compile(
    r"\b(?:what\s+(?:is|are)|explain|define|meaning\s+of|how\s+(?:does|do)|"
    r"how\s+(?:is|are|can|should|to)|why\s+(?:does|do|is|are)|"
    r"side\s+effects?|uses?\s+of|benefits?\s+of|risks?\s+of)\b"
    r".*\b(?:amlodipine|aspirin|atorvastatin|calcium|levothyroxine|metformin|"
    r"multivitamin|paracetamol|salbutamol|telmisartan|antibiotic|inhaler|"
    r"insulin|medicine|medication|tablet|arthritis|asthma|blood pressure|bp|"
    r"cardiac|cardiovascular|cholesterol|diabetes|fever|glucose|heart|"
    r"hypertension|osteoporosis|pre-diabetes|prediabetes|stroke|sugar|"
    r"symptoms?|thyroid|vitals?)\b",
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
