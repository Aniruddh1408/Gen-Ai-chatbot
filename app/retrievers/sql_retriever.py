"""
SQL Retriever — Text-to-SQL pipeline with English synthesis.
"""
import json
import re
from app.llm.client import ask_llm, ask_sql_planner
from app.core.db import run_query
from app.core.logger import get_logger

logger = get_logger("sql_retriever")

_SYNTHESIS_SYSTEM_PROMPT = """You are an Intelligent Clinical Data Summarizer.
The following data was SUCCESSFULLY retrieved from the internal clinical database.
Your task is to summarize this data for the attending physician.

STRICT RULES:
1. You must answer using ONLY the data provided below.
2. Be professional, clinical, and concise.
3. If asked about a resident, always include their name if present in the data.
4. Auto-Insights: Briefly mention any noticeable health patterns or basic logic (e.g. if BP is high).
5. Formatting: If the user asks for a list or bullet points, use markdown bullets.
"""

_RESIDENT_PROFILE_RULES = [
    {
        "name": "age",
        "patterns": [r"\bage\b", r"\bhow old\b", r"\bold is\b"],
        "column": "residents.name, residents.age",
    },
    {
        "name": "flat_no",
        "patterns": [r"\bflat\b", r"\bflat no\b", r"\bflat number\b", r"\broom\b"],
        "column": "residents.name, residents.flat_no",
    },
    {
        "name": "medical_history",
        "patterns": [r"\bmedical history\b", r"\bhealth history\b", r"\bhistory\b"],
        "column": "residents.name, residents.health_medical_history",
    },
    {
        "name": "medical_intake",
        "patterns": [r"\bprescribed\b", r"\bintake\b", r"\bmedication\b", r"\btreatment plan\b"],
        "column": "residents.name, residents.medical_intake_prescribed",
    },
]

_METRIC_RANKING_RULES = [
    {
        "name": "sleep_quality_score",
        "table": "sleep_analytics",
        "column": "residents.name, sleep_quality_score",
        "order_by": "sleep_quality_score",
        "label": "sleep score",
        "patterns": [
            r"\bsleep score\b",
            r"\bsleep quality\b",
            r"\bsleep quality score\b",
        ],
    },
    {
        "name": "sleep_duration_minutes",
        "table": "sleep_analytics",
        "column": "residents.name, sleep_duration_minutes",
        "order_by": "sleep_duration_minutes",
        "label": "sleep duration",
        "patterns": [
            r"\bsleep duration\b",
            r"\bsleep time\b",
            r"\bslept\b",
        ],
    },
    {
        "name": "steps_count",
        "table": "activity_metrics",
        "column": "residents.name, steps_count",
        "order_by": "steps_count",
        "label": "step count",
        "patterns": [
            r"\bsteps\b",
            r"\bstep count\b",
            r"\bwalking\b",
        ],
    },
    {
        "name": "sugar_level",
        "table": "health_reports",
        "column": "residents.name, sugar_level",
        "order_by": "sugar_level",
        "label": "sugar level",
        "patterns": [
            r"\bsugar\b",
            r"\bglucose\b",
        ],
    },
    {
        "name": "bp_systolic",
        "table": "health_reports",
        "column": "residents.name, bp_systolic",
        "order_by": "bp_systolic",
        "label": "systolic blood pressure",
        "patterns": [
            r"\bbp\b",
            r"\bblood pressure\b",
            r"\bsystolic\b",
        ],
    },
]

_ASC_RANKING_PATTERNS = [
    r"\bworst\b",
    r"\blowest\b",
    r"\bleast\b",
    r"\bfewest\b",
    r"\bbottom\b",
]

_DESC_RANKING_PATTERNS = [
    r"\bbest\b",
    r"\bhighest\b",
    r"\bmost\b",
    r"\btop\b",
]


