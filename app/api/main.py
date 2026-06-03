# ===========================================================================
# This file is the web server — the public entrance to the chatbot. It defines
# the web addresses the app and other programs call: send a chat message, upload
# a file, fetch or clear a conversation's history, and a health check. Each
# incoming request is run through the safety checks and answer pipeline, then a
# clean reply is sent back. It also serves the chat web page itself.
# ===========================================================================
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, File, Form, UploadFile
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import time

from app.agents.attachments import (
    add_attachment,
    chunk_text,
    clear_attachment,
    list_attachments,
)
from app.agents.memory import clear_history, get_history
from app.core.community import (
    authorize_community,
    get_community_name,
    get_memory_session_id,
)
from app.core.config import (
    CORS_ALLOW_CREDENTIALS,
    CORS_ALLOW_ORIGINS,
    ENABLE_DEBUG_ENDPOINTS,
    UPLOAD_MAX_BYTES,
)
from app.core.logger import get_logger
from app.graph.workflow import run_chat_graph
from app.ingest.file_extract import extract_text
from app.retrievers.vector_retriever import get_embedding

logger = get_logger("api")


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


@app.get("/users")
def list_users():
    """List staff users with their role and allowed community ids.

    Used by the frontend "Login as" picker so a demo viewer can select a
    user and see only that user's mapped communities. Residents are not
    included — they aren't in `users` (separated by the schema migration).

    Returns a list ordered by role precedence (admin first, then center
    owners, caregivers), then by user id within each group.
    Each row carries the `communities` array the authorize_community gate
    will accept, so the frontend can mirror the same filter locally.
    """
    from app.core.db import DatabaseUnavailableError, run_query

    try:
        rows = run_query(
            """
            SELECT u.id,
                   u.name,
                   r.name AS role,
                   COALESCE(
                       ARRAY_AGG(cum.community_id ORDER BY cum.community_id)
                       FILTER (WHERE cum.community_id IS NOT NULL),
                       ARRAY[]::integer[]
                   ) AS communities
            FROM users u
            JOIN roles r ON r.id = u.role_id
            LEFT JOIN community_user_mapping cum
                   ON cum.user_id = u.id
                  AND COALESCE(cum.is_deleted, false) = false
            WHERE COALESCE(u.is_deleted, false) = false
            GROUP BY u.id, u.name, r.name
            ORDER BY
                CASE r.name
                    WHEN 'admin'         THEN 1
                    WHEN 'center_owner'  THEN 2
                    WHEN 'caregiver'     THEN 3
                    ELSE 5
                END,
                u.id
            """
        )
    except DatabaseUnavailableError:
        logger.error("Could not load users for the login picker (DB unavailable).")
        return {"error": "Login options are temporarily unavailable. Please try again."}

    return {
        "users": [
            {"id": uid, "name": name, "role": role, "communities": list(communities)}
            for uid, name, role, communities in rows
        ]
    }


class AskRequest(BaseModel):
    """Request model for the /ask endpoint.

    user_id is optional to preserve the demo / unauthenticated path. When
    supplied, the request is rejected unless the user is mapped to
    community_id in community_user_mapping.
    """
    query: str
    session_id: str = "default"
    community_id: int
    user_id: int | None = None


@app.post("/ask")
def ask(request: AskRequest):
    err = authorize_community(request.user_id, request.community_id)
    if err is not None:
        return {"error": err}
    return run_chat_graph(
        query=request.query,
        session_id=request.session_id,
        community_id=request.community_id,
        user_id=request.user_id,
    )


def _safe_filename(filename: str) -> str:
    """Strip any path components and keep a clean basename."""
    base = os.path.basename(str(filename or "").replace("\\", "/")).strip()
    return base or "uploaded_file"


