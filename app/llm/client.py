"""
LLM Client — LangChain + Ollama integration.
"""
import datetime
import requests
from langchain_ollama import ChatOllama
from app.core.config import OLLAMA_BASE_URL, LLM_MODEL, LLM_TEMPERATURE
from app.schema.schema import SCHEMA, schema_to_text

# Shared LLM instance
llm = ChatOllama(
    model=LLM_MODEL,
    base_url=OLLAMA_BASE_URL,
    temperature=LLM_TEMPERATURE,
    num_predict=256,   # Limit generation length to save CPU/Heat
    num_ctx=2048,      # Smaller context window for faster processing
)

def get_system_prompt():
    """Default SQL planner system prompt with live date injection."""
    now = datetime.datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    schema_text = schema_to_text(SCHEMA)

    return f"""
You are an expert SQL Planner for a healthcare and IoT system.
Your mission is to convert the User Query into a valid JSON SQL Plan.

TODAY IS: {current_date}

SCHEMA:
{schema_text}

JSON FORMAT RULES:
1. table: Must be one of the schema tables.
2. column: ALWAYS select "residents.name" along with the metric you need (e.g., "residents.name, steps_count"). Never use "*". 
3. filters: List of column, operator, value. NEVER create time or date filters (assume all DB data is recent).
4. order_by: Column name if user asks for highest, lowest, best, worst.

EXAMPLE 1 (Chart or Analytics):
Query: Make a chart of the sleep quality scores.
Result:
{{
  "table": "sleep_analytics",
  "column": "residents.name, sleep_quality_score",
  "limit": 10,
  "filters": []
}}

EXAMPLE 2 (Analytic):
Query: Who has the lowest sleep quality score?
Result:
{{
  "table": "sleep_analytics",
  "column": "residents.name, sleep_quality_score",
  "order_by": "sleep_quality_score",
  "order_direction": "ASC",
  "limit": 1,
  "filters": []
}}

RULE: For "lowest", "fewest", "least", "less", use ORDER_DIRECTION: "ASC" with LIMIT 1.
RULE: For "highest", "most", "best", use ORDER_DIRECTION: "DESC" with LIMIT 1.
"""

def get_sql_planner_prompt() -> str:
    """Short, strict planner prompt optimized for smaller local models."""
    schema_text = schema_to_text(SCHEMA)

    return """
Return exactly one JSON object.
Do not use markdown.
Do not explain anything.
Do not return empty output.

Allowed tables:
- residents
- health_reports
- activity_metrics
- sleep_analytics
- device_status

Relationships:
- residents.id = health_reports.resident_id
- residents.id = activity_metrics.resident_id
- residents.id = sleep_analytics.resident_id

Rules:
- For resident metric queries, include residents.name in column.
- Never use '*'.
- filters must be a list of objects like {"column":"residents.name","operator":"=","value":"Ravi Kumar"}.
- If user asks for lowest/least/fewest, use order_direction ASC and limit 1.
- If user asks for highest/most/best, use order_direction DESC and limit 1.
- If no filters are needed, return "filters": [].

Valid JSON shape:
{
  "table": "sleep_analytics",
  "column": "residents.name, sleep_quality_score",
  "filters": [],
  "order_by": "sleep_quality_score",
  "order_direction": "ASC",
  "limit": 1
}

Schema:
""" + schema_text

def ask_sql_planner(query: str) -> str:
    """Call Ollama directly for SQL planning to avoid empty ChatOllama planner responses."""
    return ask_with_messages(
        get_sql_planner_prompt(),
        query,
        response_format="json",
        num_predict=120,
        temperature=0.0,
    )

def ask_with_messages(
    system_prompt: str,
    user_prompt: str,
    response_format: str | None = None,
    num_predict: int = 160,
    temperature: float | None = None,
) -> str:
    """Call Ollama chat API directly and return assistant content."""
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "think": False,
        "options": {
            "num_predict": num_predict,
            "temperature": LLM_TEMPERATURE if temperature is None else temperature,
        },
        "stream": False,
    }
    if response_format:
        payload["format"] = response_format

    response = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=180)
    response.raise_for_status()
    data = response.json()
    return data.get("message", {}).get("content", "").strip()

def ask_llm(query: str, system_prompt: str = None) -> str:
    sys_prompt = system_prompt if system_prompt else get_system_prompt()
    return ask_with_messages(sys_prompt, query)
