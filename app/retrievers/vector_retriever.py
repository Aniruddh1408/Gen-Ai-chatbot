"""
Vector (RAG) Retriever — Semantic search via pgvector + LangChain answer chain.
"""
import requests
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.llm.client import llm
from app.core.db import run_query
from app.core.config import OLLAMA_BASE_URL, EMBED_MODEL
from app.core.logger import get_logger

logger = get_logger("vector_retriever")

OLLAMA_EMBED_URL = f"{OLLAMA_BASE_URL}/api/embeddings"


def get_embedding(text: str) -> list[float]:
    """Get embedding vector from Ollama's embedding model."""
    try:
        res = requests.post(
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


# ----------------------------
# RAG Answer Chain
# ----------------------------
_rag_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a strictly logical help-desk assistant for an IoT device system.
You MUST NOT output a JSON format. You must reply in plain English sentences.
Read the provided context line-by-line. Answer the user's question EXACTLY as described in the context.
If the context says "Do NOT do X", then you MUST tell the user "Do not do X".
If the context does not contain the answer, reply "I don't have enough information".

Context:
{context}"""),
    ("human", "{query}"),
])

_rag_chain = _rag_prompt | llm | StrOutputParser()


def handle_rag(query: str) -> dict:
    """Full RAG pipeline: embed query → pgvector search → LLM answer."""
    # 1. Embed the query
    query_embed = get_embedding(query)
    embed_str = "[" + ",".join(map(str, query_embed)) + "]"

    # 2. Search Postgres using pgvector
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
    answer = _rag_chain.invoke({"context": context, "query": query})

    return {
        "query": query,
        "retrieved_context": context,
        "answer": answer,
    }