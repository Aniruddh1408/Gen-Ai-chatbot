"""
Router Agent - Unified intent dispatch and multi-retriever logic.
"""
import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.logger import get_logger
from app.llm.client import ask_llm, llm
from app.retrievers.sql_retriever import handle_sql
from app.retrievers.vector_retriever import handle_rag, has_relevant_documentation

logger = get_logger("router")


def _contains_term(text: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE) is not None

_classify_prompt = ChatPromptTemplate.from_messages([
    ("system", """Determine query intent: SQL, RAG, or CHAT.
- SQL: Metrics, residents, health data, comparisons.
- RAG: Documentation, manuals, troubleshooting.
- CHAT: Greetings, chat history, system info, general talk.
Output one word only."""),
    ("human", "{query}"),
])

_classify_chain = _classify_prompt | llm | StrOutputParser()

# Heuristics for reliability
FORCE_RAG_WORDS = [
    "manual", "documentation", "document", "troubleshoot", "troubleshooting",
    "firmware", "ota", "wifi", "router", "gateway", "reset", "recalibrate",
    "calibration", "flashing", "blink", "blinking", "red light", "green light",
    "error code", "e-404", "sleep mode", "companion app",
    "escalate", "escalated", "escalation", "clinical staff", "technical staff",
    "privacy", "security", "policy", "procedure", "handoff",
    "blood pressure review", "sugar level review", "sleep quality review",
    "activity review", "step count review", "combined metric review",
    "data freshness", "stale timestamp", "daily wellness review",
    "shift handoff", "medication intake documentation", "fall risk review",
    "reduced mobility follow-up", "hydration and nutrition", "missing health readings",
    "duplicate readings", "conflicting readings", "manual entry", "device reading",
    "safe language", "safe health summary", "traceability",
]
FORCE_RAG_UNAMBIGUOUS_WORDS = [
    "manual", "documentation", "document", "troubleshoot", "troubleshooting",
    "firmware", "ota", "wifi", "router", "gateway", "reset", "recalibrate",
    "calibration", "flashing", "blink", "blinking", "red light", "green light",
    "error code", "e-404", "sleep mode", "companion app",
    "privacy", "security", "policy", "procedure", "handoff",
    "blood pressure review", "sugar level review", "sleep quality review",
    "activity review", "step count review", "combined metric review",
    "data freshness", "stale timestamp", "daily wellness review",
    "shift handoff", "medication intake documentation", "fall risk review",
    "reduced mobility follow-up", "hydration and nutrition", "missing health readings",
    "duplicate readings", "conflicting readings", "manual entry", "device reading",
    "safe language", "safe health summary", "traceability",
]
FORCE_SQL_WORDS = [
    "resident", "residents", "patient", "patients", "residence", "age", "ages", "flat", "flats",
    "room", "rooms", "bp", "sugar", "step", "steps", "sleep", "slept", "medical", "intake",
    "prescribed", "prescription", "prescriptions", "treatment", "medication", "medications",
    "hypertension", "diabetes", "pre-diabetes", "prediabetes", "arthritis", "asthma",
    "cardiovascular", "cardiac", "osteoporosis", "thyroid", "surgery", "post-surgery",
    "mobility", "chronic", "metformin", "amlodipine", "paracetamol", "salbutamol",
    "atorvastatin", "aspirin", "calcium", "vitamin", "telmisartan", "levothyroxine",
    "multivitamin",
    "metric", "report", "analysis", "score", "scores", "glucose", "systolic", "diastolic",
    "low", "high", "avg", "average", "sum", "count", "history", "histories",
    "record", "records", "detail", "details", "info", "information", "profile", "profiles",
    "older", "younger", "oldest", "eldest", "youngest", "longest", "shortest",
    "care", "priority", "prioritize", "risk", "risks", "critical", "attention",
    "healthy", "healthier", "healthy", "healthiest", "unhealthy", "unhealthier", "unhealthiest", "stable", "unstable",
    "vital", "vitals", "who is", "signal", "uptime",
    "cpu", "processor", "load", "temperature", "humidity", "pressure", "voltage", "current",
    "power", "energy", "device", "devices", "board", "boards", "telemetry", "device status",
]
FORCE_SQL_PHRASES = [
    "more than", "less than", "higher than", "lower than", "greater than",
    "fewer than", "above", "below", "over", "under", "at least", "at most",
    "more care", "most care", "less care", "least care", "needs care", "need care",
    "more acre", "most acre", "less acre", "least acre",
    "requires care", "require care", "requires more care", "requires less care",
    "requires more acre", "requires less acre",
    "highest care", "highest priority", "lowest care", "lowest priority",
    "care priority", "overall health", "health metrics", "health risk",
    "risk score", "needs attention", "need attention", "vital signs",
    "most healthy", "healthiest resident", "not healthy", "least healthy",
    "unhealthy resident", "unhealthiest resident", "most unhealthy", "best health", "worst health",
    "poorest health", "poor health", "most stable", "least stable",
    "lowest risk", "highest risk", "most at risk",
]
FORCE_CHAT_EXACT = {"hi", "hello", "hey", "help", "thanks", "thank you", "bye"}
FORCE_CHAT_PHRASES = ["what are you", "previous chat", "chat history", "greet yourself"]
FORCE_CHAT_PREFIXES = [
    "what is", "what are", "explain", "define", "meaning of",
    "how does", "how do", "why does", "why is",
]
SQL_LOOKUP_PHRASES = [
    "details of", "detail of", "information on", "information about",
    "tell me about", "show me details of", "give the details of",
]
AGE_LOOKUP_RE = re.compile(
    r"\b(?:(?:h?ow)\s+old\s+is|(?:what\s+is\s+)?(?:the\s+)?age\s+of)\s+"
    r"(?:resident\s+|patient\s+)?[a-z]+(?:\s+[a-z]+){1,2}\b",
    re.IGNORECASE,
)
ROOM_LOOKUP_RE = re.compile(
    r"\b(?:(?:where\s+(?:does|is))\s+(?:resident\s+|patient\s+)?"
    r"[a-z]+(?:\s+[a-z]+){1,2}\s+(?:stay|staying|live|living|assigned)|"
    r"(?:what|which)\s+(?:flat|room)(?:\s+(?:number|no))?\s+(?:is|does)\s+"
    r"(?:resident\s+|patient\s+)?[a-z]+(?:\s+[a-z]+){1,2}(?:\s+(?:in|have|has))?)\b",
    re.IGNORECASE,
)
DEVICE_ID_RE = re.compile(r"\bdev[1-5]\b", re.IGNORECASE)
ACKNOWLEDGEMENT_WORDS = [
    "ok", "okay", "fine", "alright", "got it", "cool", "understood",
    "thanks", "thank you", "noted", "sure", "yep", "yes",
]
GREETING_RESPONSES = {
    "hi": "Hello. Ask about residents, health metrics, or device issues.",
    "hello": "Hello. Ask about residents, health metrics, or device issues.",
    "hey": "Hello. Ask about residents, health metrics, or device issues.",
    "help": "Ask about resident metrics, summaries, charts, or device troubleshooting.",
}

