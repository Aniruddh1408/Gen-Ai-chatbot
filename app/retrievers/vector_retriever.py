"""
Vector (RAG) Retriever - Semantic search via pgvector + LangChain answer chain.
"""
import requests

from app.core.config import EMBED_BASE_URL, EMBED_MODEL
from app.core.db import run_query
from app.core.logger import get_logger
from app.llm.client import ask_llm

logger = get_logger("vector_retriever")

OLLAMA_EMBED_URL = f"{EMBED_BASE_URL}/api/embeddings"
_HTTP_SESSION = requests.Session()
_HTTP_SESSION.trust_env = False
_MAX_RAG_DISTANCE = 0.82


def get_embedding(text: str) -> list[float] | None:
    """Get embedding vector from Ollama's embedding model."""
    try:
        res = _HTTP_SESSION.post(
            OLLAMA_EMBED_URL,
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


_RAG_SYSTEM_PROMPT = """You are a strictly logical assistant.
Compare the Context to the User Query. If the Context describes IoT/Hardware (sensors, signals, routers) but the User is asking about Medical/Resident info (names, health, medications), do NOT attempt to answer.
Reply ONLY with: 'I don't have recorded documentation for that specific resident or medical topic.'
Answer the user's question ONLY if the context directly contains the answer.

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


def handle_rag(query: str) -> dict:
    """Full RAG pipeline: embed query -> pgvector search -> LLM answer."""
    query_embed = get_embedding(query)
    if not query_embed:
        return {
            "query": query,
            "retrieved_context": "",
            "answer": "I couldn't access the documentation retriever right now. Please try again shortly.",
        }

    embed_str = "[" + ",".join(map(str, query_embed)) + "]"

    search_sql = """
    SELECT content, embedding <-> %s::vector AS distance
    FROM documents
    ORDER BY distance
    LIMIT 3;
    """

    try:
        results = run_query(search_sql, (embed_str,))
        if not results:
            return {
                "query": query,
                "retrieved_context": "",
                "answer": "I couldn't find that in the documentation.",
            }

        top_distance = float(results[0][1])
        if top_distance > _MAX_RAG_DISTANCE:
            logger.info(f"RAG match rejected by distance threshold: {top_distance:.3f}")
            return {
                "query": query,
                "retrieved_context": "",
                "answer": "I couldn't find that in the documentation.",
            }

        filtered_results = [row for row in results if float(row[1]) <= (_MAX_RAG_DISTANCE + 0.08)]
        context = "\n---\n".join([row[0] for row in filtered_results])

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
        return {
            "query": query,
            "retrieved_context": context,
            "error": str(exc),
            "answer": "I found relevant documentation, but the local language model took too long to generate the final response.",
        }

    return {
        "query": query,
        "retrieved_context": context,
        "answer": answer,
    }
