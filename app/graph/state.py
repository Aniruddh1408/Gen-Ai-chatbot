from typing import Any, TypedDict


class ChatGraphState(TypedDict, total=False):
    query: str
    session_id: str
    community_id: int
    community_name: str
    memory_session_id: str

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
