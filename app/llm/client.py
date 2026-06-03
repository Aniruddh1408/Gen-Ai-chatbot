# ===========================================================================
# This file is the phone line to the AI language model. It sends prompts to the
# model server and returns the model's reply, with shared settings for timeouts
# and temperature. Other parts of the app call through here instead of talking
# to the model directly.
# ===========================================================================
"""
LLM client for a vLLM OpenAI-compatible server.
"""
import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_DATA_TEMPERATURE,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
)
from app.schema.kubocare_schema import SCHEMA, schema_to_text

# Shared LLM instance for lightweight calls such as intent classification.
llm = ChatOpenAI(
    model=LLM_MODEL,
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY,
    temperature=LLM_DATA_TEMPERATURE,
    max_tokens=256,
    timeout=LLM_TIMEOUT_SECONDS,
)


# Tables the deterministic SQL builder (build_sql) knows how to community-scope.
# The LLM planner is restricted to these so a generated plan can never run
# unscoped (build_sql now fails closed on any other table). resident_profile is
# the canonical residents table; the other three carry a resident_id FK that
# build_sql auto-joins into the room→community chain.
_PLANNER_SCOPABLE_TABLES = (
    "resident_profile", "activity_log", "insights", "notifications",
)


def get_system_prompt():
    """Default SQL planner system prompt with live date injection."""
    now = datetime.datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    return _planner_prompt(current_date=current_date)


def get_sql_planner_prompt() -> str:
    """Short, strict planner prompt optimized for smaller local models."""
    return _planner_prompt()


def _planner_prompt(current_date: str | None = None) -> str:
    """Strict JSON SQL planner prompt, grounded in the *current* schema.

    Restricts the planner to tables build_sql can community-scope and forbids
    inventing tables/columns. Anything outside this allowlist is rejected by the
    safety validator, so the prompt keeps the model inside the safe set.
    """
    schema_text = schema_to_text(SCHEMA, only=_PLANNER_SCOPABLE_TABLES)
    date_line = f"TODAY IS: {current_date}\n\n" if current_date else ""
    allowed = "\n".join(f"- {t}" for t in _PLANNER_SCOPABLE_TABLES)

    return f"""You convert a user request into exactly one JSON SQL plan.
{date_line}Return exactly one JSON object. No markdown, no prose, no explanation.

You may ONLY use these tables:
{allowed}

Strict rules:
1. "table" MUST be exactly one of the allowed tables above. Never invent a table.
2. "column" MUST list real columns from the schema below, qualified as table.column,
   and MUST include resident_profile.name first for any resident-facing answer.
   Never use "*". Never invent a column.
3. "filters" is a list of objects: {{"column": "table.column", "operator": "=", "value": "..."}}.
   - For a resident name, use {{"column": "resident_profile.name", "operator": "=", "value": "<full name>"}}.
     Use the resident's full name when you know it, not a partial fragment.
   - Never add a community_id, date, or time filter. The backend applies community scope automatically.
4. "limit" is REQUIRED. Use 1 for a single resident or a top/bottom ranking; use a small number (<=50) otherwise.
5. order_by/order_direction: for lowest/least/fewest use order_direction "ASC"; for highest/most/best use "DESC".
6. If the request cannot be answered from the allowed tables, return a minimal valid plan that yields no rows:
   {{"table": "resident_profile", "column": "resident_profile.name", "filters": [], "limit": 1}}

Valid JSON shape:
{{
  "table": "resident_profile",
  "column": "resident_profile.name, resident_profile.flat_number",
  "filters": [{{"column": "resident_profile.name", "operator": "=", "value": "Ravi Kumar"}}],
  "limit": 1
}}

Schema (only these tables are allowed):
{schema_text}"""


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
    num_predict: int = 100,
    temperature: float | None = None,
    timeout: float | None = None,
) -> str:
    """Call the vLLM OpenAI-compatible chat API and return assistant content.

    ``timeout`` (seconds) overrides the client default for this one call —
    useful for latency-sensitive callers (e.g. intent extraction) that want to
    fail fast and fall back rather than block on a slow/unreachable server.
    """
    invoke_kwargs = {
        "temperature": LLM_DATA_TEMPERATURE if temperature is None else temperature,
        "max_tokens": num_predict,
    }
    if response_format == "json":
        invoke_kwargs["response_format"] = {"type": "json_object"}
    if timeout is not None:
        # Fast-fail mode: bound the wait AND skip the SDK's default 2 retries,
        # otherwise a single 8s timeout becomes ~24s (1 try + 2 retries).
        invoke_kwargs["timeout"] = timeout
        invoke_kwargs["max_retries"] = 0

    temp_llm = llm.bind(**invoke_kwargs)
    response = temp_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ])

    return response.content.strip() if isinstance(response.content, str) else str(response.content).strip()


def ask_llm(
    query: str,
    system_prompt: str = None,
    num_predict: int = 100,
    temperature: float | None = None,
) -> str:
    sys_prompt = system_prompt if system_prompt else get_system_prompt()
    return ask_with_messages(
        sys_prompt,
        query,
        num_predict=num_predict,
        temperature=temperature,
    )
