"""
Vector (RAG) Retriever — Semantic search via pgvector + LangChain answer chain.
"""
import requests
from app.llm.client import ask_llm
from app.core.db import run_query
from app.core.config import EMBED_BASE_URL, EMBED_MODEL
from app.core.logger import get_logger

logger = get_logger("vector_retriever")

OLLAMA_EMBED_URL = f"{EMBED_BASE_URL}/api/embeddings"
_HTTP_SESSION = requests.Session()
_HTTP_SESSION.trust_env = False


def get_embedding(text: str) -> list[float]:
    """Get embedding vector from Ollama's embedding model."""
    try:
        res = _HTTP_SESSION.post(
            OLLAMA_EMBED_URL,
            json={"model": EMBED_MODEL, "prompt": text},
            timeout=30,
        )
        if res.status_code == 200:
            return res.json().get("embedding", [])

        logger.warning(f"Embedding request failed: {res.text}")
    except requests.RequestException as e:
        logger.error(f"Embedding request error: {e}")

    # Fallback to a zero vector to prevent crashes
    return [0.0] * 1024


_RAG_SYSTEM_PROMPT = """You are a strictly logical assistant.
Compare the Context to the User Query. If the Context describes IoT/Hardware (sensors, signals, routers) but the User is asking about Medical/Resident info (names, health, medications), do NOT attempt to answer.
Reply ONLY with: 'I don't have recorded documentation for that specific resident or medical topic.'
Answer the user's question ONLY if the context directly contains the answer.
"""


def handle_rag(query: str) -> dict:
    """Full RAG pipeline: embed query → pgvector search → LLM answer."""
    # 1. Embed the query
    query_embed = get_embedding(query)
    embed_str = "[" + ",".join(map(str, query_embed)) + "]"

    # 2. Search Postgres using pgvector, compare each document’s stored vector with the query vector, and retrieve the top 3 most similar documents.
    search_sql = """
    SELECT content
    FROM documents
    ORDER BY embedding <-> %s::vector  
    LIMIT 3;
    """

    try:
        results = run_query(search_sql, (embed_str,))

        if not results:
            context = "No specific documentation context found in the database."
        else:
            context = "\n---\n".join([row[0] for row in results])

    except Exception as e:
        logger.error(f"RAG vector search failed: {e}")
        context = "Database vector search failed."

    # 3. Generate answer via LangChain chain
    try:
        answer = ask_llm(
            f"Context:\n{context}\n\nUser Query: {query}",
            system_prompt=_RAG_SYSTEM_PROMPT,
        )
    except Exception as e:
        logger.error(f"RAG answer generation failed: {e}")
        return {
            "query": query,
            "retrieved_context": context,
            "error": str(e),
            "answer": "I found relevant documentation, but the local language model took too long to generate the final response.",
        }

    return {
        "query": query,
        "retrieved_context": context,
        "answer": answer,
    }