def _extract_resident_name(query: str) -> str | None:
    q = query.lower().replace("’", "'").strip()
    patterns = [
        r"\b([a-z]+(?:\s+[a-z]+){1,2})'s\b",
        r"\b(?:resident|patient)\s+([a-z]+(?:\s+[a-z]+){1,2})\b",
        r"\b(?:of|for|about)\s+([a-z]+(?:\s+[a-z]+){1,2})\b",
        r"\b(?:of|for|about)\s+(?:the\s+)?(?:resident|patient)\s+([a-z]+(?:\s+[a-z]+){1,2})\b",
        r"\b([a-z]+(?:\s+[a-z]+){1,2})\s+(?:medical history|health history|treatment plan|flat(?:\s+(?:number|no))?|room|age|history|intake|prescribed|medication)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            candidate = match.group(1).strip(" .,?!")
            candidate = re.sub(r"^(?:what|who|is|the|of|for|about|resident|patient)\s+", "", candidate).strip()
            candidate = re.sub(
                r"\s+(?:medical|health|treatment|plan|flat|number|no|room|age|history|intake|prescribed|medication)$",
                "",
                candidate,
            ).strip()
            if candidate not in {"his", "her", "their", "the resident", "the patient"}:
                return candidate.title()
    return None


def _detect_resident_profile_plan(query: str) -> dict | None:
    resident_name = _extract_resident_name(query)
    if not resident_name:
        return None

    q_lower = query.lower()
    for rule in _RESIDENT_PROFILE_RULES:
        if any(re.search(pattern, q_lower) for pattern in rule["patterns"]):
            return {
                "table": "residents",
                "column": rule["column"],
                "filters": [{"column": "residents.name", "operator": "=", "value": resident_name}],
                "limit": 1,
                "_profile_field": rule["name"],
            }
    return None


def _format_resident_profile_answer(profile_field: str, result: list[tuple]) -> str | None:
    if not result:
        return None

    row = result[0]
    if len(row) < 2:
        return None

    resident_name = str(row[0]).strip()
    field_value = row[1]

    if field_value in (None, ""):
        return f"I couldn't find {profile_field.replace('_', ' ')} for {resident_name} in the database."

    if profile_field == "age":
        return f"{resident_name} is {field_value} years old."
    if profile_field == "flat_no":
        return f"{resident_name}'s flat number is {field_value}."
    if profile_field == "medical_history":
        return f"{resident_name}'s medical history is: {field_value}"
    if profile_field == "medical_intake":
        return f"{resident_name}'s prescribed medical intake is: {field_value}"
    return None


def _detect_metric_ranking_plan(query: str) -> dict | None:
    q_lower = query.lower()

    order_direction = None
    if any(re.search(pattern, q_lower) for pattern in _ASC_RANKING_PATTERNS):
        order_direction = "ASC"
    elif any(re.search(pattern, q_lower) for pattern in _DESC_RANKING_PATTERNS):
        order_direction = "DESC"

    if not order_direction:
        return None

    for rule in _METRIC_RANKING_RULES:
        if any(re.search(pattern, q_lower) for pattern in rule["patterns"]):
            return {
                "table": rule["table"],
                "column": rule["column"],
                "filters": [],
                "order_by": rule["order_by"],
                "order_direction": order_direction,
                "limit": 1,
                "_metric_name": rule["name"],
                "_metric_label": rule["label"],
            }
    return None


def _format_metric_ranking_answer(query: str, plan: dict, result: list[tuple]) -> str | None:
    if not result:
        return None

    row = result[0]
    if len(row) < 2:
        return None

    resident_name = str(row[0]).strip()
    metric_value = row[1]
    metric_label = plan.get("_metric_label", "metric")
    q_lower = query.lower()

    if plan.get("_metric_name") == "bp_systolic":
        metric_text = f"{metric_value} mmHg"
    elif plan.get("_metric_name") == "sleep_duration_minutes":
        metric_text = f"{metric_value} minutes"
    else:
        metric_text = str(metric_value)

    if any(re.search(pattern, q_lower) for pattern in _ASC_RANKING_PATTERNS):
        qualifier = "worst" if "sleep" in metric_label else "lowest"
    else:
        qualifier = "best" if "sleep" in metric_label else "highest"

    return f"The resident with the {qualifier} {metric_label} is {resident_name}, with {metric_label} {metric_text}."

def build_sql(plan: dict) -> tuple[str, list]:
    table = plan.get("table", "residents")
    column = plan.get("column", "residents.name")
    order_by = plan.get("order_by")
    
    # 1. CLEAN ORDER BY: Strip existing ASC/DESC to prevent 'DESC DESC' errors
    if order_by:
        order_by = order_by.upper().replace(" DESC", "").replace(" ASC", "").strip()

    # Strict validation of direction
    raw_dir = str(plan.get("order_direction", "ASC")).upper()
    order_dir = "DESC" if "DESC" in raw_dir else "ASC"
    
    limit = plan.get("limit", 10)
    
    # Handle auto-join for resident names
    from_clause = table
    # DEFENSIVE: Only attempt .get() if f is actually a dictionary
    filters_list = plan.get("filters", [])
    if not isinstance(filters_list, list):
        filters_list = []
        
    has_resident_filter = any(
        isinstance(f, dict) and "residents." in str(f.get("column", "")) 
        for f in filters_list
    )
    
    if "residents." in column or has_resident_filter:
        if table != "residents" and "residents" not in table:
            from_clause = f"{table} JOIN residents ON {table}.resident_id = residents.id"

    sql = f"SELECT {column} FROM {from_clause}"
    
    conditions = []
    params = []
    
    # DEFENSIVE: Ensure filters is actually a list of dictionaries
    raw_filters = plan.get("filters", [])
    if isinstance(raw_filters, dict):
        raw_filters = [raw_filters]
    if not isinstance(raw_filters, list):
        raw_filters = []
        
    for f in raw_filters:
        if not isinstance(f, dict):
            continue
            
        col = f.get("column")
        op = f.get("operator", "=")
        val = f.get("value")
        if col and val is not None:
            # 2. IMPROVEMENT: Use ILIKE for case-insensitive name matching
            if "name" in col.lower() and op == "=":
                clean_val = str(val).replace("'s", "").replace("’s", "").strip()
                conditions.append(f"{col} ILIKE %s")
                params.append(f"%{clean_val}%")
            else:
                conditions.append(f"{col} {op} %s")
                params.append(val)
            
    # 3. SAFETY: Ensure limit is a valid integer to prevent "LIMIT None" errors
    try:
        limit = int(limit)
    except (ValueError, TypeError):
        limit = 10

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    if order_by:
        sql += f" ORDER BY {order_by} {order_dir}"
    sql += f" LIMIT {limit}"
    
    return sql, params

def clean_json(json_str: str) -> str:
    """Removes trailing commas from JSON string to prevent parse errors."""
    # Remove trailing commas before matching closing brackets
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*]', ']', json_str)
    return json_str

