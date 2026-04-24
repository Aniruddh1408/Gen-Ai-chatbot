"""
LLM client for a vLLM OpenAI-compatible server.
"""
import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_SECONDS,
)
from app.schema.schema import SCHEMA, schema_to_text

# Shared LLM instance for lightweight calls such as intent classification.
llm = ChatOpenAI(
    model=LLM_MODEL,
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
    temperature=LLM_TEMPERATURE,
    max_tokens=256,
    timeout=LLM_TIMEOUT_SECONDS,
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
RULE: For "highest", "most", "best", "top", use ORDER_DIRECTION: "DESC" with LIMIT 1.
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
    """Call vLLM directly for SQL planning."""
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
    """Call the vLLM OpenAI-compatible chat API and return assistant content."""
    invoke_kwargs = {
        "temperature": LLM_TEMPERATURE if temperature is None else temperature,
        "max_tokens": num_predict,
    }
    if response_format == "json":
        invoke_kwargs["response_format"] = {"type": "json_object"}

    temp_llm = llm.bind(**invoke_kwargs)
    response = temp_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    return response.content.strip() if isinstance(response.content, str) else str(response.content).strip()


def ask_llm(query: str, system_prompt: str = None) -> str:
    sys_prompt = system_prompt if system_prompt else get_system_prompt()
    return ask_with_messages(sys_prompt, query)
