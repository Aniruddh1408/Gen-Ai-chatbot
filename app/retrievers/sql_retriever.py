"""
SQL Retriever — Text-to-SQL pipeline using LangChain chains.
Generates a JSON plan via LLM, validates it, builds safe parameterized SQL, and executes.
"""
import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.llm.client import llm, get_system_prompt
from app.schema.schema import SCHEMA, schema_to_text
from app.core.db import run_query
from app.core.logger import get_logger

logger = get_logger("sql_retriever")


# ----------------------------
# 1. Plan Generation Chain
# ----------------------------
_plan_prompt = ChatPromptTemplate.from_messages([
    ("system", "{system_prompt}"),
    ("human", "{query}"),
])

_plan_chain = _plan_prompt | llm | StrOutputParser()


def generate_plan(query: str) -> str:
    """
    Generate a JSON SQL plan using a single clean system prompt.
    The user query goes into the human message — no schema duplication.
    """
    system_prompt = get_system_prompt()
    return _plan_chain.invoke({"system_prompt": system_prompt, "query": query})


# ----------------------------
# 2. Parse JSON
# ----------------------------
def parse_plan(plan_str: str) -> dict | None:
    """Extract and parse JSON from LLM output, handling markdown fences."""
    try:
        # Strip markdown json block tags if the LLM hallucinates them
        if "```json" in plan_str:
            plan_str = plan_str.split("```json")[1].split("```")[0]
        elif "```" in plan_str:
            plan_str = plan_str.split("```")[1].split("```")[0]
        return json.loads(plan_str.strip())
    except (json.JSONDecodeError, IndexError) as e:
        logger.warning(f"Failed to parse plan JSON: {e}", extra={"raw": plan_str[:300]})
        return None


# ----------------------------
# 3. Normalize Plan
# ----------------------------
def normalize_plan(plan: dict) -> dict:
    """Sanitize and normalize the LLM-generated plan fields."""
    # Aggregation
    agg = plan.get("aggregation", "")
    if isinstance(agg, str):
        agg = agg.lower().strip()
        if agg not in ["avg", "sum", "count", "max", "min"]:
            agg = ""
    else:
        agg = ""
    plan["aggregation"] = agg

    # Column
    col = plan.get("column", "")
    col = str(col).replace("`", "").replace("'", "").strip()
    plan["column"] = col

    # Group by
    group_by = plan.get("group_by", "")
    plan["group_by"] = str(group_by).replace("`", "").replace("'", "").strip()

    # Limit
    limit = plan.get("limit", 100)
    try:
        plan["limit"] = int(limit)
    except (ValueError, TypeError):
        plan["limit"] = 100

    # Filters — normalize heterogeneous key names from LLM output
    filters = plan.get("filters", [])
    new_filters = []
    for f in filters:
        column = f.get("column") or f.get("field")
        value = f.get("value") or f.get("compare_value")
        operator = f.get("operator", "=")

        if column and value is not None:
            new_filters.append({
                "column": column,
                "operator": operator,
                "value": value,
            })

    plan["filters"] = new_filters
    return plan


# ----------------------------
# 4. Validate Plan
# ----------------------------
def validate_plan(plan: dict) -> bool:
    """Validate plan against the known schema. Raises ValueError on invalid fields."""
    table = plan.get("table", "")
    column = plan.get("column", "")
    agg = plan.get("aggregation", "")
    group_by = plan.get("group_by", "")

    if table not in SCHEMA:
        raise ValueError(f"Invalid table: {table}")

    schema = SCHEMA[table]["columns"]

    if column and column != "*" and column not in schema:
        raise ValueError(f"Invalid column: {column}")

    if group_by:
        for col in group_by.split(","):
            if col.strip() not in schema:
                raise ValueError(f"Invalid group_by column: {col.strip()}")

    if agg in ["avg", "sum", "max", "min"]:
        col_type = schema.get(column, "numeric")
        if col_type not in ["numeric"]:
            raise ValueError(f"Aggregation {agg} not allowed on {column}")

    return True


