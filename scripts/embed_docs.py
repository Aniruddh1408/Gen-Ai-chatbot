# ===========================================================================
# This is a helper script you run by hand, not part of the live app. It reads
# the documents in data/docs/, splits them into chunks, turns each chunk into a
# search-vector, and loads them into the database so the assistant can search
# them later. Re-run it whenever those documents change.
# ===========================================================================
import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Add parent dir to path so imports work when the script is run directly.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_ROOT / "data" / "docs"
LEGACY_DOC_FILE = PROJECT_ROOT / "data" / "docs.txt"

EMBED_URL = os.getenv("EMBED_BASE_URL", "http://localhost:11434") + "/api/embeddings"
EMBED_MODEL = os.getenv("EMBED_MODEL", "mxbai-embed-large")
EMBED_DIM = int(os.getenv("EMBED_DIM", "1024"))
CHUNK_SIZE = int(os.getenv("DOC_CHUNK_SIZE", "900"))
CHUNK_OVERLAP = int(os.getenv("DOC_CHUNK_OVERLAP", "80"))
CHUNKING_MODE = os.getenv("DOC_CHUNKING_MODE", "hybrid").strip().lower()
SUPPORTED_EXTENSIONS = {".md", ".txt"}
SUPPORTED_CHUNKING_MODES = {"hybrid", "recursive"}
MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

HTTP_SESSION = requests.Session()
HTTP_SESSION.trust_env = False

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5433")


@dataclass(frozen=True)
class DocumentChunk:
    text: str
    heading_path: tuple[str, ...] = ()
    section_heading: str | None = None
    chunking_mode: str = "hybrid"


@dataclass(frozen=True)
class MarkdownSection:
    body: str
    heading_path: tuple[str, ...] = ()


def normalize_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.strip().splitlines())


def sha256_text(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def get_embedding(text: str) -> list[float]:
    response = HTTP_SESSION.post(
        EMBED_URL,
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=60,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Embedding failed: {response.status_code} {response.text}")

    embedding = response.json().get("embedding", [])
    if len(embedding) != EMBED_DIM:
        raise RuntimeError(f"Expected embedding dimension {EMBED_DIM}, got {len(embedding)}")
    return embedding


def _recursive_split(content: str, chunk_size: int | None = None) -> list[str]:
    safe_chunk_size = max(int(chunk_size or CHUNK_SIZE), 1)
    safe_overlap = min(CHUNK_OVERLAP, max(safe_chunk_size - 1, 0))
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=safe_chunk_size,
        chunk_overlap=safe_overlap,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""],
    )
    return [chunk.strip() for chunk in splitter.split_text(content) if chunk.strip()]


def _parse_markdown_sections(content: str) -> list[MarkdownSection]:
    sections: list[MarkdownSection] = []
    heading_stack: list[tuple[int, str]] = []
    current_lines: list[str] = []
    current_path: tuple[str, ...] = ()

    def flush_section() -> None:
        body = normalize_text("\n".join(current_lines))
        if body:
            sections.append(MarkdownSection(body=body, heading_path=current_path))

    for line in content.splitlines():
        match = MARKDOWN_HEADING_RE.match(line.strip())
        if not match:
            current_lines.append(line)
            continue

        flush_section()
        current_lines = []

        level = len(match.group(1))
        title = match.group(2).strip()
        heading_stack = [(item_level, item_title) for item_level, item_title in heading_stack if item_level < level]
        heading_stack.append((level, title))
        current_path = tuple(item_title for _, item_title in heading_stack)

    flush_section()
    return sections


def _format_heading_prefix(heading_path: tuple[str, ...]) -> str:
    return "\n".join(
        f"{'#' * min(index + 1, 6)} {heading}"
        for index, heading in enumerate(heading_path)
    )


def _section_to_chunks(section: MarkdownSection, mode: str) -> list[DocumentChunk]:
    prefix = _format_heading_prefix(section.heading_path)
    available_size = CHUNK_SIZE - len(prefix) - 2
    body_chunk_size = available_size if available_size >= max(300, CHUNK_SIZE // 2) else CHUNK_SIZE

    chunks: list[DocumentChunk] = []
    for body_chunk in _recursive_split(section.body, chunk_size=body_chunk_size):
        text = f"{prefix}\n\n{body_chunk}".strip() if prefix else body_chunk
        chunks.append(
            DocumentChunk(
                text=text,
                heading_path=section.heading_path,
                section_heading=section.heading_path[-1] if section.heading_path else None,
                chunking_mode=mode,
            )
        )
    return chunks


def build_document_chunks(content: str, chunking_mode: str | None = None) -> list[DocumentChunk]:
    mode = (chunking_mode or CHUNKING_MODE).strip().lower()
    if mode not in SUPPORTED_CHUNKING_MODES:
        raise ValueError(
            f"Unsupported chunking mode '{mode}'. "
            f"Use one of: {', '.join(sorted(SUPPORTED_CHUNKING_MODES))}."
        )

    if mode == "recursive":
        return [
            DocumentChunk(text=chunk, chunking_mode=mode)
            for chunk in _recursive_split(content)
        ]

    sections = _parse_markdown_sections(content)
    if not sections:
        sections = [MarkdownSection(body=content)]

    chunks: list[DocumentChunk] = []
    for section in sections:
        chunks.extend(_section_to_chunks(section, mode))

    return chunks


def build_chunks(content: str, chunking_mode: str | None = None) -> list[str]:
    return [chunk.text for chunk in build_document_chunks(content, chunking_mode=chunking_mode)]


def connect_db():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        host=DB_HOST,
        port=DB_PORT,
    )


