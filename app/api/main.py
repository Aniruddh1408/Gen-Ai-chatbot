from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import time
import uuid

from app.agents.router import route_query
from app.agents.guardrails import input_guardrail, output_guardrail
from app.agents.memory import rewrite_query_with_memory, add_turn, get_history
from app.core.logger import get_logger

app = FastAPI(
    title="KuboCare AI Assistant",
    description="Intelligent Hybrid Analytics for IoT and Healthcare",
    version="2.1.0",
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Deployment: Serve Frontend
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=frontend_path), name="static")

@app.get("/")
def read_root():
    return FileResponse(os.path.join(frontend_path, "index.html"))

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": time.time()}

logger = get_logger("api_gateway")

LOCAL_DEMO_COMMUNITIES = {
    1: "Green Valley Care",
    2: "Sunrise Senior Living",
    3: "Lotus Wellness Home",
}


def _get_memory_session_id(session_id: str, community_id: int) -> str:
    """Keep local demo chat history isolated per community."""
    return f"community:{community_id}:session:{session_id}"


def _get_community_name(community_id: int) -> str | None:
    return LOCAL_DEMO_COMMUNITIES.get(community_id)


def _is_current_community_query(query: str) -> bool:
    q = query.lower().strip()
    return any(
        phrase in q
        for phrase in [
            "which community am i",
            "what community am i",
            "which community data",
            "what community data",
            "current community",
            "community am i viewing",
            "community am i using",
        ]
    )


class AskRequest(BaseModel):
    """Request model for the /ask endpoint."""
    query: str
    session_id: str = "default"
    community_id: int


@app.post("/ask")
def ask(request: AskRequest):
    start_time = time.time()
    trace_id = str(uuid.uuid4())

    query = request.query
    session_id = request.session_id
    community_id = request.community_id
    community_name = _get_community_name(community_id)
    if community_name is None:
        return {
            "error": "Invalid community_id. Use 1 for Green Valley Care, 2 for Sunrise Senior Living, or 3 for Lotus Wellness Home.",
            "trace_id": trace_id,
        }

    memory_session_id = _get_memory_session_id(session_id, community_id)
    chat_history = get_history(memory_session_id)

    # Context dictionary for structured JSON logging
    log_ctx = {
        "trace_id": trace_id,
        "query": query,
        "session_id": session_id,
        "memory_session_id": memory_session_id,
        "community_id": community_id,
        "community_name": community_name,
    }
    logger.info("Incoming query received", extra=log_ctx)

    # 1. Memory: Rewrite query using chat history context — adds context for follow-ups
    if _is_current_community_query(query):
        latency_ms = (time.time() - start_time) * 1000
        answer = f"You are viewing {community_name} (community ID {community_id})."
        add_turn(memory_session_id, query, answer)
        return {
            "query": query,
            "answer": answer,
            "trace_id": trace_id,
            "latency_ms": latency_ms,
            "community_id": community_id,
            "community_name": community_name,
        }

    rewritten_query = rewrite_query_with_memory(memory_session_id, query)
    if rewritten_query != query:
        logger.info("Query was rewritten by memory agent", extra={
            "original": query,
            "rewritten": rewritten_query,
            "trace_id": trace_id,
        })

    # 2. Firewall: Test for malicious injections or completely off-topic questions
    # Note: We check the REWRITTEN query so that contextual follow-ups (e.g. "show more")
    # are allowed if they refer to IoT data.
    is_safe = input_guardrail(rewritten_query)
    if not is_safe:
        return {
            "error": "Query blocked by security guardrails. Please constrain questions to resident, clinical, IoT, or hardware analytics.",
            "trace_id": trace_id,
        }

    # 3. Main Execution: Pass to the Multi-Retriever Agent
    try:
        response = route_query(
            rewritten_query,
            original_query=query,
            chat_history=chat_history,
            community_id=community_id,
        )
    except Exception as e:
        logger.exception(f"Agent flow crashed: {e}", extra=log_ctx)
        return {"error": "Internal System Error", "trace_id": trace_id}

    # 4. Output Validation: Check the textual reasoning to ensure no leaked prompts
    if isinstance(response, dict) and "answer" in response:
        response["answer"] = output_guardrail(response["answer"])

    # 5. Memory: Store this turn for future context
    ai_answer = ""
    if isinstance(response, dict):
        if "answer" in response:
            ai_answer = response["answer"]
        elif "result" in response:
            ai_answer = str(response["result"])
    add_turn(memory_session_id, query, ai_answer)

    # 6. Latency Telemetry
    latency_ms = (time.time() - start_time) * 1000
    log_ctx["latency_ms"] = latency_ms
    logger.info("Request completed successfully", extra=log_ctx)

    # Attach tracing stats to the response
    if isinstance(response, dict):
        response["trace_id"] = trace_id
        response["latency_ms"] = latency_ms
        response["community_id"] = community_id
        response["community_name"] = community_name
        if rewritten_query != query:
            response["rewritten_query"] = rewritten_query

    return response


@app.get("/history/{session_id}")
def get_session_history(session_id: str, community_id: int = 1):
    """Retrieve the chat history for a given session."""
    community_name = _get_community_name(community_id)
    if community_name is None:
        return {
            "error": "Invalid community_id. Use 1 for Green Valley Care, 2 for Sunrise Senior Living, or 3 for Lotus Wellness Home.",
        }

    memory_session_id = _get_memory_session_id(session_id, community_id)
    history = get_history(memory_session_id)
    return {
        "session_id": session_id,
        "memory_session_id": memory_session_id,
        "community_id": community_id,
        "community_name": community_name,
        "history": history,
        "turn_count": len(history),
    }


@app.delete("/history/{session_id}")
def clear_session_history(session_id: str, community_id: int = 1):
    """Clear the chat history for a given session."""
    from app.agents.memory import clear_history
    community_name = _get_community_name(community_id)
    if community_name is None:
        return {
            "error": "Invalid community_id. Use 1 for Green Valley Care, 2 for Sunrise Senior Living, or 3 for Lotus Wellness Home.",
        }

    memory_session_id = _get_memory_session_id(session_id, community_id)
    clear_history(memory_session_id)
    return {
        "session_id": session_id,
        "memory_session_id": memory_session_id,
        "community_id": community_id,
        "community_name": community_name,
        "status": "cleared",
    }


@app.get("/debug/guardrail")
def debug_guardrail(query: str):
    """Debug endpoint — test guardrail in isolation inside the live server."""
    from app.agents.guardrails import input_guardrail
    result = input_guardrail(query)
    return {"query": query, "allowed": result}