def normalize_filters(plan: dict) -> dict:
    """Convert drifted string filters into structured filter objects."""
    raw_filters = plan.get("filters", [])
    if isinstance(raw_filters, dict):
        raw_filters = [raw_filters]
    if not isinstance(raw_filters, list):
        raw_filters = []

    normalized = []
    for item in raw_filters:
        if isinstance(item, dict):
            normalized.append(item)
            continue
        if not isinstance(item, str):
            continue

        match = re.match(
            r"^\s*([a-zA-Z_][\w\.]*)\s*(=|!=|>=|<=|>|<|ILIKE)\s*'?(.+?)'?\s*$",
            item,
            re.IGNORECASE,
        )
        if not match:
            continue

        col, op, value = match.groups()
        normalized.append({
            "column": col,
            "operator": op.upper() if op.upper() == "ILIKE" else op,
            "value": value,
        })

    plan["filters"] = normalized
    return plan

def handle_sql(query: str) -> dict:
    try:
        direct_metric_plan = _detect_metric_ranking_plan(query)
        if direct_metric_plan:
            logger.info(f"Using deterministic metric ranking plan: {direct_metric_plan}")
            sql, params = build_sql(direct_metric_plan)
            result = run_query(sql, params)

            if not result:
                return {
                    "query": query,
                    "plan": direct_metric_plan,
                    "sql": sql,
                    "result": result,
                    "answer": f"I couldn't find matching records for '{query}'.",
                }

            answer = _format_metric_ranking_answer(query, direct_metric_plan, result) or ask_llm(
                f"User Query: {query}\nRetrieved Database Data: {result}\nProfessional Summary:",
                system_prompt=_SYNTHESIS_SYSTEM_PROMPT,
            )

            return {
                "query": query,
                "plan": direct_metric_plan,
                "sql": sql,
                "result": result,
                "answer": answer,
            }

        direct_profile_plan = _detect_resident_profile_plan(query)
        if direct_profile_plan:
            logger.info(f"Using deterministic resident profile plan: {direct_profile_plan}")
            sql, params = build_sql(direct_profile_plan)
            result = run_query(sql, params)

            if not result:
                return {
                    "query": query,
                    "plan": direct_profile_plan,
                    "sql": sql,
                    "result": result,
                    "answer": f"I couldn't find matching resident records for '{query}'.",
                }

            answer = _format_resident_profile_answer(
                direct_profile_plan["_profile_field"],
                result,
            ) or ask_llm(
                f"User Query: {query}\nRetrieved Database Data: {result}\nProfessional Summary:",
                system_prompt=_SYNTHESIS_SYSTEM_PROMPT,
            )

            return {
                "query": query,
                "plan": direct_profile_plan,
                "sql": sql,
                "result": result,
                "answer": answer,
            }

        # MACRO BYPASS: Handle complex multi-metric "Care" analytics
        complex_keywords = ["more care", "less care", "overall health", "all metrics", "comprehensive", "needs care", "need care"]
        q_lower = query.lower()
        if any(w in q_lower for w in complex_keywords):
            logger.info("Executing comprehensive care macro...")
            sql = """
            SELECT r.name, r.age, r.health_medical_history, 
                   h.bp_systolic, h.bp_diastolic, h.sugar_level, 
                   s.sleep_quality_score, a.steps_count 
            FROM residents r
            LEFT JOIN health_reports h ON r.id = h.resident_id
            LEFT JOIN sleep_analytics s ON r.id = s.resident_id
            LEFT JOIN activity_metrics a ON r.id = a.resident_id
            LIMIT 10;
            """
            result = run_query(sql)
            
            # Use synthesize chain for the macro result
            answer = ask_llm(
                f"User Query: {query}\nRetrieved Database Data: Macro Care Assessment Data: {result}\nReview this data horizontally to determine who needs more or less care.\nProfessional Summary:",
                system_prompt=_SYNTHESIS_SYSTEM_PROMPT,
            )
            
            return {
                "query": query,
                "plan": {"macro": "comprehensive_care_analysis"},
                "sql": sql,
                "result": result,
                "answer": answer
            }

        # Step 1: Generate & Parse Plan (Normal Single-Table Mode)
        plan_str = ask_sql_planner(query)

        if not plan_str:
            retry_query = f"Convert this user request into one JSON SQL plan only: {query}"
            plan_str = ask_sql_planner(retry_query)

        if not plan_str:
             raise ValueError("Planner returned an empty response.")

        # Strip markdown if present
        if "```" in plan_str:
            parts = plan_str.split("```")
            plan_str = parts[1] if len(parts) > 1 else parts[0]
            if plan_str.startswith("json"): plan_str = plan_str[4:]
        
        plan_str = clean_json(plan_str.strip())
        
        try:
            plan = json.loads(plan_str)
        except json.JSONDecodeError as je:
            logger.error(f"JSON Parse failed on: {plan_str}")
            # FALLBACK: Try to extract anything between { }
            if "{" in plan_str and "}" in plan_str:
                start = plan_str.find("{")
                end = plan_str.rfind("}") + 1
                plan = json.loads(clean_json(plan_str[start:end]))
            else:
                raise ValueError("The AI got confused and failed to generate a valid data plan for this query.")
                
        # STRICT VALIDATION: Ensure the parsed plan is actually a dictionary
        if not isinstance(plan, dict):
            raise ValueError("The AI generated a JSON structure, but it was not a valid dictionary plan.")

        plan = normalize_filters(plan)
        logger.info(f"SQL Plan Generated: {plan}")
        
        # Step 2: Build & Execute SQL
        sql, params = build_sql(plan)
        logger.info(f"SQL Query Built: {sql} | Params: {params}")
        result = run_query(sql, params)
        logger.info(f"Query Result: {result}")
        
        # Step 3: English Synthesis
        # OPTIMIZATION: If result is empty, skip LLM synthesis for speed
        if not result:
            return {
                "query": query,
                "plan": plan,
                "sql": sql,
                "result": result,
                "answer": f"I couldn't find any clinical records matching '{query}' in the database."
            }

        answer = ask_llm(
            f"User Query: {query}\nRetrieved Database Data: {result}\nProfessional Summary:",
            system_prompt=_SYNTHESIS_SYSTEM_PROMPT,
        )
        
        # CHART GENERATOR OVERRIDE
        chart_payload = None
        q_lower = query.lower()
        visual_keywords = ["chart", "graph", "plot", "visualize", "show stats", "comparison"]
        if result and any(w in q_lower for w in visual_keywords):
            # Determine dynamic chart type
            chart_type = "bar"
            if "pie" in q_lower: chart_type = "pie"
            elif "line" in q_lower: chart_type = "line"
            elif "doughnut" in q_lower or "donut" in q_lower: chart_type = "doughnut"

            # Parse results flexibly
            labels = []
            data_points = []
            
            for i, row in enumerate(result):
                if len(row) >= 2:
                    # Case: (Name, Value, ...)
                    labels.append(str(row[0]))
                    # Find the first float-able value after the label
                    val = 0
                    for cell in row[1:]:
                        try:
                            val = float(cell)
                            break
                        except (ValueError, TypeError): continue
                    data_points.append(val)
                else:
                    # Case: (Value,) — No name column provided by LLM
                    labels.append(f"Resident {i+1}")
                    try:
                        data_points.append(float(row[0]))
                    except (ValueError, TypeError):
                        data_points.append(0)
                    
            chart_payload = {
                "type": chart_type,
                "data": {
                    "labels": labels,
                    "datasets": [{
                        "label": "Requested Health Metric",
                        "data": data_points,
                        "backgroundColor": ["#38bdf8", "#818cf8", "#4ade80", "#fbbf24", "#f87171", "#c084fc"],
                        "borderColor": "rgba(255, 255, 255, 0.1)",
                        "borderWidth": 1
                    }]
                },
                "options": {
                    "responsive": True,
                    "maintainAspectRatio": False,
                    "plugins": {
                        "legend": { "display": chart_type != "bar" }
                    }
                }
            }
        
        return {
            "query": query,
            "plan": plan,
            "sql": sql,
            "result": result,
            "answer": answer,
            "chart_data": chart_payload
        }
    except Exception as e:
        logger.error(f"SQL Pipeline error: {e}")
        return {"error": str(e), "answer": "I encountered a technical error while analyzing that request."}
