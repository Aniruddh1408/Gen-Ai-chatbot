"""
LLM Client — LangChain + Ollama integration.
Provides a shared ChatOllama instance and a backward‑compatible ask_llm() helper.
"""
import datetime
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from app.core.config import OLLAMA_BASE_URL, LLM_MODEL, LLM_TEMPERATURE


# ----------------------------
# Shared LLM instance
# ----------------------------
llm = ChatOllama(
    model=LLM_MODEL,
    base_url=OLLAMA_BASE_URL,
    temperature=LLM_TEMPERATURE,
)


def get_system_prompt():
    """Default SQL planner system prompt with live date injection."""
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")
    yesterday_date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    return f"""
You are a strict SQL planner for an IoT analytics system.
CURRENT DATE AND TIME: {current_time}
TODAY'S DATE: {current_date}

Rules:
1. Use ONLY available columns from the schema.
2. ONLY set "aggregation" if the user explicitly asks for avg, sum, count, max, min. If they don't, leave it completely empty ("").
3. ONLY use "group_by" if the user explicitly asks to group, break down, or split by a column. Otherwise, "".
4. Return an appropriate integer for "limit", default is 100.
5. For times and dates, always use precise ISO 8601 timestamps (e.g., '{current_date} 00:00:00') based on the CURRENT DATE AND TIME. Do not use words like 'yesterday'. Calculate the math yourself into an exact timestamp filter.
6. Return ONLY valid JSON. No explanation.

Schema:
device_status(
    board_id TEXT,
    location TEXT,
    signal FLOAT,
    uptime FLOAT,
    cpu FLOAT,
    time TIMESTAMP
)

Example 1:
User: What is the average signal by location for dev1 yesterday?
Output:
{{
  "table": "device_status",
  "aggregation": "avg",
  "column": "signal",
  "group_by": "location",
  "limit": 100,
  "filters": [
    {{"column": "board_id", "operator": "=", "value": "dev1"}},
    {{"column": "time", "operator": ">=", "value": "{yesterday_date} 00:00:00"}},
    {{"column": "time", "operator": "<", "value": "{current_date} 00:00:00"}}
  ]
}}

Example 2:
User: What is the signal for board dev2 and location room2?
Output:
{{
  "table": "device_status",
  "aggregation": "",
  "column": "signal",
  "group_by": "",
  "limit": 100,
  "filters": [
    {{"column": "board_id", "operator": "=", "value": "dev2"}},
    {{"column": "location", "operator": "=", "value": "room2"}}
  ]
}}
"""


def ask_llm(query: str, system_prompt: str = None) -> str:
    """
    Backward-compatible wrapper.
    Accepts an optional system_prompt override; otherwise uses the default SQL planner prompt.
    """
    sys_prompt = system_prompt if system_prompt else get_system_prompt()

    messages = [
        SystemMessage(content=sys_prompt),
        HumanMessage(content=query),
    ]

    response = llm.invoke(messages)
    return response.content