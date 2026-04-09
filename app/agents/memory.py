"""
Memory — Conversational query rewriter using LangChain.
Rewrites follow-up questions into standalone queries using chat history context.
Provides session-based in-memory history storage.
"""
from collections import defaultdict
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.llm.client import llm
from app.core.logger import get_logger

logger = get_logger("memory")

# ----------------------------
# In-memory session store
# ----------------------------
# Maps session_id -> list of {"user": ..., "ai": ...} dicts
# In production, swap this for Redis or a Postgres table.
_session_store: dict[str, list[dict]] = defaultdict(list)

MAX_HISTORY_TURNS = 5  # Sliding window to prevent token overflow


def get_history(session_id: str) -> list[dict]:
    """Retrieve the chat history for a session."""
    return _session_store.get(session_id, [])


def add_turn(session_id: str, user_msg: str, ai_msg: str):
    """Append a turn to the session history, enforcing the sliding window."""
    _session_store[session_id].append({"user": user_msg, "ai": ai_msg})
    # Trim to last N turns
    if len(_session_store[session_id]) > MAX_HISTORY_TURNS:
        _session_store[session_id] = _session_store[session_id][-MAX_HISTORY_TURNS:]


def clear_history(session_id: str):
    """Clear the chat history for a session."""
    _session_store.pop(session_id, None)


# ----------------------------
# Query Rewriter Chain
# ----------------------------
_rewrite_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a Query Rewriter.
Your ONLY job is to rewrite the User's New Query into a standalone sentence using the context of the Chat History.
DO NOT ANSWER THE QUESTION. DO NOT PROVIDE TROUBLESHOOTING ADVICE.
ONLY OUTPUT THE REWRITTEN QUERY.

Example 1:
History:
User: What is the signal for dev1?
AI: The signal is 50.
TARGET QUERY TO REWRITE: Can you graph that for room2?
Your Output: What is the signal for dev1 in room2?

Example 2:
History:
User: My device is flashing red.
AI: Do not restart it.
TARGET QUERY TO REWRITE: Why not?
Your Output: Why shouldn't I manually restart the flashing red device?

CHAT HISTORY TO EVALUATE:
{history_text}

TARGET QUERY TO REWRITE: {new_query}
Your Output:"""),
    ("human", "Rewrite the query strictly based on instructions."),
])

_rewrite_chain = _rewrite_prompt | llm | StrOutputParser()


def rewrite_query_with_memory(session_id: str, new_query: str) -> str:
    """
    QUERY REWRITER AGENT (Memory Context)
    Rewrites a conversational follow-up into a standalone query using session history.
    Returns the original query if there's no history.
    """
    chat_history = get_history(session_id)

    if not chat_history:
        return new_query

    history_text = "\n".join([f"User: {msg['user']}\nAI: {msg['ai']}" for msg in chat_history])

    try:
        rewritten = _rewrite_chain.invoke({
            "history_text": history_text,
            "new_query": new_query,
        }).strip()
        logger.info("Query rewritten", extra={"original": new_query, "rewritten": rewritten})
        return rewritten if rewritten else new_query
    except Exception as e:
        logger.error(f"Query rewrite failed: {e}")
        return new_query
