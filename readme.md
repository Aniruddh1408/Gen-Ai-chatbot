# KuboCare GenAI Assistant

KuboCare GenAI Assistant is a FastAPI chatbot backend for community-scoped resident health analytics and IoT support documentation.

The project uses a hybrid retrieval design:

- Structured resident and metric questions are answered from PostgreSQL using deterministic SQL retrieval.
- Device telemetry questions are answered from the `device_status` table.
- Documentation and troubleshooting questions are answered through RAG over the local documentation set.
- Follow-up questions use session memory so prompts like `what is her BP?` can resolve to the correct resident.

## Current Flow

```text
POST /ask
  -> community_id validation
  -> community-scoped session memory
  -> query rewrite for follow-ups
  -> input guardrail
  -> intent router
      -> SQL retriever for residents, health_reports, activity_metrics, sleep_analytics, device_status
      -> RAG retriever for docs/manuals/privacy/escalation/troubleshooting
      -> chat response for greetings/basic chat
  -> output guardrail
  -> save turn in memory
  -> response with trace_id, latency, community_id, community_name
```

## Why Community ID Matters

The chatbot is meant to run inside an existing dashboard where the user is already logged into one community. The user should not need to type the community name.

The dashboard must send the logged-in community ID to `/ask`:

```json
{
  "query": "Who needs more care?",
  "session_id": "caretaker-123",
  "community_id": 3
}
```

The backend then automatically filters resident data to that community. A caretaker from community 3 cannot retrieve residents from community 1 or 2 through normal resident queries.

## Main Capabilities

Resident data:

- List residents in the current community
- Count residents
- Fetch resident details by ID or name
- Retrieve age, flat/room, medical history, and prescribed medication

Health metrics:

- Blood pressure readings and rankings
- Sugar/glucose levels and rankings
- Step counts and rankings
- Sleep duration and sleep score rankings
- Average BP, sugar, steps, sleep duration, and sleep score

Care prioritization:

- `Who needs more care?`
- `Give only one resident who requires more care.`
- `Who is most healthy?`
- `Who is not healthy?`

The care answer is a data-prioritization heuristic using age, BP, sugar, sleep, steps, and medical history. It is not a medical diagnosis.

Device status:

- List devices
- Show a specific board status such as `DEV4`
- Weakest/strongest signal
- Lowest/highest uptime
- Highest CPU usage
- Average device uptime/signal/CPU

RAG documentation:

- Error code explanations
- Device troubleshooting
- Privacy and security policy
- Clinical and technical escalation guidance

## Tech Stack

| Area | Technology |
| --- | --- |
| API | FastAPI |
| Database | PostgreSQL |
| Vector search | pgvector |
| LLM client | OpenAI-compatible vLLM endpoint through LangChain `ChatOpenAI` |
| Embeddings | Ollama embeddings API |
| Memory | Redis with in-memory fallback |
| Routing | Deterministic rules plus LangChain classifier fallback |
| Frontend | Static HTML served by FastAPI |

LangChain is used for LLM client calls, prompt templates, and lightweight routing support.

## Project Structure

```text
app/
  agents/
    guardrails.py       Input/output safety rules
    memory.py           Redis-backed chat history and follow-up rewriting
    router.py           Intent routing to SQL, RAG, or chat
  api/
    main.py             FastAPI app and endpoints
  core/
    config.py           Environment configuration
    db.py               PostgreSQL connection pool
    logger.py           JSON logging
  frontend/
    index.html          Local demo UI
  llm/
    client.py           vLLM/OpenAI-compatible LLM client
  retrievers/
    sql_retriever.py    Deterministic SQL/data retrieval
    vector_retriever.py RAG retrieval over docs
  schema/
    schema.py           Table schema used by SQL planning

data/
  rag_db.sql            Database schema and seed data
  docs/                 RAG documentation markdown files

scripts/
  embed_docs.py         Loads docs into pgvector-backed document tables
```

## Environment Variables

Create a `.env` file in the project root.