_NAME_LOOKUP_RE = re.compile(r"\b[a-z]+(?:\s+[a-z]+){1,2}\b")

_GENERIC_EXPLANATION_SQL_BLOCKERS = [
    "resident", "residents", "patient", "patients", "age", "ages", "flat", "flats", "room", "rooms",
    "history", "histories", "intake", "prescribed", "prescription", "prescriptions",
    "treatment", "medication", "medications",
    "report", "metric", "average", "avg", "count", "sum", "highest", "lowest",
    "best", "worst", "most", "least", "top", "bottom", "chart", "graph",
    "bp", "blood pressure", "sugar", "glucose", "steps", "step", "sleep", "slept",
    "score", "scores", "quality", "duration", "systolic", "diastolic",
    "oldest", "eldest", "youngest", "longest", "shortest",
    "care", "priority", "prioritize", "risk", "risks", "health metrics",
    "critical", "attention", "healthy", "healthiest", "unhealthy", "unhealthiest",
    "stable", "unstable", "vital", "vitals", "vital signs",
    "compare", "comparison", "details", "detail", "record", "records",
    "more than", "less than", "higher than", "lower than",
]
_DOC_ROUTING_DISTANCE = 0.93
_METRIC_CONCEPT_RE = re.compile(
    r"^\s*(?:what\s+(?:is|are|does)|explain|define|meaning\s+of)\s+"
    r"(?:the\s+)?(?:sleep\s+quality\s+score|sleep\s+score|blood\s+pressure|bp|"
    r"sugar\s+level|glucose\s+level|step\s+count|activity\s+steps|sleep\s+duration)"
    r"(?:\s+mean)?\??\s*$",
    re.IGNORECASE,
)


def _looks_like_resident_lookup(query: str) -> bool:
    if any(_contains_term(query, word) for word in FORCE_RAG_WORDS):
        return False
    if AGE_LOOKUP_RE.search(query) or ROOM_LOOKUP_RE.search(query):
        return True
    if not any(_contains_term(query, phrase) for phrase in SQL_LOOKUP_PHRASES):
        return False
    return _NAME_LOOKUP_RE.search(query) is not None


