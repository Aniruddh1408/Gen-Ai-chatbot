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


class AskRequest(BaseModel):
    """Request model for the /ask endpoint."""
    query: str
    session_id: str = "default"


@app.post("/ask")
def ask(request: AskRequest):
    start_time = time.time()
    trace_id = str(uuid.uuid4())

    query = request.query
    session_id = request.session_id
    chat_history = get_history(session_id)

    # Context dictionary for structured JSON logging
    log_ctx = {"trace_id": trace_id, "query": query, "session_id": session_id}
    logger.info("Incoming query received", extra=log_ctx)

    # 1. Memory: Rewrite query using chat history context — adds context for follow-ups
    rewritten_query = rewrite_query_with_memory(session_id, query)
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
            "error": "Query blocked by security guardrails. Please constrain questions strictly to IoT data and hardware analytics.",
            "trace_id": trace_id,
        }

    # 3. Main Execution: Pass to the Multi-Retriever Agent
    try:
        response = route_query(rewritten_query, original_query=query, chat_history=chat_history)
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
    add_turn(session_id, query, ai_answer)

    # 6. Latency Telemetry
    latency_ms = (time.time() - start_time) * 1000
    log_ctx["latency_ms"] = latency_ms
    logger.info("Request completed successfully", extra=log_ctx)

    # Attach tracing stats to the response
    if isinstance(response, dict):
        response["trace_id"] = trace_id
        response["latency_ms"] = latency_ms
        if rewritten_query != query:
            response["rewritten_query"] = rewritten_query

    return response


@app.get("/history/{session_id}")
def get_session_history(session_id: str):
    """Retrieve the chat history for a given session."""
    history = get_history(session_id)
    return {"session_id": session_id, "history": history, "turn_count": len(history)}


@app.delete("/history/{session_id}")
def clear_session_history(session_id: str):
    """Clear the chat history for a given session."""
    from app.agents.memory import clear_history
    clear_history(session_id)
    return {"session_id": session_id, "status": "cleared"}


@app.get("/debug/guardrail")
def debug_guardrail(query: str):
    """Debug endpoint — test guardrail in isolation inside the live server."""
    from app.agents.guardrails import input_guardrail
    result = input_guardrail(query)
    return {"query": query, "allowed": result}
