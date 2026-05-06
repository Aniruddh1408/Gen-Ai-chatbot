"""
Vector (RAG) Retriever - Semantic search via pgvector + LangChain answer chain.
"""
from pathlib import Path

import requests

from app.core.config import EMBED_BASE_URL, EMBED_MODEL
from app.core.db import run_query
from app.core.logger import get_logger
from app.llm.client import ask_llm

logger = get_logger("vector_retriever")

EMBED_URL = f"{EMBED_BASE_URL}/api/embeddings"
_HTTP_SESSION = requests.Session()
_HTTP_SESSION.trust_env = False
_MAX_RAG_DISTANCE = 0.91
_DOC_GUARDRAIL_DISTANCE = 0.93
_DOCS_DIR = Path("data/docs")


def get_embedding(text: str) -> list[float] | None:
    """Get embedding vector from the configured embedding backend."""
    try:
        res = _HTTP_SESSION.post(
            EMBED_URL,
            json={"model": EMBED_MODEL, "prompt": text},
            timeout=30,
        )
        if res.status_code == 200:
            embedding = res.json().get("embedding", [])
            return embedding if embedding else None

        logger.warning(f"Embedding request failed: {res.text}")
    except requests.RequestException as exc:
        logger.error(f"Embedding request error: {exc}")

    return None


def get_top_document_distance(query: str) -> float | None:
    """Return the nearest active documentation distance for guardrails/routing."""
    query_embed = get_embedding(query)
    if not query_embed:
        return None

    embed_str = "[" + ",".join(map(str, query_embed)) + "]"
    try:
        rows = run_query(
            """
            SELECT embedding <-> %s::vector AS distance
            FROM documents
            WHERE is_active = TRUE
              AND embedding_model = %s
            ORDER BY distance
            LIMIT 1;
            """,
            (embed_str, EMBED_MODEL),
        )
    except Exception as exc:
        logger.error(f"Documentation relevance check failed: {exc}")
        return None

    if not rows:
        return None
    return float(rows[0][0])


def has_relevant_documentation(query: str, max_distance: float = _DOC_GUARDRAIL_DISTANCE) -> bool:
    """Allow newly added documentation topics without hardcoding every keyword."""
    distance = get_top_document_distance(query)
    if distance is None:
        return False
    return distance <= max_distance


_NOT_FOUND_ANSWER = "I couldn't find that in the documentation."

_RAG_SYSTEM_PROMPT = """You are a strictly documentation-grounded assistant.
Answer the user's question ONLY if the retrieved Context directly contains the answer.
If the Context is related to the broad domain but does not directly answer the exact question, reply ONLY with:
"I couldn't find that in the documentation."
Do not use outside knowledge, assumptions, or general explanations that are not present in the Context.

Formatting rules:
- Be concise by default.
- For troubleshooting or procedural questions, answer in short bullet points.
- Prefer this structure when relevant:
  1. Meaning
  2. What to do
  3. What not to do
  4. When to check/escalate
- Do not produce long dense paragraphs unless the user explicitly asks for detail.
"""

_SECTION_PATTERNS = [
    (["e-404", "error code"], ["Error Code E-404"]),
    (["blinking red", "red light", "flashing red"], ["Rapid Blinking Red Light"]),
    (["sleep mode", "green light"], ["Sleep Mode Indicator"]),
    (["temperature", "overheating", "protection mode"], ["Temperature Protection Mode"]),
    (["moisture", "recalibrat", "calibration"], ["Moisture Sensor Recalibration"]),
    (["maintenance"], ["General Maintenance"]),
    (["technical staff", "technical escalation"], ["When To Escalate To Technical Staff"]),
    (["clinical staff", "clinical escalation"], ["When To Escalate To Clinical Staff", "Clinical Escalation Boundaries"]),
    (["privacy", "security"], ["Privacy And Security"]),
    (["documentation versus database", "source of truth"], ["Documentation Versus Database"]),
]


