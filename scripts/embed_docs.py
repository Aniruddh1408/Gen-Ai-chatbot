import os
import sys
import json
import requests
import psycopg2
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Add parent dir to path so we can import from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

OLLAMA_EMBED_URL = os.getenv("EMBED_BASE_URL", "http://localhost:11434") + "/api/embeddings"
EMBED_MODEL = os.getenv("EMBED_MODEL", "mxbai-embed-large")
CHUNK_SIZE = 900
CHUNK_OVERLAP = 80
HTTP_SESSION = requests.Session()
HTTP_SESSION.trust_env = False

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5433")


def get_embedding(text):
    res = HTTP_SESSION.post(
        OLLAMA_EMBED_URL,
        json={"model": EMBED_MODEL, "prompt": text}
    )
    if res.status_code == 200:
        return res.json().get("embedding", [])
    print(f"[WARN] Failed to embed: {res.text}")
    return []


def build_chunks(content):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return [chunk.strip() for chunk in splitter.split_text(content) if chunk.strip()]


def main():
    docs_path = os.path.join(os.path.dirname(__file__), "../data/docs.txt")

    if not os.path.exists(docs_path):
        print(f"File not found: {docs_path}")
        return

    with open(docs_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.strip():
        print("docs.txt is empty. Add some text first!")
        return

    # Recursive chunking keeps paragraph meaning while handling longer sections better.
    chunks = build_chunks(content)

    print(f"Found {len(chunks)} chunks to embed.")

    # Connect directly for inserting (need write permissions)
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT
    )
    cur = conn.cursor()

    import datetime
    
    def parse_metadata(chunk_text):
        """
        Mimics advanced semantic or LLM-driven metadata extraction.
        This provides dimensions for Postgres Metadata filtering later.
        """
        meta = {
            "source": "docs.txt",
            "ingested_on": datetime.datetime.utcnow().isoformat() + "Z",
            "doc_type": "troubleshooting" if "error" in chunk_text.lower() or "flash" in chunk_text.lower() else "manual"
        }
        
        # Simple extraction of sensor categories
        if "temperature" in chunk_text.lower() or "moisture" in chunk_text.lower():
            meta["category"] = "environmental_sensors"
        elif "firmware" in chunk_text.lower() or "ota" in chunk_text.lower() or "wifi" in chunk_text.lower():
            meta["category"] = "system_hardware"
        else:
            meta["category"] = "general"
            
        return meta

    inserted = 0
    for chunk in chunks:
        embed = get_embedding(chunk)
        if not embed:
            continue

        embed_str = "[" + ",".join(map(str, embed)) + "]"
        doc_metadata = parse_metadata(chunk)

        try:
            cur.execute(
                "INSERT INTO documents (content, embedding, metadata) VALUES (%s, %s::vector, %s)",
                (chunk, embed_str, json.dumps(doc_metadata))
            )
            inserted += 1
            print(f"Inserted chunk {inserted}...")
        except Exception as e:
            print(f"Database error on insert: {e}")
            conn.rollback()

    conn.commit()
    cur.close()
    conn.close()

    print(f"Successfully embedded and stored {inserted} document chunks!")


if __name__ == "__main__":
    main()