# Every endpoint below takes community_id, so every endpoint below applies
# the same authorize_community gate. Without this, a caller could read or
# mutate another community's uploads / chat history just by passing a
# community_id they aren't mapped to. (Pre-fix this was a security gap; the
# original allowlist check only confirmed community_id was valid, not that
# the caller had access to it.) user_id is optional everywhere — when
# omitted, only the allowlist check runs (the demo path).
@app.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    session_id: str = Form("default"),
    community_id: int = Form(...),
    user_id: int | None = Form(None),
):
    """Accept a document, extract its text, embed it, and store it for this
    chat session only (ephemeral + private). Returns a safe summary; technical
    errors are logged, never returned."""
    err = authorize_community(user_id, community_id)
    if err is not None:
        return {"error": err}

    filename = _safe_filename(file.filename)
    try:
        raw = file.file.read()
    except Exception as exc:
        logger.error(f"Upload read failed for {filename}: {exc}")
        return {"error": "I couldn't read that file. Please try again."}

    if len(raw) > UPLOAD_MAX_BYTES:
        max_mb = UPLOAD_MAX_BYTES // (1024 * 1024)
        return {"error": f"File is too large. Maximum size is {max_mb} MB."}

    result = extract_text(filename, raw)
    if not result.ok:
        return {"error": result.error or "I couldn't read that file."}

    chunks = chunk_text(result.text)
    chunks_with_embeddings = []
    if chunks:
        # Embed chunks concurrently so a multi-page document doesn't wait on a
        # long sequence of one-at-a-time embedding round-trips.
        with ThreadPoolExecutor(max_workers=4) as executor:
            embeddings = list(executor.map(get_embedding, chunks))
        chunks_with_embeddings = [
            {"text": chunk, "embedding": embedding}
            for chunk, embedding in zip(chunks, embeddings)
            if embedding
        ]

    if not chunks_with_embeddings:
        logger.error(f"No embeddings produced for upload {filename}")
        return {"error": "I couldn't process the file content right now. Please try again shortly."}

    memory_session_id = get_memory_session_id(session_id, community_id, user_id)
    preview = result.text[:600]
    file_id = add_attachment(
        memory_session_id,
        filename,
        chunks_with_embeddings,
        preview,
        len(result.text),
        result.n_units,
        result.kind,
    )

    logger.info(
        "File uploaded and attached",
        extra={
            "session_id": session_id,
            "community_id": community_id,
            "user_id": user_id,
            "upload_filename": filename,
            "upload_kind": result.kind,
            "upload_chars": len(result.text),
            "upload_chunks": len(chunks_with_embeddings),
        },
    )

    return {
        "file_id": file_id,
        "filename": filename,
        "kind": result.kind,
        "chars": len(result.text),
        "n_units": result.n_units,
        "preview": preview[:200],
        "status": "ready",
    }


@app.get("/upload")
def list_session_uploads(
    session_id: str,
    community_id: int,
    user_id: int | None = None,
):
    """List active attachments for a session (used by the UI to rehydrate chips)."""
    err = authorize_community(user_id, community_id)
    if err is not None:
        return {"error": err}
    memory_session_id = get_memory_session_id(session_id, community_id, user_id)
    return {"files": list_attachments(memory_session_id)}


@app.delete("/upload/{file_id}")
def delete_session_upload(
    file_id: str,
    session_id: str,
    community_id: int,
    user_id: int | None = None,
):
    """Remove a single uploaded file from a session."""
    err = authorize_community(user_id, community_id)
    if err is not None:
        return {"error": err}
    memory_session_id = get_memory_session_id(session_id, community_id, user_id)
    removed = clear_attachment(memory_session_id, file_id)
    return {"file_id": file_id, "status": "removed" if removed else "not_found"}


@app.get("/history/{session_id}")
def get_session_history(
    session_id: str,
    community_id: int,
    user_id: int | None = None,
):
    """Retrieve the chat history for a given session."""
    err = authorize_community(user_id, community_id)
    if err is not None:
        return {"error": err}

    memory_session_id = get_memory_session_id(session_id, community_id, user_id)
    history = get_history(memory_session_id)

    return {
        "session_id": session_id,
        "memory_session_id": memory_session_id,
        "community_id": community_id,
        "community_name": get_community_name(community_id),
        "history": history,
        "turn_count": len(history),
    }


@app.delete("/history/{session_id}")
def clear_session_history(
    session_id: str,
    community_id: int,
    user_id: int | None = None,
):
    """Clear the chat history for a given session."""
    err = authorize_community(user_id, community_id)
    if err is not None:
        return {"error": err}

    memory_session_id = get_memory_session_id(session_id, community_id, user_id)
    clear_history(memory_session_id)

    return {
        "session_id": session_id,
        "memory_session_id": memory_session_id,
        "community_id": community_id,
        "community_name": get_community_name(community_id),
        "status": "cleared",
    }


if ENABLE_DEBUG_ENDPOINTS:
    @app.get("/debug/guardrail")
    def debug_guardrail(query: str):
        """Debug endpoint - test guardrail in isolation. Disabled unless ENABLE_DEBUG_ENDPOINTS is set."""
        from app.agents.guardrails import input_guardrail

        result = input_guardrail(query)
        return {"query": query, "allowed": result}