def _looks_like_generic_explanatory_query(query: str) -> bool:
    q = query.lower().strip()
    if not any(q.startswith(prefix) for prefix in FORCE_CHAT_PREFIXES):
        return False
    if _looks_like_resident_lookup(q):
        return False
    for hint in _GENERIC_EXPLANATION_SQL_BLOCKERS:
        if " " in hint:
            if hint in q:
                return False
        elif _contains_term(q, hint):
            return False
    return True


def _looks_like_clear_sql_query(query: str) -> bool:
    q = query.lower().strip()
    if DEVICE_ID_RE.search(q):
        return True
    if AGE_LOOKUP_RE.search(q) or ROOM_LOOKUP_RE.search(q):
        return True
    if any(phrase in q for phrase in FORCE_SQL_PHRASES):
        return True
    if _looks_like_resident_lookup(q):
        return True
    return any(_contains_term(q, word) for word in FORCE_SQL_WORDS)


def _looks_like_unambiguous_documentation_query(query: str) -> bool:
    return any(_contains_term(query, word) for word in FORCE_RAG_UNAMBIGUOUS_WORDS)


def _looks_like_metric_concept_query(query: str) -> bool:
    return _METRIC_CONCEPT_RE.search(query) is not None


def _format_chat_history(chat_history: list[dict] | None, limit: int = 3) -> str:
    if not chat_history:
        return ""

    recent_turns = chat_history[-limit:]
    return "\n".join(
        f"User: {turn.get('user', '')}\nAssistant: {turn.get('ai', '')}"
        for turn in recent_turns
    ).strip()


def classify_intent(query: str) -> str:
    q = query.lower().strip()

    if q in FORCE_CHAT_EXACT or any(_contains_term(q, phrase) for phrase in FORCE_CHAT_PHRASES) or q in ACKNOWLEDGEMENT_WORDS:
        return "CHAT"

    # Hard documentation phrases win first so "sleep mode" is not treated as a
    # resident sleep metric.
    if _looks_like_unambiguous_documentation_query(q):
        return "RAG"

    if _looks_like_metric_concept_query(q):
        return "RAG"

    # Data questions win before generic "what is / who is" handling. This keeps
    # resident follow-ups such as "what are their ages?" in SQL.
    if _looks_like_clear_sql_query(q):
        return "SQL"

    if _looks_like_generic_explanatory_query(q):
        return "RAG"

    if any(_contains_term(q, word) for word in FORCE_RAG_WORDS):
        return "RAG"

    if has_relevant_documentation(query, max_distance=_DOC_ROUTING_DISTANCE):
        return "RAG"

    if any(q.startswith(prefix) for prefix in FORCE_CHAT_PREFIXES):
        return "CHAT"

    try:
        ans = _classify_chain.invoke({"query": query}).strip().upper()
        if "SQL" in ans:
            return "SQL"
        if "CHAT" in ans:
            return "CHAT"
        return "RAG"
    except Exception:
        return "SQL"


def route_query(
    query: str,
    original_query: str | None = None,
    chat_history: list[dict] | None = None,
    *,
    community_id: int,
) -> dict:
    intent = classify_intent(query)
    raw_query = (original_query or query).strip()
    q_lower = raw_query.lower().strip()

    if intent == "CHAT":
        if q_lower in ACKNOWLEDGEMENT_WORDS:
            return {"query": query, "answer": "It was my pleasure to help. Please feel free to ask anything else."}
        if q_lower in GREETING_RESPONSES:
            return {"query": query, "answer": GREETING_RESPONSES[q_lower]}
        try:
            history_text = _format_chat_history(chat_history)
            chat_input = raw_query
            if history_text:
                chat_input = f"Recent Conversation:\n{history_text}\n\nCurrent User Message: {raw_query}"

            answer = ask_llm(
                chat_input,
                system_prompt=(
                    "You are a Healthcare AI. Use the recent conversation to resolve follow-up messages naturally. "
                    "Answer clearly and concisely by default. For simple questions, keep the answer to 2-4 sentences "
                    "unless the user asks for detail. If the current message is too vague and the recent context does "
                    "not clearly determine the topic, ask a short clarification question."
                ),
            )
            return {"query": query, "answer": answer}
        except Exception as e:
            logger.error(f"Chat response failed: {e}")
            return {
                "query": query,
                "error": str(e),
                "answer": "The language model is taking too long to respond. Please try again shortly.",
            }

    if intent == "SQL":
        logger.info("Routing to SQL...")
        res = handle_sql(query, community_id=community_id)
        if "error" in res and not any(_contains_term(query.lower(), word) for word in ["iot", "signal", "uptime"]):
            res["answer"] = "I couldn't find matches in the database. Please check the name or ID."
        return res

    logger.info("Routing to RAG...")
    return handle_rag(query)
