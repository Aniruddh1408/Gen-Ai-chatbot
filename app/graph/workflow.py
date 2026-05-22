import time
import uuid
import re
from langgraph.graph import END, StateGraph
from app.agents.guardrails import input_guardrail, output_guardrail
from app.agents.memory import add_turn, get_history, rewrite_query_with_memory
from app.agents.router import route_query
from app.llm.client import ask_llm

from app.core.community import (
    get_community_name,
    get_memory_session_id,
    invalid_community_error,
    is_current_community_query,
)
from app.core.logger import get_logger
from app.graph.state import ChatGraphState

logger = get_logger("chat_graph")

_QUESTION_START_RE = re.compile(
    r"\b(?:what|who|which|when|where|why|how|does|do|did|can|could|should|"
    r"is|are|was|were|tell|show|give|list|explain)\b",
    re.IGNORECASE,
)
_FOLLOW_UP_SPLIT_RE = re.compile(
    r"\s+(?:and|also|then)\s+(?=(?:what|who|which|when|where|why|how|does|do|did|"
    r"can|could|should|is|are|was|were|tell|show|give|list|explain)\b)",
    re.IGNORECASE,
)
_COMPOUND_METRIC_CONCEPT_RE = re.compile(
    r"^\s*(?:what\s+(?:is|are)|explain|define)\s+(?:the\s+)?"
    r"(?:bp|blood\s+pressure|sugar(?:\s+level)?|glucose(?:\s+level)?|"
    r"steps?|step\s+count|sleep\s+duration)\b.*\s+and\s+how\s+"
    r"(?:is|are|do|does)\s+(?:it|they|this|that)?\s*"
    r"(?:measured|calculated|tracked|counted)\b",
    re.IGNORECASE,
)
_MAX_SUB_QUERIES = 4

# Response fields safe to return to the client. Anything not listed here
# (sql, plan, result, retrieved_context, sub_responses, ...) is stripped in
# finalize_node so backend/implementation details never leak to users.
_CLIENT_SAFE_RESPONSE_KEYS = {
    "answer",
    "error",
    "chart_data",
    "query",
    "sub_queries",
    "blocked_queries",
    "trace_id",
    "latency_ms",
    "community_id",
    "community_name",
    "rewritten_query",
}

_SIMPLE_REPHRASE_TERMS = [
    "explain simply",
    "explain it simply",
    "explain in simple words",
    "explain it in simple words",
    "explain in simple terms",
    "explain it in simple terms",
    "simple terms",
    "simpler terms",
    "plain language",
    "layman terms",
    "layman's terms",
    "make it simple",
    "make this simple",
    "make it easier",
    "make this easier",
    "make it understandable",
    "make this understandable",
    "did not get it",
    "did not get that",
    "did not get",
    "didnt get",
    "didn't get",
    "simplify",
    "i did not understand",
    "i didn't understand",
    "did not understand",
    "dont understand",
    "don't understand",
    "explain like i am new",
    "explain like a beginner",
]

_POINT_REPHRASE_TERMS = [
    "give it in points",
    "give this in points",
    "give that in points",
    "give it as points",
    "give this as points",
    "give that as points",
    "give it in bullets",
    "give this in bullets",
    "give that in bullets",
    "give it as bullets",
    "give this as bullets",
    "give that as bullets",
    "give it in bullet points",
    "give this in bullet points",
    "give that in bullet points",
    "tell it in points",
    "explain in points",
    "make it points",
    "make it bullets",
    "make this bullets",
    "bullet points",
    "bullets",
    "pointwise",
    "step by step",
]

_FORMAT_REPHRASE_TERMS = [
    "give it in a neat form",
    "give this in a neat form",
    "give that in a neat form",
    "give it in neat form",
    "give this in neat form",
    "give that in neat form",
    "make it neat",
    "make this neat",
    "format it neatly",
    "format this neatly",
    "neat format",
    "neat form",
]

_SHORT_REPHRASE_TERMS = [
    "make it short",
    "summarize",
    "short summary",
    "briefly",
    "in brief",
]
_DETAIL_FOLLOWUP_TERMS = [
    "explain in detail",
    "explain it in detail",
    "explain this in detail",
    "in detail",
    "more detail",
    "more details",
    "tell me more",
    "explain more",
    "elaborate",
    "go deeper",
    "expand",
]
_TRANSFORM_ONLY_TERMS = set(
    _SIMPLE_REPHRASE_TERMS
    + _POINT_REPHRASE_TERMS
    + _FORMAT_REPHRASE_TERMS
    + _SHORT_REPHRASE_TERMS
    + _DETAIL_FOLLOWUP_TERMS
)