def _extract_markdown_section(context: str, headings: list[str]) -> str | None:
    lines = context.splitlines()
    heading_indexes: list[int] = []

    for index, line in enumerate(lines):
        normalized = line.strip().lstrip("#").strip().lower()
        if any(heading.lower() == normalized for heading in headings):
            heading_indexes.append(index)

    if not heading_indexes:
        return None

    start = heading_indexes[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped == "---" or stripped.startswith("## "):
            end = index
            break

    section_lines = [
        line.strip()
        for line in lines[start:end]
        if line.strip() and not line.strip().startswith("Source:")
    ]
    if not section_lines:
        return None

    if section_lines[0].startswith("## "):
        section_lines[0] = section_lines[0].lstrip("#").strip()

    return "\n".join(section_lines[:28])


def _load_section_from_local_docs(headings: list[str]) -> str | None:
    if not _DOCS_DIR.exists():
        return None

    for path in sorted(_DOCS_DIR.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue

        section = _extract_markdown_section(content, headings)
        if section:
            return section

    return None


def _section_document_answer(query: str, context: str) -> str | None:
    q_lower = query.lower()
    for triggers, headings in _SECTION_PATTERNS:
        if any(trigger in q_lower for trigger in triggers):
            section = _load_section_from_local_docs(headings) or _extract_markdown_section(context, headings)
            if section:
                return section
    return None


def _fallback_document_answer(query: str, context: str) -> str:
    section_answer = _section_document_answer(query, context)
    if section_answer:
        return section_answer

    compact_lines = []
    for line in context.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Source:"):
            continue
        if stripped.startswith("# "):
            continue
        compact_lines.append(stripped.lstrip("#").strip())
        if len(compact_lines) >= 12:
            break

    if compact_lines:
        return "\n".join(compact_lines)

    return _NOT_FOUND_ANSWER


def handle_rag(query: str) -> dict:
    """Full RAG pipeline: embed query -> pgvector search -> LLM answer."""
    local_answer = _section_document_answer(query, "")
    if local_answer:
        return {
            "query": query,
            "retrieved_context": "local documentation section",
            "answer": local_answer,
        }

    query_embed = get_embedding(query)
    if not query_embed:
        return {
            "query": query,
            "retrieved_context": "",
            "answer": "I couldn't access the documentation retriever right now. Please try again shortly.",
        }

    embed_str = "[" + ",".join(map(str, query_embed)) + "]"

    search_sql = """
    SELECT content, source_title, source_path, embedding <-> %s::vector AS distance
    FROM documents
    WHERE is_active = TRUE
      AND embedding_model = %s
    ORDER BY distance
    LIMIT 3;
    """

    try:
        results = run_query(search_sql, (embed_str, EMBED_MODEL))
        if not results:
            return {
                "query": query,
                "retrieved_context": "",
                "answer": _NOT_FOUND_ANSWER,
            }

        top_distance = float(results[0][3])
        if top_distance > _MAX_RAG_DISTANCE:
            logger.info(f"RAG match rejected by distance threshold: {top_distance:.3f}")
            return {
                "query": query,
                "retrieved_context": "",
                "answer": _NOT_FOUND_ANSWER,
            }

        filtered_results = [row for row in results if float(row[3]) <= (_MAX_RAG_DISTANCE + 0.08)]
        context = "\n---\n".join(
            f"Source: {row[1] or row[2]}\n{row[0]}"
            for row in filtered_results
        )
        section_answer = _section_document_answer(query, context)
        if section_answer:
            return {
                "query": query,
                "retrieved_context": context,
                "answer": section_answer,
            }

    except Exception as exc:
        logger.error(f"RAG vector search failed: {exc}")
        return {
            "query": query,
            "retrieved_context": "",
            "answer": "I couldn't access the documentation database right now.",
        }

    try:
        answer = ask_llm(
            f"Context:\n{context}\n\nUser Query: {query}",
            system_prompt=_RAG_SYSTEM_PROMPT,
            num_predict=180,
        )
    except Exception as exc:
        logger.error(f"RAG answer generation failed: {exc}")
        fallback_answer = _fallback_document_answer(query, context)
        return {
            "query": query,
            "retrieved_context": context,
            "answer": fallback_answer,
        }

    legacy_not_found_phrases = [
        "I don't have recorded documentation for that specific resident or medical topic.",
        "I do not have recorded documentation for that specific resident or medical topic.",
    ]
    if answer.strip() in legacy_not_found_phrases:
        answer = _NOT_FOUND_ANSWER

    return {
        "query": query,
        "retrieved_context": context,
        "answer": answer,
    }