def ensure_schema(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS document_sources (
            source_id TEXT PRIMARY KEY,
            source_title TEXT,
            source_path TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            metadata JSONB DEFAULT '{}'::jsonb,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_id TEXT;")
    cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_title TEXT;")
    cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_path TEXT;")
    cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS chunk_index INTEGER;")
    cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS chunk_hash TEXT;")
    cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_model TEXT;")
    cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS embedding_dim INTEGER;")
    cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;")
    cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
    cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS documents_chunk_hash_idx ON documents (chunk_hash);")
    cur.execute("CREATE INDEX IF NOT EXISTS documents_active_model_idx ON documents (is_active, embedding_model);")
    cur.execute("CREATE INDEX IF NOT EXISTS documents_source_idx ON documents (source_id, is_active);")


def source_id_for(path: Path) -> str:
    relative_path = path.relative_to(PROJECT_ROOT).as_posix()
    return hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:16]


def title_for(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").title()


def parse_metadata(path: Path, chunk_text: str, chunk: DocumentChunk | None = None) -> dict:
    text = chunk_text.lower()
    path_text = path.as_posix().lower()
    metadata = {
        "source": path.relative_to(PROJECT_ROOT).as_posix(),
        "file_type": path.suffix.lstrip("."),
        "chunking_mode": chunk.chunking_mode if chunk else CHUNKING_MODE,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
    }

    if chunk and chunk.heading_path:
        metadata["heading_path"] = list(chunk.heading_path)
        metadata["section_heading"] = chunk.section_heading

    if any(term in text for term in ["error", "alarm", "alert", "blink", "flashing", "troubleshoot"]):
        metadata["doc_type"] = "troubleshooting"
    elif any(term in text for term in ["policy", "escalation", "handoff", "sop"]):
        metadata["doc_type"] = "procedure"
    else:
        metadata["doc_type"] = "reference"

    if any(term in text for term in ["wifi", "firmware", "ota", "gateway", "battery", "sensor"]):
        metadata["category"] = "device_operations"
    elif any(term in text for term in ["resident", "clinical", "vital", "blood pressure", "sleep", "glucose"]):
        metadata["category"] = "clinical_operations"
    elif "privacy" in text or "hipaa" in text or "security" in text:
        metadata["category"] = "privacy_security"
    else:
        metadata["category"] = "general"

    if "healthcare" in path_text or "clinical" in path_text:
        metadata["domain"] = "healthcare"
    elif "device" in path_text:
        metadata["domain"] = "device"
    else:
        metadata["domain"] = "operations"

    return metadata


def discover_sources() -> list[Path]:
    sources = []
    if DOCS_DIR.exists():
        sources.extend(
            path for path in sorted(DOCS_DIR.rglob("*"))
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )
    if LEGACY_DOC_FILE.exists():
        sources.append(LEGACY_DOC_FILE)
    return sources


def upsert_source(cur, path: Path, content_hash: str, metadata: dict):
    source_id = source_id_for(path)
    source_title = title_for(path)
    source_path = path.relative_to(PROJECT_ROOT).as_posix()
    cur.execute(
        """
        INSERT INTO document_sources (
            source_id, source_title, source_path, source_hash, metadata, is_active, updated_at
        )
        VALUES (%s, %s, %s, %s, %s::jsonb, TRUE, CURRENT_TIMESTAMP)
        ON CONFLICT (source_id) DO UPDATE SET
            source_title = EXCLUDED.source_title,
            source_path = EXCLUDED.source_path,
            source_hash = EXCLUDED.source_hash,
            metadata = EXCLUDED.metadata,
            is_active = TRUE,
            updated_at = CURRENT_TIMESTAMP;
        """,
        (source_id, source_title, source_path, content_hash, json.dumps(metadata)),
    )
    return source_id, source_title, source_path


def ingest_source(cur, path: Path, dry_run: bool = False, chunking_mode: str | None = None) -> dict:
    content = path.read_text(encoding="utf-8")
    normalized_content = normalize_text(content)
    if not normalized_content:
        return {"source": str(path), "chunks": 0, "inserted": 0, "skipped": 0, "deactivated": 0}

    source_hash = sha256_text(normalized_content)
    source_metadata = {"source": path.relative_to(PROJECT_ROOT).as_posix(), "source_hash": source_hash}
    source_id, source_title, source_path = upsert_source(cur, path, source_hash, source_metadata)
    chunks = build_document_chunks(normalized_content, chunking_mode=chunking_mode)

    stats = {"source": source_path, "chunks": len(chunks), "inserted": 0, "skipped": 0, "deactivated": 0}
    active_hashes = []

    for chunk_index, chunk in enumerate(chunks):
        chunk_hash = sha256_text(f"{source_id}:{chunk_index}:{chunk.text}")
        active_hashes.append(chunk_hash)

        cur.execute(
            "SELECT id FROM documents WHERE chunk_hash = %s AND embedding_model = %s",
            (chunk_hash, EMBED_MODEL),
        )
        existing = cur.fetchone()
        if existing:
            cur.execute(
                """
                UPDATE documents
                SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (existing[0],),
            )
            stats["skipped"] += 1
            continue

        if dry_run:
            stats["inserted"] += 1
            continue

        embedding = get_embedding(chunk.text)
        embed_str = "[" + ",".join(map(str, embedding)) + "]"
        metadata = parse_metadata(path, chunk.text, chunk)
        metadata.update({
            "chunk_hash": chunk_hash,
            "source_id": source_id,
            "embedding_model": EMBED_MODEL,
            "embedding_dim": EMBED_DIM,
        })

        cur.execute(
            """
            INSERT INTO documents (
                source_id, source_title, source_path, chunk_index, chunk_hash,
                content, embedding, embedding_model, embedding_dim, metadata,
                is_active, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s, %s, %s::jsonb, TRUE, CURRENT_TIMESTAMP)
            ON CONFLICT (chunk_hash) DO UPDATE SET
                content = EXCLUDED.content,
                embedding = EXCLUDED.embedding,
                embedding_model = EXCLUDED.embedding_model,
                embedding_dim = EXCLUDED.embedding_dim,
                metadata = EXCLUDED.metadata,
                is_active = TRUE,
                updated_at = CURRENT_TIMESTAMP;
            """,
            (
                source_id, source_title, source_path, chunk_index, chunk_hash,
                chunk.text, embed_str, EMBED_MODEL, EMBED_DIM, json.dumps(metadata),
            ),
        )
        stats["inserted"] += 1

    if active_hashes and not dry_run:
        cur.execute(
            """
            UPDATE documents
            SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
            WHERE source_id = %s
              AND embedding_model = %s
              AND NOT (chunk_hash = ANY(%s))
            """,
            (source_id, EMBED_MODEL, active_hashes),
        )
        stats["deactivated"] = cur.rowcount

    return stats


def deactivate_missing_sources(cur, active_source_ids: set[str], dry_run: bool = False) -> int:
    cur.execute("SELECT source_id FROM document_sources WHERE is_active = TRUE")
    existing_source_ids = {row[0] for row in cur.fetchall()}
    missing_source_ids = sorted(existing_source_ids - active_source_ids)
    if not missing_source_ids or dry_run:
        return len(missing_source_ids)

    cur.execute(
        "UPDATE document_sources SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE source_id = ANY(%s)",
        (missing_source_ids,),
    )
    cur.execute(
        "UPDATE documents SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE source_id = ANY(%s)",
        (missing_source_ids,),
    )
    return len(missing_source_ids)


def rebuild(cur):
    cur.execute("UPDATE documents SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE embedding_model = %s", (EMBED_MODEL,))
    cur.execute("UPDATE document_sources SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP")


def main():
    parser = argparse.ArgumentParser(description="Incrementally embed production documentation.")
    parser.add_argument("--rebuild", action="store_true", help="Deactivate existing chunks before ingesting current docs.")
    parser.add_argument("--dry-run", action="store_true", help="Scan files without embedding or writing chunks.")
    parser.add_argument(
        "--chunking-mode",
        choices=sorted(SUPPORTED_CHUNKING_MODES),
        default=CHUNKING_MODE if CHUNKING_MODE in SUPPORTED_CHUNKING_MODES else "hybrid",
        help="Use 'hybrid' for Markdown section-aware recursive chunking or 'recursive' for the legacy splitter.",
    )
    args = parser.parse_args()

    sources = discover_sources()
    if not sources:
        print(f"No docs found. Add .md or .txt files under {DOCS_DIR}")
        return

    conn = connect_db()
    try:
        cur = conn.cursor()
        ensure_schema(cur)
        if args.rebuild:
            rebuild(cur)

        totals = {"chunks": 0, "inserted": 0, "skipped": 0, "deactivated": 0}
        active_source_ids = set()
        for path in sources:
            active_source_ids.add(source_id_for(path))
            stats = ingest_source(cur, path, dry_run=args.dry_run, chunking_mode=args.chunking_mode)
            for key in totals:
                totals[key] += stats[key]
            print(
                f"{stats['source']}: mode={args.chunking_mode} chunks={stats['chunks']} "
                f"inserted={stats['inserted']} skipped={stats['skipped']} "
                f"deactivated={stats['deactivated']}"
            )

        missing_count = deactivate_missing_sources(cur, active_source_ids, dry_run=args.dry_run)
        if args.dry_run:
            conn.rollback()
            print("Dry run complete. No database changes were committed.")
        else:
            conn.commit()
            print(
                "Ingestion complete: "
                f"chunks={totals['chunks']} inserted={totals['inserted']} "
                f"skipped={totals['skipped']} deactivated={totals['deactivated']} "
                f"missing_sources_deactivated={missing_count}"
            )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
