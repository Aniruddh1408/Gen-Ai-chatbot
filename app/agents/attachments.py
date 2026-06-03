# ===========================================================================
# This file remembers the documents a user uploads during a chat. It stores the
# extracted text and its search-vectors tied to that one conversation, saved to
# disk so they survive a restart and stay private to that chat. Other chats
# can't see them, and nothing here is added to the shared knowledge base.
# ===========================================================================
"""Per-session attachment store for uploaded documents.

Holds the extracted text + embeddings of files a user uploads in a chat, scoped
to that chat session (``memory_session_id`` = ``community:{id}:session:{sid}``).
Content is **durable and private**: it persists with the chat (no expiry) on a
local JSON file (the source of truth, so it survives restarts), with Redis used
as a best-effort read cache. A new chat gets a new session id and therefore
cannot see another chat's files. Nothing is written to the shared ``documents``
knowledge base.

Mirrors the durable on-disk pattern in ``app/agents/memory.py``.
"""
from __future__ import annotations

import json
import math
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

try:
    import redis
except Exception:
    redis = None

from app.core.config import (
    ATTACHMENT_CHUNK_OVERLAP,
    ATTACHMENT_CHUNK_SIZE,
    ATTACHMENT_MAX_CHARS,
    ATTACHMENT_MAX_FILES_PER_SESSION,
    ATTACHMENT_STORE_FILE,
    REDIS_DB,
    REDIS_HOST,
    REDIS_PORT,
)
from app.core.logger import get_logger

logger = get_logger("attachments")

_KEY_PREFIX = "kubo_attachments:"
_PREVIEW_CHARS = 600

try:
    if redis is None:
        raise RuntimeError("redis package is not installed")
    _redis_client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True
    )
    _redis_client.ping()
except Exception as exc:
    logger.error(f"Attachments: Redis unavailable ({exc}); using in-memory fallback.")
    _redis_client = None

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STORE_FILE = Path(
    ATTACHMENT_STORE_FILE or str(_REPO_ROOT / ".cache" / "kubocare_attachments.json")
)
# In-process cache of the durable store: {memory_session_id: [attachment_dict]}.
_memory_cache: dict[str, list[dict]] = {}


@dataclass
class Attachment:
    file_id: str
    filename: str
    preview: str
    chars: int
    n_units: int
    kind: str
    created_at: float
    chunks: list[dict]  # [{"text": str, "embedding": [float, ...]}]


# ----------------------------- chunking ---------------------------------

def chunk_text(text: str) -> list[str]:
    """Split text into overlapping chunks for embedding/retrieval.

    Reuses the same RecursiveCharacterTextSplitter the offline ingestion script
    uses. Falls back to a simple fixed-window split if the splitter is missing.
    """
    capped = (text or "")[:ATTACHMENT_MAX_CHARS]
    if not capped.strip():
        return []

    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=ATTACHMENT_CHUNK_SIZE,
            chunk_overlap=ATTACHMENT_CHUNK_OVERLAP,
            separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""],
        )
        chunks = [c.strip() for c in splitter.split_text(capped) if c.strip()]
        if chunks:
            return chunks
    except Exception as exc:  # pragma: no cover - depends on optional dep
        logger.error(f"Chunk splitter unavailable, using fallback: {exc}")

    step = max(1, ATTACHMENT_CHUNK_SIZE - ATTACHMENT_CHUNK_OVERLAP)
    return [capped[i : i + ATTACHMENT_CHUNK_SIZE] for i in range(0, len(capped), step)]


# ----------------------------- storage ----------------------------------

def _key(memory_session_id: str) -> str:
    return f"{_KEY_PREFIX}{memory_session_id}"


def _load_file_store() -> dict[str, list[dict]]:
    try:
        if not _STORE_FILE.exists():
            return {}
        with _STORE_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.error(f"Attachments: failed to load store file: {exc}")
        return {}


def _save_file_store(store: dict[str, list[dict]]) -> None:
    try:
        _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_file = _STORE_FILE.with_suffix(f"{_STORE_FILE.suffix}.tmp")
        with temp_file.open("w", encoding="utf-8") as handle:
            json.dump(store, handle)
        temp_file.replace(_STORE_FILE)
    except Exception as exc:
        logger.error(f"Attachments: failed to save store file: {exc}")


def _read(memory_session_id: str) -> list[dict]:
    if memory_session_id in _memory_cache:
        return _memory_cache[memory_session_id]

    key = _key(memory_session_id)
    if _redis_client:
        try:
            raw = _redis_client.get(key)
            if raw:
                data = json.loads(raw)
                items = data if isinstance(data, list) else []
                _memory_cache[memory_session_id] = items
                return items
        except Exception as exc:
            logger.error(f"Attachments: Redis read failed: {exc}")

    # Durable file is the source of truth (survives restarts / a Redis flush).
    items = _load_file_store().get(memory_session_id, [])
    _memory_cache[memory_session_id] = items
    if _redis_client and items:
        try:
            _redis_client.set(key, json.dumps(items))
        except Exception:
            pass
    return items


