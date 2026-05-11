import time
import uuid
from langgraph.graph import END, StateGraph
from app.agents.guardrails import input_guardrail, output_guardrail
from app.agents.memory import add_turn, get_history, rewrite_query_with_memory
from app.agents.router import route_query
from app.core.community import (
    get_community_name,
    get_memory_session_id,
    invalid_community_error,
    is_current_community_query,
)
from app.core.logger import get_logger
from app.graph.state import ChatGraphState

logger = get_logger("chat_graph")


def _has_response(state: ChatGraphState) -> bool:
    return bool(state.get("response"))


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


def rewrite_node(state: ChatGraphState) -> ChatGraphState:
    if _has_response(state):
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


def guardrail_node(state: ChatGraphState) -> ChatGraphState:
    if _has_response(state):
        return {}

    rewritten_query = state.get("rewritten_query") or state["query"]

    if input_guardrail(rewritten_query):
        return {}

    return {
        "response": {
            "error": (
                "Query blocked by security guardrails. Please constrain questions "
                "to resident, clinical, IoT, or hardware analytics."
            ),
            "trace_id": state["trace_id"],
        },
        "should_save_memory": False,
    }


def route_node(state: ChatGraphState) -> ChatGraphState:
    if _has_response(state):
        return {}

    rewritten_query = state.get("rewritten_query") or state["query"]

    try:
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
    response = dict(state.get("response") or {})

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
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("guardrail", guardrail_node)
    graph.add_node("route", route_node)
    graph.add_node("output_guardrail", output_guardrail_node)
    graph.add_node("save_memory", save_memory_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("load_context")

    graph.add_edge("load_context", "current_community")
    graph.add_edge("current_community", "rewrite")
    graph.add_edge("rewrite", "guardrail")
    graph.add_edge("guardrail", "route")
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