def _has_response(state: ChatGraphState) -> bool:
    return bool(state.get("response"))


def _after_load_context(state: ChatGraphState) -> str:
    if _has_response(state):
        return "finalize"
    return "current_community"


def _after_current_community(state: ChatGraphState) -> str:
    if _has_response(state):
        return "output_guardrail"
    return "transform_previous_answer"


def _after_guardrail(state: ChatGraphState) -> str:
    if _has_response(state):
        return "finalize"
    return "route"


def _after_transform_previous_answer(state: ChatGraphState) -> str:
    if _has_response(state):
        return "output_guardrail"
    return "rewrite"


def _clean_sub_query(query: str) -> str:
    cleaned = re.sub(r"\s+", " ", query).strip(" \t\r\n.;")
    if not cleaned:
        return ""
    if _QUESTION_START_RE.search(cleaned) and cleaned[-1] not in ".?!":
        return f"{cleaned}?"
    return cleaned


def split_multi_question_query(query: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", query).strip()
    if not normalized:
        return []
    if _COMPOUND_METRIC_CONCEPT_RE.search(normalized):
        return [normalized]

    question_mark_parts = [
        _clean_sub_query(part)
        for part in re.findall(r"[^?]+(?:\?|$)", normalized)
    ]
    question_mark_parts = [part for part in question_mark_parts if part]
    if len(question_mark_parts) > 1:
        return question_mark_parts[:_MAX_SUB_QUERIES]

    connector_parts = [
        _clean_sub_query(part)
        for part in _FOLLOW_UP_SPLIT_RE.split(normalized)
    ]
    connector_parts = [part for part in connector_parts if part]
    if len(connector_parts) > 1:
        return connector_parts[:_MAX_SUB_QUERIES]

    return [normalized]


def _queries_for_routing(state: ChatGraphState) -> list[str]:
    sub_queries = state.get("sub_queries")
    if isinstance(sub_queries, list) and sub_queries:
        return [str(query).strip() for query in sub_queries if str(query).strip()]

    rewritten_query = state.get("rewritten_query") or state["query"]
    return [rewritten_query]


def _format_multi_query_answer(responses: list[dict]) -> str:
    lines = []
    for index, response in enumerate(responses, start=1):
        question = response.get("query") or f"Question {index}"
        answer = response.get("answer") or response.get("error") or "No answer generated."
        lines.append(f"{index}. {question}\n{answer}")
    return "\n\n".join(lines)


def _detect_transform_style(query: str) -> str | None:
    q_lower = query.lower().strip()

    if any(term in q_lower for term in _POINT_REPHRASE_TERMS + _FORMAT_REPHRASE_TERMS):
        return "points"

    if any(term in q_lower for term in _SHORT_REPHRASE_TERMS):
        return "short"

    if any(term in q_lower for term in _SIMPLE_REPHRASE_TERMS):
        return "simple"

    if any(term in q_lower for term in _DETAIL_FOLLOWUP_TERMS):
        return "detail"

    return None


def _latest_assistant_answer(chat_history: list[dict]) -> str | None:
    for turn in reversed(chat_history or []):
        answer = str(turn.get("ai", "")).strip()
        if answer:
            return answer
    return None


def _normalize_followup_text(query: str) -> str:
    cleaned = query.lower().replace("\\", " ")
    cleaned = re.sub(r"[^\w\s']", " ", cleaned)
    cleaned = re.sub(r"\bplease\b", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _is_transform_only_followup(query: str) -> bool:
    normalized = _normalize_followup_text(query)
    if not normalized:
        return False

    return any(normalized == term for term in _TRANSFORM_ONLY_TERMS)


def _latest_user_question(chat_history: list[dict]) -> str | None:
    for turn in reversed(chat_history or []):
        question = str(turn.get("user", "")).strip()
        if question and not _is_transform_only_followup(question):
            return question
    return None


def load_context_node(state: ChatGraphState) -> ChatGraphState:
    community_id = state["community_id"]
    community_name = get_community_name(community_id)

    if community_name is None:
        return {
            "response": {
                "error": invalid_community_error(),
                "trace_id": state["trace_id"],
            },
            "should_save_memory": False,
        }

    if not state["query"].strip():
        return {
            "community_name": community_name,
            "response": {
                "answer": "Please enter a question and I'll do my best to help.",
            },
            "should_save_memory": False,
        }

    memory_session_id = get_memory_session_id(state["session_id"], community_id)
    chat_history = get_history(memory_session_id)

    logger.info(
        "Incoming query received",
        extra={
            "trace_id": state["trace_id"],
            "query": state["query"],
            "session_id": state["session_id"],
            "memory_session_id": memory_session_id,
            "community_id": community_id,
            "community_name": community_name,
        },
    )

    return {
        "community_name": community_name,
        "memory_session_id": memory_session_id,
        "chat_history": chat_history,
    }


def current_community_node(state: ChatGraphState) -> ChatGraphState:
    if _has_response(state):
        return {}

    if not is_current_community_query(state["query"]):
        return {}

    answer = f"You are viewing {state['community_name']} (community ID {state['community_id']})."

    return {
        "response": {
            "query": state["query"],
            "answer": answer,
        },
        "ai_answer": answer,
        "should_save_memory": True,
    }


def transform_previous_answer_node(state: ChatGraphState) -> ChatGraphState:
    if _has_response(state):
        return {}

    style = _detect_transform_style(state["query"])
    if not style:
        return {}

    if style == "detail":
        previous_question = _latest_user_question(state.get("chat_history", []))
        if not previous_question:
            return {}

        return {
            "rewritten_query": f"Explain in more detail: {previous_question}",
            "transform_style": style,
        }

    previous_answer = _latest_assistant_answer(state.get("chat_history", []))
    if not previous_answer:
        return {}

    if style == "points":
        transform_prompt = (
            "Rewrite the previous answer as clear bullet points. "
            "Do not add new facts. Do not remove important warnings, numbers, names, or values."
        )
    elif style == "short":
        transform_prompt = (
            "Summarize the previous answer briefly. "
            "Do not add new facts. Preserve important warnings, numbers, names, and values."
        )
    else:
        transform_prompt = (
            "Rewrite the previous answer in simpler language for a non-technical user. "
            "Do not add new facts. Preserve important warnings, numbers, names, and values."
        )

    answer = ask_llm(
        f"Previous answer:\n{previous_answer}",
        system_prompt=transform_prompt,
        num_predict=500,
        temperature=0.0,
    )

    return {
        "response": {
            "query": state["query"],
            "answer": answer,
        },
        "ai_answer": answer,
        "should_save_memory": True,
        "transform_style": style,
    }


def rewrite_node(state: ChatGraphState) -> ChatGraphState:
    if _has_response(state):
        return {}

    if state.get("rewritten_query"):
        return {}

    rewritten_query = rewrite_query_with_memory(
        state["memory_session_id"],
        state["query"],
    )

    if rewritten_query != state["query"]:
        logger.info(
            "Query was rewritten by memory agent",
            extra={
                "trace_id": state["trace_id"],
                "original": state["query"],
                "rewritten": rewritten_query,
            },
        )

    return {"rewritten_query": rewritten_query}


def split_questions_node(state: ChatGraphState) -> ChatGraphState:
    if _has_response(state):
        return {}

    rewritten_query = state.get("rewritten_query") or state["query"]
    sub_queries = split_multi_question_query(rewritten_query)

    if len(sub_queries) > 1:
        logger.info(
            "Multi-question query split",
            extra={
                "trace_id": state["trace_id"],
                "query": state["query"],
                "sub_query_count": len(sub_queries),
            },
        )

    return {"sub_queries": sub_queries}


def guardrail_node(state: ChatGraphState) -> ChatGraphState:
    if _has_response(state):
        return {}

    blocked_queries = [
        query for query in _queries_for_routing(state)
        if not input_guardrail(query)
    ]

    if not blocked_queries:
        return {}

    return {
        "response": {
            "error": (
                "Query blocked by security guardrails. Please constrain questions "
                "to resident, clinical, IoT, or hardware analytics."
            ),
            "trace_id": state["trace_id"],
            "blocked_queries": blocked_queries,
        },
        "should_save_memory": False,
    }


def route_node(state: ChatGraphState) -> ChatGraphState:
    if _has_response(state):
        return {}

    routing_queries = _queries_for_routing(state)

    try:
        if len(routing_queries) > 1:
            responses = [
                route_query(
                    sub_query,
                    original_query=sub_query,
                    chat_history=state.get("chat_history", []),
                    community_id=state["community_id"],
                )
                for sub_query in routing_queries
            ]
            return {
                "response": {
                    "query": state["query"],
                    "sub_queries": routing_queries,
                    "sub_responses": responses,
                    "answer": _format_multi_query_answer(responses),
                },
                "should_save_memory": True,
            }

        rewritten_query = routing_queries[0]
        response = route_query(
            rewritten_query,
            original_query=state["query"],
            chat_history=state.get("chat_history", []),
            community_id=state["community_id"],
        )
    except Exception as exc:
        logger.exception(
            f"Agent flow crashed: {exc}",
            extra={
                "trace_id": state["trace_id"],
                "query": state["query"],
                "community_id": state["community_id"],
            },
        )
        return {
            "response": {
                "error": "Internal System Error",
                "trace_id": state["trace_id"],
            },
            "should_save_memory": False,
        }

    return {
        "response": response,
        "should_save_memory": True,
    }


def output_guardrail_node(state: ChatGraphState) -> ChatGraphState:
    response = state.get("response")
    if not isinstance(response, dict):
        return {}

    if "answer" in response:
        response = dict(response)
        response["answer"] = output_guardrail(response["answer"])
        return {"response": response}

    return {}


def save_memory_node(state: ChatGraphState) -> ChatGraphState:
    if not state.get("should_save_memory"):
        return {}

    memory_session_id = state.get("memory_session_id")
    if not memory_session_id:
        return {}

    response = state.get("response", {})

    ai_answer = state.get("ai_answer", "")
    if not ai_answer and isinstance(response, dict):
        if "answer" in response:
            ai_answer = str(response["answer"])
        elif "result" in response:
            ai_answer = str(response["result"])

    add_turn(memory_session_id, state["query"], ai_answer)

    return {"ai_answer": ai_answer}


def finalize_node(state: ChatGraphState) -> ChatGraphState:
    raw_response = state.get("response") or {}
    response = {key: value for key, value in raw_response.items() if key in _CLIENT_SAFE_RESPONSE_KEYS}

    latency_ms = (time.time() - state["start_time"]) * 1000

    response["trace_id"] = state["trace_id"]
    response["latency_ms"] = latency_ms

    if state.get("community_name"):
        response["community_id"] = state["community_id"]
        response["community_name"] = state["community_name"]

    rewritten_query = state.get("rewritten_query")
    if rewritten_query and rewritten_query != state["query"]:
        response["rewritten_query"] = rewritten_query

    logger.info(
        "Request completed",
        extra={
            "trace_id": state["trace_id"],
            "query": state["query"],
            "latency_ms": latency_ms,
            "community_id": state.get("community_id"),
            "community_name": state.get("community_name"),
        },
    )

    return {
        "response": response,
        "latency_ms": latency_ms,
    }


def build_chat_graph():
    graph = StateGraph(ChatGraphState)

    graph.add_node("load_context", load_context_node)
    graph.add_node("current_community", current_community_node)
    graph.add_node("transform_previous_answer", transform_previous_answer_node)
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("split_questions", split_questions_node)
    graph.add_node("guardrail", guardrail_node)
    graph.add_node("route", route_node)
    graph.add_node("output_guardrail", output_guardrail_node)
    graph.add_node("save_memory", save_memory_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("load_context")

    graph.add_conditional_edges(
        "load_context",
        _after_load_context,
        {
            "current_community": "current_community",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "current_community",
        _after_current_community,
        {
            "transform_previous_answer": "transform_previous_answer",
            "output_guardrail": "output_guardrail",
        },
    )
    graph.add_conditional_edges(
        "transform_previous_answer",
        _after_transform_previous_answer,
        {
            "rewrite": "rewrite",
            "output_guardrail": "output_guardrail",
        },
    )

    graph.add_edge("rewrite", "split_questions")
    graph.add_edge("split_questions", "guardrail")
    graph.add_conditional_edges(
        "guardrail",
        _after_guardrail,
        {
            "route": "route",
            "finalize": "finalize",
        },
    )
    graph.add_edge("route", "output_guardrail")
    graph.add_edge("output_guardrail", "save_memory")
    graph.add_edge("save_memory", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


chat_graph = build_chat_graph()


def run_chat_graph(query: str, session_id: str, community_id: int) -> dict:
    initial_state: ChatGraphState = {
        "query": query,
        "session_id": session_id,
        "community_id": community_id,
        "trace_id": str(uuid.uuid4()),
        "start_time": time.time(),
        "should_save_memory": False,
    }

    final_state = chat_graph.invoke(initial_state)
    return final_state["response"]
