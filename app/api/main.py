from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import time

from app.agents.memory import clear_history, get_history
from app.core.community import (
    get_community_name,
    get_memory_session_id,
    invalid_community_error,
)
from app.core.config import (
    CORS_ALLOW_CREDENTIALS,
    CORS_ALLOW_ORIGINS,
    ENABLE_DEBUG_ENDPOINTS,
)
from app.graph.workflow import run_chat_graph


app = FastAPI(
    title="KuboCare AI Assistant",
    description="Intelligent Hybrid Analytics for IoT and Healthcare",
    version="2.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/static", StaticFiles(directory=frontend_path), name="static")


@app.get("/")
def read_root():
    return FileResponse(os.path.join(frontend_path, "index.html"))


@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": time.time()}


class AskRequest(BaseModel):
    """Request model for the /ask endpoint."""
    query: str
    session_id: str = "default"
    community_id: int


@app.post("/ask")
def ask(request: AskRequest):
    return run_chat_graph(
        query=request.query,
        session_id=request.session_id,
        community_id=request.community_id,
    )


@app.get("/history/{session_id}")
def get_session_history(session_id: str, community_id: int):
    """Retrieve the chat history for a given session."""
    community_name = get_community_name(community_id)
    if community_name is None:
        return {"error": invalid_community_error()}

    memory_session_id = get_memory_session_id(session_id, community_id)
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
def clear_session_history(session_id: str, community_id: int):
    """Clear the chat history for a given session."""
    community_name = get_community_name(community_id)
    if community_name is None:
        return {"error": invalid_community_error()}

    memory_session_id = get_memory_session_id(session_id, community_id)
    clear_history(memory_session_id)

    return {
        "session_id": session_id,
        "memory_session_id": memory_session_id,
        "community_id": community_id,
        "community_name": community_name,
        "status": "cleared",
    }


if ENABLE_DEBUG_ENDPOINTS:
    @app.get("/debug/guardrail")
    def debug_guardrail(query: str):
        """Debug endpoint - test guardrail in isolation. Disabled unless ENABLE_DEBUG_ENDPOINTS is set."""
        from app.agents.guardrails import input_guardrail

        result = input_guardrail(query)
        return {"query": query, "allowed": result}
