# ===========================================================================
# This file describes the "clipboard" passed from step to step while a chat
# message is processed. It lists every piece of information a step might read or
# fill in — the question, who's asking, the running answer, timing, and so on —
# so all the steps agree on the same shape of data.
# ===========================================================================
from typing import Any, TypedDict


class ChatGraphState(TypedDict, total=False):
    query: str
    session_id: str
    community_id: int
    community_name: str
    memory_session_id: str
    # Optional caller identity. When set, the memory_session_id includes it
    # so two users on the same (community, session_id) get separate history.
    # See get_memory_session_id in app/core/community.py.
    user_id: int

    trace_id: str
    start_time: float
    latency_ms: float

    transform_style: str
    chat_history: list[dict]
    rewritten_query: str
    sub_queries: list[str]

    response: dict[str, Any]
    ai_answer: str
    should_save_memory: bool
    attachment_answered: bool
