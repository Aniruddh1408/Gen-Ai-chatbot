# KuboCare GenAI Assistant

KuboCare GenAI Assistant is a FastAPI backend for a care-community dashboard. It answers questions about residents, health metrics, IoT device status, and internal documentation.

The project is designed as a hybrid retrieval system:

- SQL retrieval answers structured database questions.
- RAG retrieval answers documentation, policy, troubleshooting, and procedure questions.
- LangGraph controls the full chat flow.
- Redis stores short session memory so follow-up questions can stay on topic.
- Community isolation keeps resident queries scoped to the selected community.

This backend assumes login, dashboard authorization, and user identity are handled by the parent application. The dashboard must pass the trusted `community_id` to this service with every request.

## What The Assistant Can Answer

Resident profile questions:

- List residents in the current community.
- Count residents.
- Get a resident by name or ID.
- Show age, room/flat, medical history, or prescribed intake.

Health metric questions:

- Blood pressure, sugar/glucose, steps, sleep duration, and sleep quality score.
- Highest, lowest, average, and threshold-based metric questions.
- Named resident metric questions like `What is Ravi Kumar's BP?`.
- Community-level questions like `Who slept the longest?`.

Care prioritization questions:

- `Who needs more care?`
- `Who is most healthy?`
- `Who is not healthy?`
- `Give only one resident who requires more care.`

The care-priority answer is a deterministic scoring heuristic over recorded age, BP, sugar, sleep, steps, and medical history. It is not a diagnosis.

Device and IoT questions:

- Device board status.
- Signal, uptime, CPU, and device rankings.
- Specific board queries such as `Show status of DEV4.`

Documentation questions:

- Device troubleshooting.
- Error codes.
- Moisture sensor recalibration.
- Privacy and escalation policies.
- Clinical review workflows.
- Manual entry versus device reading.
- Data quality, stale readings, duplicates, and traceability.

Follow-up and formatting questions:

- `What is her BP?`
- `What about sugar?`
- `Tell it in points.`
- `Explain in simple terms.`
- `Elaborate.`
- Multiple questions in one prompt, up to four sub-questions.

## Request Flow

The main endpoint is `POST /ask`. The LangGraph flow is defined in `app/graph/workflow.py`.

```text
POST /ask
  -> load_context
       validate community_id
       load community-scoped memory
  -> current_community
       answer "which community am I viewing?" directly
  -> transform_previous_answer
       rewrite previous answer into points/simple/short form
       or expand "elaborate" against the previous real topic
  -> rewrite
       resolve follow-up references using memory
  -> split_questions
       split multi-question prompts into sub-queries
  -> guardrail
       block prompt injection and out-of-domain questions
  -> route
       SQL, RAG, or CHAT
  -> output_guardrail
       remove obvious prompt/backend leaks
  -> save_memory
       save successful turns under community-scoped session key
  -> finalize
       attach trace_id, latency, community_id, and community_name
```

Conditional edges are used where the graph may skip later work. For example, an invalid `community_id` goes straight to `finalize`, and a simple formatting follow-up can skip retrieval.

## Retrieval Design

### SQL Retrieval

SQL retrieval lives in `app/retrievers/sql_retriever.py`.

It is used for database-backed facts:

- residents
- health reports
- activity metrics
- sleep analytics
- device status

Most common resident, metric, ranking, threshold, and device queries are handled with deterministic plans. The LLM planner is only a fallback for supported SQL-style questions that do not match a deterministic path.

Community filtering is enforced in backend SQL construction. The user query is not trusted to choose the community.

### RAG Retrieval

RAG retrieval lives in `app/retrievers/vector_retriever.py`.

It is used for unstructured docs:

- manuals
- troubleshooting
- policies
- escalation guidance
- clinical workflow notes
- data quality guidance

The retriever first checks known local documentation sections for exact operational topics. If no local section matches, it embeds the query, searches the `documents` table with pgvector, applies a distance threshold, and then asks the LLM to answer only from retrieved context.

### Intent Routing

Routing lives in `app/agents/router.py`.

The router chooses:

- `SQL` for residents, metrics, rankings, device telemetry, and care-priority questions.
- `RAG` for documentation, policy, troubleshooting, and general concept explanations.
- `CHAT` for greetings, acknowledgements, and light conversational replies.

The router uses deterministic keyword and regex rules first, then falls back to a lightweight LLM classifier.

## Community Isolation

Community isolation is important because the same backend can serve multiple care communities.

The dashboard sends:

```json
{
  "query": "List all residents.",
  "session_id": "dashboard-session-id",
  "community_id": 3
}
```

The backend then:

- validates the `community_id` in `app/core/community.py`
- creates a memory key like `community:3:session:dashboard-session-id`
- applies `residents.community_id = %s` to resident-scoped SQL queries
- returns the selected `community_id` and `community_name` in the response

Do not let users choose community access by typing a community name in chat. The `community_id` should come from the already-authorized dashboard context.

To add a new community in the current local setup:

