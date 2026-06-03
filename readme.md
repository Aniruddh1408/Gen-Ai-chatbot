# KuboCare GenAI Assistant

The question-answering backend behind a senior-living care dashboard. A caregiver
asks something in plain English — "How did this person last night?", "Who needs the
most attention/care today?", "How do I recalibrate the sensor?" — and the service works
out where the answer should come from, fetches it safely, and replies in a precise,
grounded sentence.

It doesn't just hand everything to one AI model. Instead it picks the right source
for each question:

- **Data questions** (residents, sleep, vitals, activity, wellness, falls) are
  answered from the database with safe, read-only queries.
- **How-to and policy questions** are answered from the written care and device
  guides.
- **Small talk** is answered directly, without touching any data.
- **Uploaded files** — a user can attach a document and ask about it; the file
  stays private to that one chat.

A key design choice: the assistant would rather say "I don't have that" than make
something up.

## What it can and can't tell you

The sensors are radar-based, so the assistant can talk about heart rate,
respiration, sleep, activity, wellness scores, and falls — plus resident profiles
(age, room, medical history) and a "who needs care first" triage hint for staff.

It does **not** track blood pressure, blood sugar, weight, or medications. Ask for
those and it says so plainly instead of inventing a number.

## How it works

Every question runs through a fixed pipeline: check who's asking and load recent
chat context, screen the input for anything unsafe, answer from attached files if
there are any, otherwise route to the database or the documents, clean the reply,
and remember the turn for follow-ups like "what about her heart rate?".

Two things keep it trustworthy: each answer is locked to the community (and role)
the caller is allowed to see, and any answer that names a resident is checked
against the real roster before it goes out — so it can't leak or confuse people
across communities.

The dashboard owns login and identity; it sends the community and user with each
request, and this service re-checks that before reading anything.

## Project structure

```text
app/
  agents/      input/output guardrails, chat memory, routing,
               answer grounding, and the uploaded-file store
  api/         the web server and its endpoints
  core/        config, database access, logging, community/role rules
  graph/       the step-by-step request pipeline
  ingest/      pulling text out of uploaded files
  llm/         the AI model client
  retrievers/  the data ("text-to-SQL") and document search paths
  schema/      the map of what data exists
data/docs/     the care and device guides the assistant reads
scripts/       loads the guides so they can be searched
tests/         automated tests
```

## Running it locally

1. Create a virtual environment and install dependencies:

   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Copy your settings into a `.env` file (database, AI model, embedding, and Redis
   connection details). Keep real credentials out of source control.

3. Load the guides and start the server:

   ```powershell
   .\venv\Scripts\python.exe scripts\embed_docs.py
   uvicorn app.api.main:app --reload --port 8001
   ```

4. Open `http://127.0.0.1:8001/`.

## Asking a question

The main endpoint is `POST /ask`:

```json
{
  "query": "Who slept the longest?",
  "session_id": "demo-session",
  "community_id": 3
}
```

There are also endpoints to upload and remove files, fetch or clear a chat's
history, and a health check. Every one of them confirms the caller is allowed to
see that community before doing anything.

## Tests

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests
```

Most tests run without live services. Real answer quality is best checked against a
running setup, since it depends on the live database, AI model, and search index.
