"""
Router Agent — Unified Intent Dispatch and Multi-Retriever Logic.
"""
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.retrievers.sql_retriever import handle_sql
from app.retrievers.vector_retriever import handle_rag
from app.llm.client import llm, ask_llm
from app.core.logger import get_logger

logger = get_logger("router")

# ----------------------------
# 1. Intent Classification
# ----------------------------
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
FORCE_SQL_WORDS = [
    "resident", "residence", "bp", "sugar", "step", "sleep", "medical", "intake", 
    "metric", "report", "analysis", "score", "glucose", "systolic", "diastolic",
    "low", "high", "avg", "average", "sum", "count", "history", "record", 
    "less", "more", "than", "older", "younger", "oldest", "youngest"
]
FORCE_CHAT_WORDS = ["chat", "previous", "who are you", "hi", "hello", "hey", "help", "greet", "thanks", "bye"]

def classify_intent(query: str) -> str:
    q = query.lower()
    
    # 1. PRIORITY 1: Force SQL (Healthcare/Metrics)
    if any(w in q for w in FORCE_SQL_WORDS): 
        return "SQL"
    
    # 2. PRIORITY 2: Force Chat (Greetings/Social)
    if any(w in q for w in FORCE_CHAT_WORDS): 
        return "CHAT"
    
    # 3. PRIORITY 3: LLM Classification Fallback
    try:
        ans = _classify_chain.invoke({"query": query}).strip().upper()
        if "SQL" in ans: return "SQL"
        if "CHAT" in ans: return "CHAT"
        return "RAG"
    except:
        return "SQL" # Default to SQL for safest clinical coverage

# ----------------------------
# 2. Main Router
# ----------------------------
def route_query(query: str) -> dict:
    intent = classify_intent(query)
    
    if intent == "CHAT":
        answer = ask_llm(query, system_prompt="You are a Healthcare AI. Answer conversationally.")
        return {"query": query, "answer": answer}

    if intent == "SQL":
        logger.info("Routing to SQL...")
        res = handle_sql(query)
        # Prevent irrelevant fallbacks
        if "error" in res and not any(w in query.lower() for w in ["iot", "signal", "uptime"]):
             res["answer"] = "I couldn't find matches in the database. Please check the name or ID."
        return res

    logger.info("Routing to RAG...")
    return handle_rag(query)