1. Add it to the `communities` table in the database.
2. Add the same ID and display name to `LOCAL_DEMO_COMMUNITIES` in `app/core/community.py`.
3. Make sure the parent dashboard sends that ID to `/ask`.
4. Add or import residents and metric rows using that same `community_id`.

In a production dashboard, replace the local in-code community map with the dashboard or database source of truth.

## Project Structure

```text
app/
  agents/
    guardrails.py          Input and output guardrails
    memory.py              Redis-backed chat memory and follow-up rewriting
    router.py              Intent routing to SQL, RAG, or chat
  api/
    main.py                FastAPI app and API endpoints
  core/
    community.py           Community ID validation and memory isolation
    config.py              Environment variables
    db.py                  PostgreSQL connection pool
    logger.py              JSON logging
  frontend/
    index.html             Local demo UI served by FastAPI
  graph/
    state.py               LangGraph state shape
    workflow.py            LangGraph nodes and edges
  llm/
    client.py              OpenAI-compatible LLM client
  retrievers/
    sql_retriever.py       Deterministic SQL/data retrieval
    vector_retriever.py    Documentation RAG retrieval
  schema/
    schema.py              Table schema text used by the SQL planner

data/
  rag_db.sql               PostgreSQL schema and local seed data
  docs/                    Markdown documentation used by RAG

scripts/
  embed_docs.py            Ingests docs into pgvector-backed document tables

tests/
  test_document_chunking.py
  test_graph_conditional_edges.py
  test_health_document_retrieval.py
  test_resident_superlatives.py
  test_vector_section_formatting.py
```

## Tech Stack

| Area | Technology |
| --- | --- |
| API | FastAPI |
| Workflow | LangGraph |
| LLM calls | LangChain `ChatOpenAI` against an OpenAI-compatible endpoint |
| Database | PostgreSQL |
| Vector search | pgvector |
| Embeddings | Ollama-compatible embeddings API |
| Memory | Redis with in-memory fallback |
| Tests | Python `unittest` |
| Demo UI | Static HTML served by FastAPI |

## Environment Setup

Create a `.env` file in the project root. Use your own values. Do not commit real credentials.

```env
DB_NAME=your_database_name
DB_USER=your_database_user
DB_PASS=your_database_password
DB_HOST=localhost
DB_PORT=5432

LLM_BASE_URL=http://your-llm-host:your-port/v1
LLM_API_KEY=your_llm_api_key_or_local_placeholder
LLM_MODEL=your_model_name
LLM_TEMPERATURE=0
LLM_TIMEOUT_SECONDS=0

EMBED_BASE_URL=http://localhost:11434
EMBED_MODEL=mxbai-embed-large
EMBED_DIM=1024

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

DB_POOL_MIN=1
DB_POOL_MAX=10

DOC_CHUNKING_MODE=hybrid
DOC_CHUNK_SIZE=900
DOC_CHUNK_OVERLAP=80
```

Notes:

- `LLM_BASE_URL` must point to an OpenAI-compatible chat-completions server.
- `LLM_API_KEY` may be a real key or a local placeholder depending on your LLM server.
- `EMBED_DIM` must match the embedding model and the `documents.embedding VECTOR(...)` dimension.
- Redis is recommended for real sessions. If Redis is unavailable, the app uses an in-memory fallback for local testing.

## Local Setup

1. Create and activate a virtual environment:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Create the PostgreSQL database and load schema plus seed data:

```powershell
psql -U <db_user> -d <db_name> -f data\rag_db.sql
```

4. Make sure the embedding service is running and has the configured embedding model available.

5. Ingest documentation into pgvector:

```powershell
.\venv\Scripts\python.exe scripts\embed_docs.py
```

6. Run the API:

```powershell
uvicorn app.api.main:app --reload --port 8001
```

7. Open the local demo UI:

```text
http://127.0.0.1:8001/
```

If port `8001` is already used or blocked, run the API on another local port:

```powershell
uvicorn app.api.main:app --reload --port 8010
```

## API Usage

Health check:

```http
GET /health
```

Ask:

```http
POST /ask
Content-Type: application/json
```

Request:

```json
{
  "query": "Who slept the longest?",
  "session_id": "demo-session",
  "community_id": 3
}
```

Response shape:

```json
{
  "query": "Who slept the longest?",
  "answer": "Resident name and metric answer here.",
  "community_id": 3,
  "community_name": "Community display name",
  "trace_id": "request-trace-id",
  "latency_ms": 12.3
}
```

History:

```http
GET /history/{session_id}?community_id=3
DELETE /history/{session_id}?community_id=3
```

Guardrail debug:

```http
GET /debug/guardrail?query=Who%20needs%20more%20care
```

## Documentation Ingestion

Documentation files live in `data/docs/`.

Supported file types:

- `.md`
- `.txt`

Default chunking mode is `hybrid`.

Hybrid chunking means:

1. Markdown headings are used to keep sections together.
2. Oversized sections are split with LangChain's recursive character splitter.
3. Section metadata is stored with each chunk.

This usually improves retrieval accuracy because a heading and its section content stay together.

