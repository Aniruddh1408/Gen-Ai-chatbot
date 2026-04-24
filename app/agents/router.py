"""
Router Agent - Unified intent dispatch and multi-retriever logic.
"""
import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.core.logger import get_logger
from app.llm.client import ask_llm, llm
from app.retrievers.sql_retriever import handle_sql
from app.retrievers.vector_retriever import handle_rag

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
]
FORCE_SQL_WORDS = [
    "resident", "residence", "bp", "sugar", "step", "sleep", "medical", "intake",
    "metric", "report", "analysis", "score", "glucose", "systolic", "diastolic",
    "low", "high", "avg", "average", "sum", "count", "history", "record",
    "less", "more", "than", "older", "younger", "oldest", "youngest",
    "care", "who is", "condition", "overall", "health", "signal", "uptime",
    "cpu", "temperature", "humidity", "pressure", "voltage", "current",
    "power", "energy", "device status",
]
FORCE_CHAT_EXACT = {"hi", "hello", "hey", "help", "thanks", "thank you", "bye"}
FORCE_CHAT_PHRASES = ["what are you", "previous chat", "chat history", "greet yourself"]
SQL_LOOKUP_PHRASES = [
    "details of", "detail of", "information on", "information about",
    "tell me about", "show me details of", "give the details of",
]
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


def _looks_like_resident_lookup(query: str) -> bool:
    if any(_contains_term(query, word) for word in FORCE_RAG_WORDS):
        return False
    if not any(_contains_term(query, phrase) for phrase in SQL_LOOKUP_PHRASES):
        return False
    return _NAME_LOOKUP_RE.search(query) is not None


def classify_intent(query: str) -> str:
    q = query.lower().strip()

    if any(_contains_term(q, word) for word in FORCE_RAG_WORDS):
        return "RAG"

    if any(_contains_term(q, word) for word in FORCE_SQL_WORDS) or _looks_like_resident_lookup(q):
        return "SQL"

    if q in FORCE_CHAT_EXACT or any(_contains_term(q, phrase) for phrase in FORCE_CHAT_PHRASES) or q in ACKNOWLEDGEMENT_WORDS:
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


def route_query(query: str) -> dict:
    intent = classify_intent(query)
    q_lower = query.lower().strip()

    if intent == "CHAT":
        if q_lower in ACKNOWLEDGEMENT_WORDS:
            return {"query": query, "answer": "It was my pleasure to help. Please feel free to ask anything else."}
        if q_lower in GREETING_RESPONSES:
            return {"query": query, "answer": GREETING_RESPONSES[q_lower]}
        try:
            answer = ask_llm(query, system_prompt="You are a Healthcare AI. Answer conversationally.")
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
        res = handle_sql(query)
        if "error" in res and not any(_contains_term(query.lower(), word) for word in ["iot", "signal", "uptime"]):
            res["answer"] = "I couldn't find matches in the database. Please check the name or ID."
        return res

    logger.info("Routing to RAG...")
    return handle_rag(query)
