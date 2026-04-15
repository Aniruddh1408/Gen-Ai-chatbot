"""
LLM Client — LangChain + Ollama integration.
"""
import datetime
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
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
    current_time = now.strftime("%Y-%m-%d %H:%M:%S")
    current_date = now.strftime("%Y-%m-%d")
    yesterday_date = (now - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    three_days_ago = (now - datetime.timedelta(days=3)).strftime("%Y-%m-%d")
    
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

def ask_llm(query: str, system_prompt: str = None) -> str:
    sys_prompt = system_prompt if system_prompt else get_system_prompt()
    messages = [SystemMessage(content=sys_prompt), HumanMessage(content=query)]
    response = llm.invoke(messages)
    return response.content