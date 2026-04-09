"""
Guardrails — Input validation and output sanitization.
Uses deterministic keyword/regex rules instead of LLM for reliability.
The small qwen2:1.5b model is too inconsistent for binary classification tasks.
"""
import re
from app.core.logger import get_logger

logger = get_logger("guardrails")


# ----------------------------
# Input Guardrail (Keyword-Based)
# ----------------------------

# Injection patterns — queries matching these are ALWAYS blocked
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous\s+)?instructions",
    r"forget\s+(everything|all|previous)",
    r"you\s+are\s+now\s+a\s+",  # More specific than just 'you are now'
    r"system\s*prompt",
    r"act\s+as\s+(an?\s+)?admin",
    r"override\s+(safety|security|guardrail)",
    r"reveal\s+(your|the)\s+(prompt|instructions)",
    r"what\s+are\s+your\s+instructions",
    r"disregard\s+(all|previous)",
]
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

# IoT-related keywords — if a query contains ANY of these, it's likely valid
_IOT_KEYWORDS = [
    # Device & hardware terms
    "device", "sensor", "board", "dev1", "dev2", "dev3", "dev4", "dev5",
    "iot", "hardware", "firmware", "ota", "wifi", "router", "gateway",
    "microcontroller", "esp32", "arduino", "raspberry", "node", "unit",
    "active", "offline", "online", "connected", "connection",
    # Metrics & analytics terms
    "signal", "uptime", "cpu", "temperature", "moisture", "battery",
    "humidity", "pressure", "voltage", "current", "power", "energy",
    "average", "avg", "sum", "count", "max", "min", "total", "mean",
    "peak", "lowest", "highest", "last", "latest", "historical",
    # Location terms
    "room", "location", "zone", "floor", "building", "area", "site", "warehouse",
    # Troubleshooting terms
    "flashing", "error", "reset", "recalibrate", "calibrat", "blink",
    "sleep mode", "e-404", "red light", "green light", "trouble", "broken",
    "fix", "issue", "problem", "fault", "diagnostic", "status", "health",
    # Database/analytics terms
    "metric", "data", "query", "table", "report", "analytics", "graph", "chart",
    "yesterday", "today", "last hour", "last week", "month", "year",
    # Common conversational IoT helpers
    "list", "show", "find", "check", "get", "tell", "monitor", "help",
]
_IOT_KEYWORDS_RE = re.compile("|".join(re.escape(k) for k in _IOT_KEYWORDS), re.IGNORECASE)


def input_guardrail(query: str) -> bool:
    """
    INPUT GUARDRAIL — Deterministic keyword-based approach.
    1. Block injection attempts (regex blacklist)
    2. Allow if IoT keywords are present (keyword whitelist)
    3. Block everything else (safe default)
    """
    if not query or not query.strip():
        return False

    query_lower = query.lower().strip()

    # Step 1: Check for injection attacks — ALWAYS block
    if _INJECTION_RE.search(query_lower):
        logger.info("Query blocked by injection detection", extra={"query": query})
        return False

    # Step 2: Conversational flexibility — ALLOW very short greetings or "help"
    # This allows the LLM to handle basic social context or explain its purpose.
    if len(query_lower.split()) <= 2 and any(w in query_lower for w in ["hi", "hello", "hey", "help", "who", "what"]):
        return True

    # Step 3: Check for IoT-related keywords — ALLOW if found
    if _IOT_KEYWORDS_RE.search(query_lower):
        return True

    # Step 4: No IoT keywords found — block as off-topic
    logger.info("Query blocked: no IoT keywords detected", extra={"query": query})
    return False


# ----------------------------
# Output Guardrail
# ----------------------------
# Expanded list of phrases that should never leak into user responses
_BAD_PHRASES = [
    "system_prompt",
    "you are a strict sql planner",
    "forget previous instructions",
    "you are an ai security guard",
    "you are a query rewriter",
    "you are an intention classifier",
    "select.*from.*device_status",  # raw SQL leaking
    "def handle_sql",               # source code leaking
    "psycopg2",                     # backend internals
    "ollama",                       # infra internals
]

# Compiled regex for output scanning (case-insensitive)
_BAD_PATTERN = re.compile("|".join(_BAD_PHRASES), re.IGNORECASE)


def output_guardrail(answer_text: str) -> str:
    """
    OUTPUT GUARDRAIL
    A heuristic + regex check to verify that the generated LLM response hasn't
    fallen into catastrophic hallucination, prompt leaking, or exposed backend internals.
    """
    if not answer_text or not isinstance(answer_text, str):
        return "No response generated."

    if _BAD_PATTERN.search(answer_text):
        logger.warning("Response blocked by output guardrail", extra={"answer_snippet": answer_text[:200]})
        return "Security Alert: Response blocked by output guardrails."

    # Check for suspiciously short or empty answers
    if len(answer_text.strip()) < 5:
        return "I could not generate a meaningful response. Please rephrase your question."

    return answer_text