Useful ingestion commands:

```powershell
.\venv\Scripts\python.exe scripts\embed_docs.py --dry-run
```

```powershell
.\venv\Scripts\python.exe scripts\embed_docs.py
```

```powershell
.\venv\Scripts\python.exe scripts\embed_docs.py --rebuild
```

```powershell
.\venv\Scripts\python.exe scripts\embed_docs.py --chunking-mode recursive
```

The ingestion script is incremental:

- unchanged chunks are skipped
- new chunks are inserted
- removed or changed chunks are marked inactive
- `chunk_hash` prevents duplicate active chunks for the same content and model

When adding new docs:

1. Add the file under `data/docs/`.
2. Use clear Markdown headings.
3. Keep each section focused on one topic.
4. Run `--dry-run` to inspect chunk counts.
5. Run the normal ingest command.
6. Run retrieval tests and a few manual `/ask` checks.

## Guardrails

Input guardrails are in `app/agents/guardrails.py`.

They block:

- common prompt injection attempts
- out-of-domain questions
- empty queries

They allow:

- resident and clinical analytics questions
- IoT and hardware questions
- documentation questions
- greetings and simple acknowledgements
- newly added doc topics when vector relevance is strong enough

Output guardrails remove obvious backend or prompt leakage before the response is returned.

Guardrails are deterministic by design. This makes behavior easier to test and safer than relying only on an LLM.

## Memory And Follow-Ups

Memory is implemented in `app/agents/memory.py`.

The memory key includes the community ID:

```text
community:{community_id}:session:{session_id}
```

This prevents a session in one community from reusing another community's chat context.

The system keeps a short history window to keep context focused. Follow-up logic handles:

- single-resident follow-ups
- resident collection follow-ups
- metric follow-ups
- short continuations like `elaborate`
- answer transformations like `tell it in points`

Formatting-only follow-ups do not add new facts. They rewrite the previous answer or re-query the previous real topic depending on the request.

## Manual Checks

After starting the API, try these from the UI or with `/ask`:

```text
Which community am I viewing?
List all residents.
Give me the details of resident with id 11.
What is the age of Devendra Patil?
What is Devendra Patil's blood pressure?
What is the average BP?
Show step count of all residents.
Who slept the longest?
Who has the lowest sleep quality score?
What is sleep quality score?
Give only one resident who requires more care.
Who is most healthy?
Show status of DEV4.
Which device has weakest signal?
What does error E-404 mean?
How do I recalibrate the moisture sensor?
What is the privacy and security policy?
What is the difference between manual entry and device reading?
Tell it in points.
Elaborate.
```

Example PowerShell request:

```powershell
$body = @{
  query = "List all residents."
  session_id = "manual-check"
  community_id = 3
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8001/ask" `
  -Method Post `
  -ContentType "application/json" `
  -Body $body
```

## Tests

Run all tests:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests
```

Run focused tests:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_graph_conditional_edges
.\venv\Scripts\python.exe -m unittest tests.test_document_chunking
.\venv\Scripts\python.exe -m unittest tests.test_health_document_retrieval
.\venv\Scripts\python.exe -m unittest tests.test_vector_section_formatting
.\venv\Scripts\python.exe -m unittest tests.test_resident_superlatives
```

Syntax check:

```powershell
.\venv\Scripts\python.exe -c "import ast, pathlib; files=list(pathlib.Path('app').rglob('*.py'))+list(pathlib.Path('scripts').rglob('*.py')); [ast.parse(f.read_text(), filename=str(f)) for f in files]; print(f'syntax ok: {len(files)} files')"
```

Dependency check:

```powershell
.\venv\Scripts\python.exe -m pip check
```

The unit tests use stubs where possible. Full retrieval quality should also be checked through the live `/ask` flow because it depends on the active database, embeddings, Redis state, and LLM service.

## Production Notes

Before deploying:

- Keep real credentials only in environment variables or a secrets manager.
- Do not hardcode private service URLs, API keys, database passwords, or tokens.
- Make the parent dashboard pass the authorized `community_id`; do not trust a user-written community name.
- Replace the local demo community map with the production community source of truth.
- Restrict CORS origins in `app/api/main.py`.
- Use Redis or another persistent session store for multi-worker deployments.
- Make sure PostgreSQL, pgvector, Redis, the LLM service, and the embedding service are reachable from the runtime environment.
- Run `scripts/embed_docs.py` whenever docs change.
- Keep `DOC_CHUNKING_MODE=hybrid` unless retrieval tests show a clear reason to roll back.
- Review logs for PHI/PII exposure before using real resident data.
- Add request rate limiting, observability, and health checks in the deployment layer.
- Run the unit tests and live retrieval checks before each release.

## Design Principle

The system intentionally does not use one generic LLM call for everything.

Structured resident and metric answers come from SQL because the backend can enforce community scope, query shape, and deterministic behavior. Documentation answers come from RAG because policies and procedures are unstructured text. LangGraph connects these paths and gives the system clear places to validate, route, transform, save memory, and stop early when needed.
