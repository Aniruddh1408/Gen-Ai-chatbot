# GenAI Assistant

> A grounded, role-aware question-answering backend for senior-living care dashboards.

GenAI Assistant lets a caregiver ask a question in plain English — *"How did this
resident sleep last night?"*, *"Who needs the most attention today?"*, *"How do I recalibrate
the sensor?"* — and returns a precise, evidence-backed answer. Instead of handing every
question to a single model, it routes each one to the right source and refuses to invent
answers it cannot ground.

---

## Table of contents

- [Key features](#key-features)
- [How it works](#how-it-works)
- [What it can and cannot answer](#what-it-can-and-cannot-answer)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Testing](#testing)
- [Security model](#security-model)
- [License](#license)

---

## Key features

- **Smart routing** — each question is sent to the source most likely to answer it:
  the database, the document library, or direct chat.
- **Safe, read-only SQL** — generated queries are validated and restricted to read-only
  operations before they ever touch the database.
- **Grounded answers** — every answer that names a resident is verified against the real
  roster before it is returned, so the assistant cannot leak or confuse people across
  communities.
- **Document Q&A** — how-to and policy questions are answered from the written care and
  device guides via semantic (vector) search.
- **Private file uploads** — a user can attach a document and ask about it; the file stays
  scoped to that one chat session.
- **Role & community isolation** — every request is locked to the community (and role) the
  caller is allowed to see.
- **Honest fallbacks** — when evidence is insufficient, the assistant says *"I don't have
  that"* rather than guessing.
- **Conversational memory** — follow-ups like *"what about her heart rate?"* are resolved
  against recent chat history.

## How it works

Every message flows through a fixed [LangGraph](https://langchain-ai.github.io/langgraph/)
pipeline:

```
load context → community check → reshape previous answer (if asked)
   → rewrite with memory → split multi-questions → input guardrail
   → answer from attachments (if relevant) → route (SQL / vector / chat)
   → output guardrail → save memory → finalize
```

The router classifies each question and dispatches it:

| Question type | Source | Example |
| --- | --- | --- |
| Structured / data | Read-only SQL over the database | "Who slept the longest last night?" |
| How-to / policy | Vector search over care & device guides | "How do I recalibrate the sensor?" |
| Casual / general | Direct chat, no retrieval | "Thanks, that helps!" |
| About an upload | Semantic search over the attached file | "Summarize the document I just sent." |

Login and identity are owned by the dashboard, which sends the community and user with each
request. This service re-verifies that access before reading anything.

## What it can and cannot answer

The sensors are radar-based, so the assistant can report on **heart rate, respiration,
sleep, activity, wellness scores, and falls**, plus **resident profiles** (age, room,
medical history) and a *"who needs care first"* triage hint for staff.

It does **not** track blood pressure, blood sugar, weight, or medications. Asked for those,
it says so plainly instead of inventing a number.

## Tech stack

| Layer | Technology |
| --- | --- |
| API | [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/) |
| Orchestration | [LangGraph](https://langchain-ai.github.io/langgraph/), [LangChain](https://www.langchain.com/) |
| Generation LLM | OpenAI-compatible endpoint (vLLM), default `Qwen/Qwen2.5-7B-Instruct-AWQ` |
| Embeddings | [Ollama](https://ollama.com/), default `mxbai-embed-large` |
| Database | PostgreSQL (`psycopg2`) |
| SQL validation | [sqlglot](https://github.com/tobymao/sqlglot) |
| Conversational memory | Redis |
| File parsing | `pypdf`, `python-docx`, `openpyxl` |

## Project structure

```text
app/
  agents/      input/output guardrails, chat memory, routing,
               answer grounding, and the uploaded-file store
  api/         the FastAPI web server and its endpoints
  core/        config, database access, logging, community/role rules
  graph/       the step-by-step request pipeline (LangGraph)
  ingest/      text extraction from uploaded files
  llm/         the generation-model client
  retrievers/  the data ("text-to-SQL") and document-search paths
  schema/      the map of what data exists
data/docs/     the care and device guides the assistant reads
scripts/       loads and embeds the guides so they can be searched
tests/         automated tests
```

## Getting started

### Prerequisites

- Python 3.10+
- A reachable PostgreSQL database
- A running Redis instance (for conversational memory)
- An OpenAI-compatible LLM endpoint (e.g. vLLM) for generation
- An Ollama server for embeddings

### Installation

1. **Create a virtual environment and install dependencies:**

   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. **Configure your environment.** Create a `.env` file in the project root (see
   [Configuration](#configuration)). Keep real credentials out of source control.

3. **Embed the care and device guides:**

   ```powershell
   .\venv\Scripts\python.exe scripts\embed_docs.py
   ```

4. **Start the server:**

   ```powershell
   uvicorn app.api.main:app --reload --port 8001
   ```

5. **Open the chat UI** at [http://127.0.0.1:8001/](http://127.0.0.1:8001/).

## Configuration

All settings are read from environment variables in `app/core/config.py`. Sensible defaults
are provided for everything except the database credentials.

### Database

| Variable | Description | Default |
| --- | --- | --- |
| `DB_NAME` | Database name | _(required)_ |
| `DB_USER` | Database user | _(required)_ |
| `DB_PASS` | Database password | _(required)_ |
| `DB_HOST` | Database host | _(required)_ |
| `DB_PORT` | Database port | _(required)_ |
| `DB_POOL_MIN` | Minimum pooled connections | `1` |
| `DB_POOL_MAX` | Maximum pooled connections | `10` |

### Generation LLM

| Variable | Description | Default |
| --- | --- | --- |
| `LLM_BASE_URL` | OpenAI-compatible base URL | `Any URL` |
| `LLM_API_KEY` | API key for the LLM endpoint | `dummy` |
| `LLM_MODEL` | Model name | `Qwen/Qwen2.5-7B-Instruct-AWQ` |
| `LLM_DATA_TEMPERATURE` | Temperature for data answers | `0.0` |
| `LLM_CHAT_TEMPERATURE` | Temperature for chat answers | `0.2` |
| `LLM_TIMEOUT_SECONDS` | Request timeout (`none`/`0` disables) | _(disabled)_ |
| `LLM_NUM_CTX` | Context window size | `2048` |
| `LLM_KEEP_ALIVE` | Model keep-alive duration | `10m` |

### Embeddings

| Variable | Description | Default |
| --- | --- | --- |
| `EMBED_BASE_URL` | Ollama base URL | `http://localhost:11434` |
| `EMBED_MODEL` | Embedding model name | `mxbai-embed-large` |

### Redis (conversational memory)

| Variable | Description | Default |
| --- | --- | --- |
| `REDIS_HOST` | Redis host | `localhost` |
| `REDIS_PORT` | Redis port | `6379` |
| `REDIS_DB` | Redis database index | `0` |

### File uploads

| Variable | Description | Default |
| --- | --- | --- |
| `UPLOAD_MAX_BYTES` | Max upload size in bytes | `10485760` (10 MB) |
| `UPLOAD_ALLOWED_EXTENSIONS` | Comma-separated allowed extensions | `pdf,docx,txt,md,csv,xlsx` |
| `ATTACHMENT_STORE_FILE` | On-disk attachment store path | _(default location)_ |
| `ATTACHMENT_MAX_FILES_PER_SESSION` | Files kept per session | `5` |
| `ATTACHMENT_MAX_CHARS` | Max characters stored per file | `60000` |
| `ATTACHMENT_TOP_K` | Most relevant chunks fed to the LLM | `4` |
| `ATTACHMENT_MIN_SCORE` | Minimum cosine similarity for relevance | `0.35` |
| `ATTACHMENT_CHUNK_SIZE` | Chunk size for embedding | `900` |
| `ATTACHMENT_CHUNK_OVERLAP` | Chunk overlap | `80` |

### API / CORS

| Variable | Description | Default |
| --- | --- | --- |
| `CORS_ALLOW_ORIGINS` | Comma-separated allowed origins | `*` |
| `ENABLE_DEBUG_ENDPOINTS` | Enable debug/introspection routes | `false` |

## API reference

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/` | Serves the chat web UI |
| `GET` | `/health` | Health check |
| `GET` | `/users` | Lists staff users with role and allowed communities (login picker) |
| `POST` | `/ask` | Ask a question |
| `POST` | `/upload` | Upload a document to the current chat session |
| `GET` | `/upload` | List active attachments for a session |
| `DELETE` | `/upload/{file_id}` | Remove a single uploaded file |
| `GET` | `/history/{session_id}` | Fetch a session's chat history |
| `DELETE` | `/history/{session_id}` | Clear a session's chat history |

Every endpoint takes a `community_id` and confirms the caller is allowed to see that
community before doing anything.

### Example: `POST /ask`

```json
{
  "query": "Who slept the longest?",
  "session_id": "demo-session",
  "community_id": 3,
  "user_id": 12
}
```

`user_id` is optional. When supplied, the request is rejected unless that user is mapped to
the given `community_id`.

## Testing

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests
```

Most tests run without live services. Real answer quality is best checked against a running
setup, since it depends on the live database, LLM, and search index.

## Security model

- **Read-only SQL.** Generated queries are validated and reject mutating or destructive
  operations (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, etc.) before execution.
- **Community authorization.** Every request is gated against the caller's mapped
  communities; a caller cannot read or mutate another community's data by passing an
  unauthorized `community_id`.
- **Roster grounding.** Answers that name residents are checked against the real roster.
- **Prompt-injection defense.** Input and output guardrails screen for unsafe content and
  injection attempts from users and retrieved documents.
- **No internal leakage.** Generated SQL, internal prompts, stack traces, and secrets are
  never returned to users; technical details are logged for developers only.