# ----------------------------
# 5. Retry with Feedback Chain
# ----------------------------
_retry_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a strict SQL planner for an IoT analytics system.
The previous plan was INCORRECT.
Fix the JSON plan based on the error feedback.
Return ONLY valid JSON. No explanation."""),
    ("human", """Error: {error_msg}

User Query: {query}"""),
])

_retry_chain = _retry_prompt | llm | StrOutputParser()


def retry_plan(query: str, error_msg: str) -> str:
    """Re-generate plan with the validation error as feedback."""
    return _retry_chain.invoke({"query": query, "error_msg": error_msg})


# ----------------------------
# 6. Build SQL (DYNAMIC & SAFE)
# ----------------------------
def build_sql(plan: dict) -> tuple[str, list]:
    """Convert a validated plan into a parameterized SQL query."""
    table = plan["table"]
    col = plan["column"] if plan["column"] else "*"
    agg = plan.get("aggregation")
    group_by = plan.get("group_by")
    limit = plan.get("limit", 100)

    # Build selections dynamically
    selections = []
    if group_by:
        selections.append(group_by)

    if agg:
        selections.append(f"{agg.upper()}({col}) as result")
    else:
        selections.append(col)

    sql = f"SELECT {', '.join(selections)} FROM {table}"

    conditions = []
    params = []

    for f in plan.get("filters", []):
        column = f["column"]
        op = str(f["operator"]).upper().strip()
        val = f["value"]

        # Prevent SQL injection via operator string
        allowed_ops = ["=", "!=", ">", "<", ">=", "<=", "LIKE", "ILIKE", "IN", "IS", "IS NOT"]
        if op not in allowed_ops:
            op = "="

        if op == "IN":
            if isinstance(val, list):
                # Secure parameterization for lists
                placeholders = ", ".join(["%s"] * len(val))
                conditions.append(f"{column} IN ({placeholders})")
                params.extend(val)
            else:
                conditions.append(f"{column} = %s")
                params.append(val)
        elif "IS" in op:
            if str(val).upper() in ["NULL", "TRUE", "FALSE"]:
                conditions.append(f"{column} {op} {str(val).upper()}")
            else:
                conditions.append(f"{column} {op} NULL")
        else:
            conditions.append(f"{column} {op} %s")
            params.append(val)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    if group_by:
        sql += f" GROUP BY {group_by}"

    sql += f" LIMIT {limit}"

    return sql, params


# ----------------------------
# 7. Main Handler
# ----------------------------
def handle_sql(query: str) -> dict:
    """Full text-to-SQL pipeline: plan → validate → build → execute."""
    # Step 1: Generate plan via LLM chain
    plan_str = generate_plan(query)
    logger.info("Raw plan generated", extra={"raw_plan": plan_str[:300]})

    # Step 2: Parse JSON
    plan = parse_plan(plan_str)
    if not plan:
        return {"error": "Invalid JSON", "raw": plan_str}

    # Step 3: Normalize
    plan = normalize_plan(plan)
    logger.info("Plan normalized", extra={"plan": str(plan)})

    # Step 4: Validate + Retry
    try:
        validate_plan(plan)
    except ValueError as e:
        logger.warning(f"Validation failed: {e}, retrying...")
        retry_str = retry_plan(query, str(e))
        retry_plan_json = parse_plan(retry_str)

        if retry_plan_json:
            plan = normalize_plan(retry_plan_json)
            try:
                validate_plan(plan)
            except ValueError as e2:
                return {"error": "Plan failed after retry", "details": str(e2), "plan": plan}
        else:
            return {"error": "Retry failed", "raw": retry_str}

    # Step 5: Build parameterized SQL
    sql, params = build_sql(plan)

    # Step 6: Execute
    try:
        result = run_query(sql, params)
    except Exception as e:
        return {"error": "SQL execution failed", "sql": sql, "params": params, "details": str(e)}

    return {
        "query": query,
        "plan": plan,
        "sql": sql,
        "params": params,
        "result": result,
    }