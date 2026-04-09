"""
Router Agent — Intent classification and multi-retriever dispatch.
Uses LangChain chain for reliable intent routing.
"""
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.retrievers.sql_retriever import handle_sql
from app.retrievers.vector_retriever import handle_rag
from app.llm.client import llm
from app.core.logger import get_logger

logger = get_logger("router")


# ----------------------------
# Intent Classification Chain
# ----------------------------
_classify_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an Intention Classifier Router for an IoT Analytics Architecture.
Determine if this query requires SQL Database Metrics OR Vector Documentation.
Output EXACTLY one word: 'SQL' or 'RAG'. Do not explain.

Examples:
- What is the average signal for board dev1?: SQL
- Why is my device flashing red?: RAG
- Show me the uptime for room1: SQL
- How do I reset the moisture sensor?: RAG
- What is the CPU usage for all devices yesterday?: SQL
- Error code E-404 on my device: RAG"""),
    ("human", "{query}"),
])

_classify_chain = _classify_prompt | llm | StrOutputParser()


def classify_intent(query: str) -> str:
    """
    INPUT GUARDRAIL & MULTI-RETRIEVER ROUTER
    Determines via LLM chain which system is most appropriate.
    """
    try:
        answer = _classify_chain.invoke({"query": query}).strip().upper()
        intent = "SQL" if "SQL" in answer else "RAG"
    except Exception as e:
        logger.error(f"Intent classification failed: {e}, defaulting to RAG")
        intent = "RAG"

    logger.info(f"Intent classified as: {intent}", extra={"query": query})
    return intent


def route_query(query: str) -> dict:
    """Route the query to the appropriate retriever based on intent classification."""
    intent = classify_intent(query)

    if intent == "SQL":
        logger.info("Dispatching to SQL Database Retriever...")
        sql_response = handle_sql(query)

        # --- FALLBACK LOGIC ---
        # Detect if SQL crashes or returns [[None]]
        is_empty = not sql_response.get("result") or sql_response.get("result") == [[None]]

        if "error" in sql_response or is_empty:
            reason = "SQL syntax/execution failed" if "error" in sql_response else "No exact metrics found in tables"
            logger.info(f"SQL Retriever aborted ({reason}). Falling back to Vector RAG...")

            fallback_response = handle_rag(query)
            fallback_response["fallback_reason"] = reason

            # Surface exactly WHY it fell back for debugging
            if "error" in sql_response:
                fallback_response["sql_error"] = sql_response.get("details", sql_response.get("error"))
                fallback_response["failed_plan"] = sql_response.get("plan", sql_response.get("raw"))

            return fallback_response

        return sql_response

    # Direct RAG for documentation/troubleshooting queries
    logger.info("Dispatching directly to Vector RAG Retriever...")
    return handle_rag(query)