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
    "resident", "residence", "age", "flat", "room", "bp", "sugar", "step", "sleep", "medical", "intake",
    "metric", "report", "analysis", "score", "glucose", "systolic", "diastolic",
    "low", "high", "avg", "average", "sum", "count", "history", "record",
    "older", "younger", "oldest", "youngest",
    "care", "who is", "condition", "overall", "health", "signal", "uptime",
    "cpu", "temperature", "humidity", "pressure", "voltage", "current",
    "power", "energy", "device status",
]
FORCE_SQL_PHRASES = [
    "more than", "less than", "higher than", "lower than",
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
    "resident", "patient", "age", "flat", "room", "history", "intake",
    "report", "metric", "average", "avg", "count", "sum", "highest", "lowest",
    "best", "worst", "most", "least", "top", "bottom", "chart", "graph",
    "compare", "comparison", "details", "detail", "record", "records",
    "more than", "less than", "higher than", "lower than",
]


def _looks_like_resident_lookup(query: str) -> bool:
    if any(_contains_term(query, word) for word in FORCE_RAG_WORDS):
        return False
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

    if _looks_like_generic_explanatory_query(q):
        return "RAG"

    if any(_contains_term(q, word) for word in FORCE_RAG_WORDS):
        return "RAG"

    if any(_contains_term(q, word) for word in FORCE_SQL_WORDS) or any(phrase in q for phrase in FORCE_SQL_PHRASES) or _looks_like_resident_lookup(q):
        return "SQL"

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


def route_query(query: str, original_query: str | None = None, chat_history: list[dict] | None = None) -> dict:
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
        res = handle_sql(query)
        if "error" in res and not any(_contains_term(query.lower(), word) for word in ["iot", "signal", "uptime"]):
            res["answer"] = "I couldn't find matches in the database. Please check the name or ID."
        return res

    logger.info("Routing to RAG...")
    return handle_rag(query)