def _write(memory_session_id: str, items: list[dict]) -> None:
    key = _key(memory_session_id)
    if items:
        _memory_cache[memory_session_id] = items
    else:
        _memory_cache.pop(memory_session_id, None)

    # Durable, permanent on-disk store (no expiry) is the source of truth.
    store = _load_file_store()
    if items:
        store[memory_session_id] = items
    else:
        store.pop(memory_session_id, None)
    _save_file_store(store)

    # Best-effort Redis cache, written without a TTL so it never auto-expires.
    if _redis_client:
        try:
            if items:
                _redis_client.set(key, json.dumps(items))
            else:
                _redis_client.delete(key)
        except Exception as exc:
            logger.error(f"Attachments: Redis write failed: {exc}")


def add_attachment(
    memory_session_id: str,
    filename: str,
    chunks_with_embeddings: list[dict],
    preview: str,
    chars: int,
    n_units: int,
    kind: str,
) -> str:
    """Store a file's chunks for a session and return its file_id.

    Enforces the per-session file cap by dropping the oldest attachments.
    """
    items = _read(memory_session_id)
    file_id = f"file_{uuid.uuid4().hex[:12]}"
    items.append(
        {
            "file_id": file_id,
            "filename": filename,
            "preview": preview[:_PREVIEW_CHARS],
            "chars": chars,
            "n_units": n_units,
            "kind": kind,
            "created_at": time.time(),
            "chunks": chunks_with_embeddings,
        }
    )
    # Keep only the most recent N files.
    if len(items) > ATTACHMENT_MAX_FILES_PER_SESSION:
        items = items[-ATTACHMENT_MAX_FILES_PER_SESSION:]
    _write(memory_session_id, items)
    return file_id


def get_attachments(memory_session_id: str) -> list[Attachment]:
    """Return all active attachments for a session."""
    result = []
    for item in _read(memory_session_id):
        try:
            result.append(
                Attachment(
                    file_id=item["file_id"],
                    filename=item.get("filename", "file"),
                    preview=item.get("preview", ""),
                    chars=int(item.get("chars", 0)),
                    n_units=int(item.get("n_units", 0)),
                    kind=item.get("kind", ""),
                    created_at=float(item.get("created_at", 0.0)),
                    chunks=item.get("chunks", []),
                )
            )
        except Exception:
            continue
    return result


def list_attachments(memory_session_id: str) -> list[dict]:
    """Lightweight listing for the UI (no embeddings/chunks)."""
    return [
        {
            "file_id": a.file_id,
            "filename": a.filename,
            "chars": a.chars,
            "n_units": a.n_units,
            "kind": a.kind,
        }
        for a in get_attachments(memory_session_id)
    ]


def clear_attachment(memory_session_id: str, file_id: str) -> bool:
    """Remove a single attachment; returns True if something was removed."""
    items = _read(memory_session_id)
    remaining = [item for item in items if item.get("file_id") != file_id]
    if len(remaining) == len(items):
        return False
    _write(memory_session_id, remaining)
    return True


def clear_session_attachments(memory_session_id: str) -> None:
    """Remove all attachments for a session."""
    _write(memory_session_id, [])


# ----------------------------- retrieval ---------------------------------

def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a <= 0.0 or norm_b <= 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def retrieve_relevant_chunks(
    memory_session_id: str, query_embedding: list[float], k: int
) -> list[tuple[str, float, str]]:
    """Return the top-k (chunk_text, cosine_score, filename) for the question.

    Pure-Python cosine over the (small) set of this session's chunks — no
    pgvector schema changes needed.
    """
    if not query_embedding:
        return []

    scored: list[tuple[str, float, str]] = []
    for attachment in get_attachments(memory_session_id):
        for chunk in attachment.chunks:
            text = chunk.get("text", "")
            embedding = chunk.get("embedding") or []
            if not text or not embedding:
                continue
            scored.append((text, _cosine(query_embedding, embedding), attachment.filename))

    scored.sort(key=lambda row: row[1], reverse=True)
    return scored[: max(1, k)]


def retrieve_relevant_chunks_per_file(
    memory_session_id: str, query_embedding: list[float], per_file_k: int
) -> list[tuple[str, float, str]]:
    """Return the top ``per_file_k`` chunks for EACH attached file, combined.

    Guarantees every uploaded file is represented in the context (so a question
    or summary spanning multiple files doesn't ignore one of them). When no
    query embedding is available, falls back to each file's leading chunks.
    """
    results: list[tuple[str, float, str]] = []
    for attachment in get_attachments(memory_session_id):
        scored: list[tuple[str, float, str]] = []
        for chunk in attachment.chunks:
            text = chunk.get("text", "")
            embedding = chunk.get("embedding") or []
            if not text:
                continue
            score = _cosine(query_embedding, embedding) if query_embedding else 0.0
            scored.append((text, score, attachment.filename))
        scored.sort(key=lambda row: row[1], reverse=True)
        results.extend(scored[: max(1, per_file_k)])

    results.sort(key=lambda row: row[1], reverse=True)
    return results