```env
DB_NAME=your_database
DB_USER=your_user
DB_PASS=your_password
DB_HOST=localhost
DB_PORT=5432

LLM_BASE_URL=http://your-vllm-host:8001/v1
LLM_API_KEY=dummy
LLM_MODEL=Qwen/Qwen2.5-7B-Instruct-AWQ
LLM_TEMPERATURE=0
LLM_TIMEOUT_SECONDS=0

EMBED_BASE_URL=http://localhost:11434
EMBED_MODEL=mxbai-embed-large

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

DB_POOL_MIN=1
DB_POOL_MAX=10
```

Notes:

- `community_id` is required for `/ask`.
- Redis is recommended for real sessions. If Redis is unavailable, the app falls back to in-memory history for local testing.
- The RAG retriever can answer known local documentation sections even if embeddings are unavailable, but full vector search requires Ollama embeddings and pgvector documents.

## Setup

1. Create and activate a virtual environment:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Create the PostgreSQL database and load the schema/data:

```powershell
psql -U <db_user> -d <db_name> -f data\rag_db.sql
```

4. Load documentation embeddings after the DB is ready:

```powershell
.\venv\Scripts\python.exe scripts\embed_docs.py
```

5. Run the API:

```powershell
uvicorn app.api.main:app --reload --port 8001
```

If Windows blocks port `8001` with `WinError 10013`, use another port:

```powershell
uvicorn app.api.main:app --reload --port 8010
```

Open the local UI:

```text
http://127.0.0.1:8001/
```

## API Usage

Health check:

```http
GET /health
```

Ask endpoint:

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

Example response:

```json
{
  "query": "Who slept the longest?",
  "answer": "Leela Varma has the highest sleep duration: 430 minutes.",
  "community_id": 3,
  "community_name": "Lotus Wellness Home",
  "trace_id": "...",
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

## Quick Manual Checks

Run these after the server starts.

```powershell
$body = @{
  query = "List all residents."
  session_id = "manual-check"
  community_id = 3
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8001/ask" -Method Post -ContentType "application/json" -Body $body
```

Useful retrieval checks:

```text
Which community am I viewing?
List all residents.
Give me the details of resident with id 11.
What is Devendra Patil blood pressure?
What is the average BP?
Show step count of all residents.
Who slept the longest?
Give only one resident who requires more care.
Who is most healthy?
Show status of DEV4.
Which device has weakest signal?
What does error E-404 mean?
What is the privacy and security policy?
```

## Verification Commands

Syntax check:

```powershell
.\venv\Scripts\python.exe -c "import ast, pathlib; files=list(pathlib.Path('app').rglob('*.py'))+list(pathlib.Path('scripts').rglob('*.py')); [ast.parse(f.read_text(), filename=str(f)) for f in files]; print(f'syntax ok: {len(files)} files')"
```

Dependency check:

```powershell
.\venv\Scripts\python.exe -m pip check
```

There is currently no committed pytest test suite. Retrieval should be verified through the live `/ask` flow because it depends on the active PostgreSQL data, Redis/session state, and configured RAG/LLM services.

## Deployment Notes

Before deployment:

- Use production `.env` values. Do not hardcode DB passwords or API keys.
- Ensure PostgreSQL is reachable and `data/rag_db.sql` has been applied.
- Ensure pgvector is installed if full vector search is required.
- Run `scripts/embed_docs.py` whenever documentation markdown files change.
- Ensure the dashboard sends the correct `community_id` with every `/ask` call.
- Run with a production ASGI server setup, for example Uvicorn behind Nginx or a managed load balancer.
- Restrict CORS origins for production. The current code allows all origins for local/demo use.
- Review logging and PHI/PII handling before exposing real resident data.

## Current Design Choice

This project intentionally uses deterministic SQL retrieval for structured data instead of relying only on an LLM to generate SQL. That is safer for resident data because community isolation and metric logic are enforced in backend code.

RAG is used for unstructured documents and policies. It should not be used as the source of truth for resident health metrics.
