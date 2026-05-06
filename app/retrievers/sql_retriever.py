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
4. Do not add auto-insights, recommendations, diagnoses, or pattern analysis unless the user explicitly asks for analysis, risks, care priority, trends, patterns, or recommendations.
5. For simple list, detail, or value requests, answer only with the requested data.
6. Formatting: If the user asks for a list or bullet points, use markdown bullets.
7. Complete every sentence. If many rows are returned, use compact bullets instead of long prose.
"""

_SYNTHESIS_MAX_TOKENS = 320

_RESIDENT_PROFILE_RULES = [
    {
        "name": "age",
        "patterns": [r"\bage\b", r"\bhow old\b", r"\bold is\b"],
        "column": "residents.name, residents.age",
    },
    {
        "name": "flat_no",
        "patterns": [
            r"\bflat\b",
            r"\bflat no\b",
            r"\bflat number\b",
            r"\broom\b",
            r"\bwhere\s+(?:does|is)\b",
            r"\bstay\b",
            r"\bstaying\b",
            r"\blive\b",
            r"\bliving\b",
            r"\bassigned\b",
        ],
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
    {
        "name": "details",
        "patterns": [
            r"\bdetails?\b",
            r"\binfo\b",
            r"\binformation\b",
            r"\bprofile\b",
            r"\btell\s+me\s+about\b",
            r"\bwho\s+is\b",
        ],
        "column": (
            "residents.name, residents.id, residents.flat_no, residents.age, "
            "residents.health_medical_history, residents.medical_intake_prescribed"
        ),
    },
    {
        "name": "name",
        "patterns": [r"\bname\b"],
        "column": "residents.name, residents.id",
    },
]

_RESIDENT_LIST_PATTERNS = [
    r"\b(?:list|show|display|get)\b(?:\s+me)?(?:\s+the)?(?:\s+all)?\s+(?:residents|patients)\b",
    r"\bgive\s+me\s+(?:the\s+)?list\s+of\s+(?:the\s+)?(?:residents|patients)\b",
    r"\b(?:list|show|display|get)\b(?:\s+me)?(?:\s+the)?\s+list\s+of\s+(?:the\s+)?(?:residents|patients)\b",
    r"\b(?:the\s+)?list\s+of\s+(?:the\s+)?(?:residents|patients)\b",
    r"\bwho\s+are\s+(?:the\s+)?(?:residents|patients)\b",
]

_RESIDENT_LIST_METRIC_TERMS = {
    "age",
    "ages",
    "old",
    "flat",
    "flats",
    "room",
    "rooms",
    "medical",
    "history",
    "histories",
    "medication",
    "medications",
    "intake",
    "prescribed",
    "detail",
    "details",
    "bp",
    "blood pressure",
    "sugar",
    "glucose",
    "steps",
    "sleep",
    "score",
    "quality",
    "duration",
    "highest",
    "lowest",
    "best",
    "worst",
    "top",
    "bottom",
    "care",
    "analysis",
    "analyze",
    "compare",
    "comparison",
    "chart",
    "graph",
    "plot",
}

_RESIDENT_COLLECTION_TERMS = {
    "residents",
    "patients",
    "they",
    "them",
    "their",
    "theirs",
    "these",
    "those",
}

_RANKING_TERMS = {
    "best",
    "worst",
    "highest",
    "lowest",
    "top",
    "bottom",
    "most",
    "least",
    "fewest",
    "oldest",
    "youngest",
    "runner-up",
    "runner up",
}

_METRIC_RANKING_RULES = [
    {
        "name": "sleep_quality_score",
        "table": "sleep_analytics",
        "column": "residents.name, sleep_quality_score",
        "order_by": "sleep_quality_score",
        "label": "sleep score",
        "patterns": [
            r"\bsleep score\b",
            r"\bsleep scores\b",
            r"\bsleep quality\b",
            r"\bsleep quality score\b",
            r"\bsleep quality scores\b",
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
            r"\bstep counts\b",
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
            r"\bsugar level\b",
            r"\bsugar levels\b",
            r"\bglucose level\b",
            r"\bglucose levels\b",
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
            r"\bblood pressures\b",
            r"\bsystolic\b",
        ],
    },
]

_RESIDENT_AVERAGE_METRIC_RULES = [
    {
        "metric": "sugar",
        "patterns": [r"\bsugar\b", r"\bglucose\b"],
        "sql": """
        WITH latest_health AS (
            SELECT DISTINCT ON (resident_id)
                resident_id, sugar_level, recorded_at
            FROM health_reports
            ORDER BY resident_id, recorded_at DESC
        )
        SELECT ROUND(AVG(h.sugar_level)::numeric, 1)
        FROM residents r
        JOIN latest_health h ON r.id = h.resident_id
        WHERE r.community_id = %s;
        """,
        "label": "sugar level",
        "suffix": "",
    },
    {
        "metric": "steps",
        "patterns": [r"\bsteps\b", r"\bstep count\b", r"\bstep counts\b", r"\bactivity\b"],
        "sql": """
        WITH latest_activity AS (
            SELECT DISTINCT ON (resident_id)
                resident_id, steps_count, recorded_at
            FROM activity_metrics
            ORDER BY resident_id, recorded_at DESC
        )
        SELECT ROUND(AVG(a.steps_count)::numeric, 1)
        FROM residents r
        JOIN latest_activity a ON r.id = a.resident_id
        WHERE r.community_id = %s;
        """,
        "label": "step count",
        "suffix": " steps",
    },
    {
        "metric": "sleep_duration",
        "patterns": [r"\bsleep duration\b", r"\bsleep time\b", r"\bslept\b"],
        "sql": """
        WITH latest_sleep AS (
            SELECT DISTINCT ON (resident_id)
                resident_id, sleep_duration_minutes, recorded_at
            FROM sleep_analytics
            ORDER BY resident_id, recorded_at DESC
        )
        SELECT ROUND(AVG(s.sleep_duration_minutes)::numeric, 1)
        FROM residents r
        JOIN latest_sleep s ON r.id = s.resident_id
        WHERE r.community_id = %s;
        """,
        "label": "sleep duration",
        "suffix": " minutes",
    },
    {
        "metric": "sleep_quality",
        "patterns": [r"\bsleep score\b", r"\bsleep scores\b", r"\bsleep quality\b"],
        "sql": """
        WITH latest_sleep AS (
            SELECT DISTINCT ON (resident_id)
                resident_id, sleep_quality_score, recorded_at
            FROM sleep_analytics
            ORDER BY resident_id, recorded_at DESC
        )
        SELECT ROUND(AVG(s.sleep_quality_score)::numeric, 1)
        FROM residents r
        JOIN latest_sleep s ON r.id = s.resident_id
        WHERE r.community_id = %s;
        """,
        "label": "sleep score",
        "suffix": "",
    },
    {
        "metric": "bp",
        "patterns": [r"\bbp\b", r"\bblood pressure\b"],
        "sql": """
        WITH latest_health AS (
            SELECT DISTINCT ON (resident_id)
                resident_id, bp_systolic, bp_diastolic, recorded_at
            FROM health_reports
            ORDER BY resident_id, recorded_at DESC
        )
        SELECT
            ROUND(AVG(h.bp_systolic)::numeric, 1),
            ROUND(AVG(h.bp_diastolic)::numeric, 1)
        FROM residents r
        JOIN latest_health h ON r.id = h.resident_id
        WHERE r.community_id = %s;
        """,
        "label": "blood pressure",
        "suffix": " mmHg",
    },
]

_DEVICE_METRIC_LABELS = {
    "signal": "signal",
    "uptime": "uptime",
    "cpu": "CPU",
}

_NAMED_RESIDENT_METRIC_TERMS = [
    ("all_metrics", ["health metrics", "all metrics", "vital signs", "vitals"]),
    ("bp", ["bp", "blood pressure", "systolic", "diastolic"]),
    ("sugar", ["sugar", "glucose"]),
    ("steps", ["steps", "step count", "activity"]),
    ("sleep_duration", ["sleep duration", "sleep time", "slept"]),
    ("sleep_quality", ["sleep score", "sleep quality", "sleep scores"]),
    ("sleep", ["sleep"]),
]

_CARE_ASSESSMENT_KEYWORDS = [
    "more care",
    "most care",
    "more acre",
    "most acre",
    "less care",
    "least care",
    "less acre",
    "least acre",
    "requires less care",
    "requires least care",
    "requires less acre",
    "requires least acre",
    "highest care",
    "highest priority",
    "lowest care",
    "lowest priority",
    "care priority",
    "overall health",
    "health metrics",
    "all metrics",
    "comprehensive",
    "needs care",
    "need care",
    "prioritize",
    "risk",
    "risks",
    "at risk",
    "health risk",
    "risk score",
    "needs attention",
    "need attention",
    "critical",
    "vital signs",
    "vitals",
    "other residents",
    "requires care",
    "require care",
    "requires more care",
    "requires less care",
    "requires more acre",
    "requires less acre",
    "healthy",
    "healthiest",
    "unhealthy",
    "unhealthiest",
    "most unhealthy",
    "not healthy",
    "least healthy",
    "most healthy",
    "best health",
    "worst health",
    "poorest health",
    "poor health",
    "stable health",
    "most stable",
    "least stable",
    "lowest risk",
    "highest risk",
    "least risk",
    "most at risk",
]

_LOW_RISK_CARE_PHRASES = [
    "less care",
    "least care",
    "less acre",
    "least acre",
    "lower care",
    "routine care",
    "lowest care",
    "lowest priority",
    "least priority",
    "routine priority",
    "healthy",
    "healthiest",
    "most healthy",
    "best health",
    "best overall health",
    "stable health",
    "most stable",
    "lowest risk",
    "least risk",
    "least attention",
    "lowest attention",
    "does not need care",
    "doesn't need care",
    "doesnt need care",
]

_HIGH_RISK_CARE_PHRASES = [
    "more care",
    "most care",
    "more acre",
    "most acre",
    "higher care",
    "highest care",
    "highest priority",
    "needs care",
    "need care",
    "requires care",
    "require care",
    "requires more care",
    "requires most care",
    "requires more acre",
    "requires most acre",
    "needs attention",
    "need attention",
    "critical",
    "risk",
    "risks",
    "at risk",
    "health risk",
    "highest risk",
    "most at risk",
    "not healthy",
    "unhealthy",
    "unhealthiest",
    "most unhealthy",
    "least healthy",
    "worst health",
    "poorest health",
    "poor health",
    "least stable",
]

_HEALTHIEST_CARE_PHRASES = [
    "healthy",
    "healthiest",
    "most healthy",
    "best health",
    "best overall health",
    "stable health",
    "most stable",
]

_UNHEALTHY_CARE_PHRASES = [
    "not healthy",
    "unhealthy",
    "unhealthiest",
    "most unhealthy",
    "least healthy",
    "worst health",
    "poorest health",
    "poor health",
    "least stable",
]

_BROAD_CARE_PHRASES = [
    "other residents",
    "other patients",
    "all residents",
    "all patients",
    "all metrics",
    "comprehensive",
    "what about",
]

_ASC_RANKING_PATTERNS = [
    r"\bworst\b",
    r"\blowest\b",
    r"\bleast\b",
    r"\bfewest\b",
    r"\bbottom\b",
    r"\bshortest\b",
]

_DESC_RANKING_PATTERNS = [
    r"\bbest\b",
    r"\bhighest\b",
    r"\bmost\b",
    r"\btop\b",
    r"\blongest\b",
    r"\brunner[-\s]?up\b",
]

_ORDINAL_WORDS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}

_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _extract_resident_name(query: str) -> str | None:
    q = query.lower().replace("’", "'").strip()
    patterns = [
        r"\b(?:h?ow\s+old\s+is|(?:what\s+is\s+)?(?:the\s+)?age\s+of)\s+(?:resident\s+|patient\s+)?([a-z]+(?:\s+[a-z]+){1,2})\b",
        r"\bwho\s+is\s+(?:resident\s+|patient\s+)?([a-z]+(?:\s+[a-z]+){1,2})\b",
        r"\b(?:what|which)\s+(?:flat|room)(?:\s+(?:number|no))?\s+(?:is|does)\s+(?:resident\s+|patient\s+)?([a-z]+(?:\s+[a-z]+){1,2})(?:\s+(?:in|have|has))?\b",
        r"\b(?:where\s+(?:does|is))\s+(?:resident\s+|patient\s+)?([a-z]+(?:\s+[a-z]+){1,2})(?:\s+(?:stay|staying|live|living|assigned))?\b",
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
                r"\s+(?:medical|health|treatment|plan|flat|number|no|room|age|history|intake|prescribed|medication|in|have|has|stay|staying|live|living|assigned)$",
                "",
                candidate,
            ).strip()
            if candidate not in {
                "his",
                "her",
                "their",
                "the resident",
                "the patient",
                "all residents",
                "all patients",
                "residents",
                "patients",
                "these residents",
                "those residents",
                "community residents",
            }:
                return candidate.title()
    return None


def _extract_resident_id(query: str) -> int | None:
    q = query.lower().strip()
    if not re.search(r"\b(?:resident|patient)\b", q):
        return None

    patterns = [
        r"\b(?:resident|patient)\s+(?:with\s+)?(?:the\s+)?(?:id|number|no\.?|#)\s*(?:is\s*)?(\d+)\b",
        r"\b(?:resident|patient)\s+#\s*(\d+)\b",
        r"\b(?:id|number|no\.?|#)\s*(?:is\s*)?(\d+)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            return int(match.group(1))
    return None


def _detect_resident_profile_plan(query: str) -> dict | None:
    q_lower = query.lower()
    for rule in _RESIDENT_PROFILE_RULES:
        if any(re.search(pattern, q_lower) for pattern in rule["patterns"]):
            resident_id = _extract_resident_id(query)
            if resident_id is not None:
                return {
                    "table": "residents",
                    "column": rule["column"],
                    "filters": [{"column": "residents.id", "operator": "=", "value": resident_id}],
                    "limit": 1,
                    "_profile_field": rule["name"],
                }

            resident_name = _extract_resident_name(query)
            if not resident_name:
                return None

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
    if profile_field == "name":
        if not row or row[0] in (None, ""):
            return None
        resident_name = str(row[0]).strip()
        resident_id = row[1] if len(row) > 1 else None
        return f"{resident_name} (ID {resident_id})" if resident_id is not None else resident_name

    if len(row) < 2:
        return None

    resident_name = str(row[0]).strip()
    field_value = row[1]

    if profile_field == "details":
        if len(row) >= 6:
            resident_id = row[1]
            flat_no = row[2]
            age = row[3]
            history = row[4]
            medication = row[5]
            id_text = f"ID {resident_id}, " if resident_id is not None else ""
        else:
            flat_no = row[1] if len(row) > 1 else None
            age = row[2] if len(row) > 2 else None
            history = row[3] if len(row) > 3 else None
            medication = row[4] if len(row) > 4 else None
            id_text = ""
        age_text = f"{age} years" if age is not None else "age not recorded"
        return (
            f"{resident_name} ({id_text}{flat_no or 'room not recorded'}, {age_text}). "
            f"Medical history: {history or 'not recorded'}. "
            f"Prescribed medication: {medication or 'not recorded'}."
        )

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


def _detect_resident_list_plan(query: str) -> dict | None:
    q_lower = query.lower().strip()
    if not any(re.search(pattern, q_lower) for pattern in _RESIDENT_LIST_PATTERNS):
        return None

    if any(term in q_lower for term in _RESIDENT_LIST_METRIC_TERMS):
        return None

    return {
        "table": "residents",
        "column": "residents.name, residents.flat_no",
        "filters": [],
        "order_by": "residents.flat_no",
        "order_direction": "ASC",
        "limit": 100,
        "_macro": "resident_list",
    }


def _format_resident_list_answer(result: list[tuple]) -> str:
    if not result:
        return "I couldn't find residents in this community."

    lines = ["Residents in this community:"]
    for row in result:
        resident_name = str(row[0]).strip() if len(row) > 0 and row[0] is not None else "Unnamed resident"
        flat_no = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        if flat_no:
            lines.append(f"- {resident_name} ({flat_no})")
        else:
            lines.append(f"- {resident_name}")
    return "\n".join(lines)


def _is_resident_collection_query(q_lower: str) -> bool:
    words = {word.strip(".,?!") for word in q_lower.split()}
    if words.intersection(_RESIDENT_COLLECTION_TERMS):
        return True
    if any(action in words for action in {"all", "list", "show", "display", "give", "get"}):
        profile_or_metric_terms = [
            "age", "ages", "room", "rooms", "flat", "flats", "medical", "history", "histories",
            "medication", "medications", "bp", "blood pressure", "sugar", "glucose", "steps",
            "sleep", "metrics", "details",
        ]
        if any(term in q_lower for term in profile_or_metric_terms):
            return True
    return "listed residents" in q_lower or "community residents" in q_lower


def _has_ranking_request(q_lower: str) -> bool:
    return any(term in q_lower for term in _RANKING_TERMS) or re.search(r"\btop\s+\d+\b", q_lower) is not None


def _detect_resident_aggregate_plan(query: str) -> dict | None:
    q_lower = query.lower().strip()
    has_resident_scope = any(term in q_lower for term in ["resident", "residents", "patient", "patients"])
    if not has_resident_scope:
        return None

    if any(term in q_lower for term in ["how many", "count", "number of", "total"]):
        return {"_macro": "resident_aggregate", "_aggregate": "count"}

    if any(term in q_lower for term in ["average age", "avg age", "mean age"]):
        return {"_macro": "resident_aggregate", "_aggregate": "average_age"}

    limit = 1
    count_match = re.search(r"\b(?:top|oldest|youngest)\s+(\d+)\b", q_lower)
    if count_match:
        limit = max(int(count_match.group(1)), 1)

    if "oldest" in q_lower:
        return {
            "table": "residents",
            "column": "residents.name, residents.age",
            "filters": [],
            "order_by": "residents.age",
            "order_direction": "DESC",
            "limit": limit,
            "_macro": "resident_age_ranking",
            "_rank_type": "oldest",
        }

    if "youngest" in q_lower:
        return {
            "table": "residents",
            "column": "residents.name, residents.age",
            "filters": [],
            "order_by": "residents.age",
            "order_direction": "ASC",
            "limit": limit,
            "_macro": "resident_age_ranking",
            "_rank_type": "youngest",
        }

    return None


def _run_resident_aggregate(plan: dict, community_id: int) -> dict:
    aggregate = plan.get("_aggregate")
    if aggregate == "count":
        sql = "SELECT COUNT(*) FROM residents WHERE community_id = %s;"
        result = run_query(sql, (community_id,))
        count = result[0][0] if result else 0
        return {
            "plan": plan,
            "sql": sql,
            "result": result,
            "answer": f"There are {count} residents in this community.",
        }

    sql = "SELECT ROUND(AVG(age)::numeric, 1) FROM residents WHERE community_id = %s;"
    result = run_query(sql, (community_id,))
    average_age = result[0][0] if result else None
    if average_age is None:
        answer = "I couldn't find recorded ages for residents in this community."
    else:
        answer = f"The average resident age in this community is {average_age} years."
    return {
        "plan": plan,
        "sql": sql,
        "result": result,
        "answer": answer,
    }


def _format_resident_age_ranking_answer(plan: dict, result: list[tuple]) -> str:
    if not result:
        return "I couldn't find resident age records in this community."

    rank_type = plan.get("_rank_type", "ranked")
    if len(result) == 1:
        name, age = result[0]
        return f"The {rank_type} resident is {name}, age {age}."

    lines = [f"The {rank_type} residents are:"]
    for index, row in enumerate(result, start=1):
        name, age = row
        lines.append(f"{index}. {name}: {age} years")
    return "\n".join(lines)


def _detect_resident_collection_profile_plan(query: str) -> dict | None:
    q_lower = query.lower().strip()
    if not _is_resident_collection_query(q_lower):
        return None

    if _has_ranking_request(q_lower):
        return None

    base_plan = {
        "table": "residents",
        "filters": [],
        "order_by": "residents.flat_no",
        "order_direction": "ASC",
        "limit": 100,
    }

    if any(term in q_lower for term in ["age", "ages", "old"]):
        return {
            **base_plan,
            "column": "residents.name, residents.age",
            "_macro": "resident_collection_profile",
            "_profile_field": "ages",
        }

    if any(term in q_lower for term in ["flat", "flats", "room", "rooms"]):
        return {
            **base_plan,
            "column": "residents.name, residents.flat_no",
            "_macro": "resident_collection_profile",
            "_profile_field": "rooms",
        }

    if any(term in q_lower for term in ["medical history", "medical histories", "health history", "histories"]):
        return {
            **base_plan,
            "column": "residents.name, residents.health_medical_history",
            "_macro": "resident_collection_profile",
            "_profile_field": "medical_histories",
        }

    if any(term in q_lower for term in ["medication", "medications", "intake", "prescribed", "treatment"]):
        return {
            **base_plan,
            "column": "residents.name, residents.medical_intake_prescribed",
            "_macro": "resident_collection_profile",
            "_profile_field": "medications",
        }

    if any(term in q_lower for term in ["detail", "details", "profile", "profiles", "info", "information", "about"]):
        return {
            **base_plan,
            "column": (
                "residents.name, residents.flat_no, residents.age, "
                "residents.health_medical_history, residents.medical_intake_prescribed"
            ),
            "_macro": "resident_collection_profile",
            "_profile_field": "details",
        }

    return None


def _format_resident_collection_profile_answer(plan: dict, result: list[tuple]) -> str:
    if not result:
        return "I couldn't find residents in this community."

    profile_field = plan.get("_profile_field")
    if profile_field == "ages":
        lines = ["Resident ages:"]
        for name, age in result:
            age_text = f"{age} years" if age is not None else "not recorded"
            lines.append(f"- {name}: {age_text}")
        return "\n".join(lines)

    if profile_field == "rooms":
        lines = ["Resident rooms:"]
        for name, flat_no in result:
            lines.append(f"- {name}: {flat_no or 'not recorded'}")
        return "\n".join(lines)

    if profile_field == "medical_histories":
        lines = ["Resident medical histories:"]
        for name, history in result:
            lines.append(f"- {name}: {history or 'not recorded'}")
        return "\n".join(lines)

    if profile_field == "medications":
        lines = ["Resident prescribed medications:"]
        for name, medication in result:
            lines.append(f"- {name}: {medication or 'not recorded'}")
        return "\n".join(lines)

    if profile_field == "details":
        lines = ["Resident details:"]
        for row in result:
            name, flat_no, age, history, medication = row
            age_text = f"{age} years" if age is not None else "age not recorded"
            lines.append(
                f"- {name} ({flat_no or 'room not recorded'}, {age_text}): "
                f"history: {history or 'not recorded'}; medication: {medication or 'not recorded'}."
            )
        return "\n".join(lines)

    return _format_resident_list_answer(result)


def _detect_resident_metric_summary_plan(query: str) -> dict | None:
    q_lower = query.lower().strip()
    if not _is_resident_collection_query(q_lower):
        return None

    if _has_ranking_request(q_lower):
        return None

    if any(term in q_lower for term in ["bp", "blood pressure"]):
        return {"_macro": "resident_metric_summary", "_metric": "bp"}
    if any(term in q_lower for term in ["sugar", "glucose"]):
        return {"_macro": "resident_metric_summary", "_metric": "sugar"}
    if any(term in q_lower for term in ["steps", "step count", "activity"]):
        return {"_macro": "resident_metric_summary", "_metric": "steps"}
    if any(term in q_lower for term in ["sleep duration", "sleep time", "slept"]):
        return {"_macro": "resident_metric_summary", "_metric": "sleep_duration"}
    if any(term in q_lower for term in ["sleep score", "sleep quality", "sleep scores"]):
        return {"_macro": "resident_metric_summary", "_metric": "sleep_quality"}
    if "all metrics" in q_lower or "health metrics" in q_lower:
        return {"_macro": "resident_metric_summary", "_metric": "all_metrics"}

    return None


def _detect_resident_average_metric_plan(query: str) -> dict | None:
    q_lower = query.lower().strip()
    if not any(term in q_lower for term in ["average", "avg", "mean"]):
        return None

    if re.search(r"\bage\b|\bages\b", q_lower):
        return None

    for rule in _RESIDENT_AVERAGE_METRIC_RULES:
        if any(re.search(pattern, q_lower) for pattern in rule["patterns"]):
            return {"_macro": "resident_average_metric", **rule}

    return None


def _run_resident_average_metric(plan: dict, community_id: int) -> dict:
    sql = plan["sql"]
    result = run_query(sql, (community_id,))
    label = plan["label"]
    suffix = plan.get("suffix", "")

    if not result or result[0][0] is None:
        answer = f"I couldn't find recorded {label} values in this community."
    elif plan.get("metric") == "bp":
        systolic, diastolic = result[0]
        answer = f"The average blood pressure in this community is {systolic}/{diastolic} mmHg."
    else:
        value = result[0][0]
        answer = f"The average {label} in this community is {value}{suffix}."

    return {
        "query": "",
        "plan": plan,
        "sql": sql,
        "result": result,
        "answer": answer,
    }


def _extract_device_id(query: str) -> str | None:
    match = re.search(r"\bDEV\d+\b", query, re.IGNORECASE)
    return match.group(0).upper() if match else None


def _device_metric_from_query(q_lower: str) -> str | None:
    if "signal" in q_lower or "rssi" in q_lower:
        return "signal"
    if "uptime" in q_lower or "availability" in q_lower:
        return "uptime"
    if "cpu" in q_lower or "processor" in q_lower or "load" in q_lower:
        return "cpu"
    return None


def _is_device_query(query: str) -> bool:
    q_lower = query.lower()
    return (
        _extract_device_id(query) is not None
        or any(term in q_lower for term in ["device", "devices", "board", "boards", "telemetry"])
        or _device_metric_from_query(q_lower) is not None
    )


def _device_order_direction(q_lower: str, metric: str) -> str:
    low_terms = ["lowest", "least", "weakest", "worst", "minimum", "min", "low"]
    high_terms = ["highest", "most", "strongest", "best", "maximum", "max", "high"]

    if any(term in q_lower for term in low_terms):
        return "ASC"
    if any(term in q_lower for term in high_terms):
        return "DESC"

    return "ASC" if metric == "signal" else "DESC"


def _detect_device_status_plan(query: str) -> dict | None:
    if not _is_device_query(query):
        return None

    q_lower = query.lower().strip()
    board_id = _extract_device_id(query)
    metric = _device_metric_from_query(q_lower)

    if any(term in q_lower for term in ["average", "avg", "mean"]):
        if not metric:
            metric = "uptime"
        return {"_macro": "device_average", "_metric": metric}

    if board_id:
        return {"_macro": "device_details", "board_id": board_id}

    if metric and any(term in q_lower for term in [
        "highest", "lowest", "strongest", "weakest", "best", "worst", "top", "bottom", "max", "min"
    ]):
        return {
            "_macro": "device_ranking",
            "_metric": metric,
            "_order_direction": _device_order_direction(q_lower, metric),
        }

    if any(term in q_lower for term in ["list", "show", "display", "all", "status", "statuses", "devices", "boards"]):
        return {"_macro": "device_list"}

    if metric:
        return {"_macro": "device_list"}

    return None


def _format_device_row(row: tuple) -> str:
    board_id, location, signal, uptime, cpu, recorded_time = row
    return (
        f"{board_id} ({location or 'location not recorded'}): "
        f"signal {signal}, uptime {uptime}, CPU {cpu}, time {recorded_time}."
    )


def _run_device_status(plan: dict) -> dict:
    macro = plan.get("_macro")

    if macro == "device_details":
        sql = """
        SELECT board_id, location, signal, uptime, cpu, time
        FROM device_status
        WHERE UPPER(board_id) = %s
        ORDER BY time DESC
        LIMIT 1;
        """
        result = run_query(sql, (plan["board_id"],))
        answer = _format_device_row(result[0]) if result else f"I couldn't find device status for {plan['board_id']}."
        return {"query": "", "plan": plan, "sql": sql, "result": result, "answer": answer}

    if macro == "device_ranking":
        metric = plan["_metric"]
        order_direction = plan["_order_direction"]
        sql = f"""
        SELECT board_id, location, {metric}, time
        FROM device_status
        ORDER BY {metric} {order_direction}, board_id ASC
        LIMIT 1;
        """
        result = run_query(sql)
        label = _DEVICE_METRIC_LABELS[metric]
        if result:
            board_id, location, value, recorded_time = result[0]
            qualifier = "lowest" if order_direction == "ASC" else "highest"
            if metric == "signal":
                qualifier = "weakest" if order_direction == "ASC" else "strongest"
            answer = (
                f"The device with the {qualifier} {label} is {board_id} "
                f"({location or 'location not recorded'}), with {label} {value} at {recorded_time}."
            )
        else:
            answer = f"I couldn't find device {label} records."
        return {"query": "", "plan": plan, "sql": sql, "result": result, "answer": answer}

    if macro == "device_average":
        metric = plan["_metric"]
        sql = f"SELECT ROUND(AVG({metric})::numeric, 1) FROM device_status;"
        result = run_query(sql)
        label = _DEVICE_METRIC_LABELS[metric]
        value = result[0][0] if result and result[0][0] is not None else None
        answer = (
            f"The average device {label} is {value}."
            if value is not None
            else f"I couldn't find device {label} records."
        )
        return {"query": "", "plan": plan, "sql": sql, "result": result, "answer": answer}

    sql = """
    SELECT board_id, location, signal, uptime, cpu, time
    FROM device_status
    ORDER BY board_id ASC
    LIMIT 100;
    """
    result = run_query(sql)
    if not result:
        answer = "I couldn't find device status records."
    else:
        lines = ["Device status:"]
        lines.extend(f"- {_format_device_row(row)}" for row in result)
        answer = "\n".join(lines)
    return {"query": "", "plan": plan, "sql": sql, "result": result, "answer": answer}


def _run_resident_metric_summary(plan: dict, community_id: int) -> dict:
    metric = plan.get("_metric")
    if metric in {"bp", "sugar"}:
        select_columns = "h.bp_systolic, h.bp_diastolic, h.sugar_level"
        sql = f"""
        WITH latest_health AS (
            SELECT DISTINCT ON (resident_id)
                resident_id, bp_systolic, bp_diastolic, sugar_level, recorded_at
            FROM health_reports
            ORDER BY resident_id, recorded_at DESC
        )
        SELECT r.name, r.flat_no, {select_columns}
        FROM residents r
        LEFT JOIN latest_health h ON r.id = h.resident_id
        WHERE r.community_id = %s
        ORDER BY r.flat_no, r.name;
        """
    elif metric == "steps":
        sql = """
        WITH latest_activity AS (
            SELECT DISTINCT ON (resident_id)
                resident_id, steps_count, recorded_at
            FROM activity_metrics
            ORDER BY resident_id, recorded_at DESC
        )
        SELECT r.name, r.flat_no, a.steps_count
        FROM residents r
        LEFT JOIN latest_activity a ON r.id = a.resident_id
        WHERE r.community_id = %s
        ORDER BY r.flat_no, r.name;
        """
    elif metric in {"sleep_quality", "sleep_duration"}:
        sql = """
        WITH latest_sleep AS (
            SELECT DISTINCT ON (resident_id)
                resident_id, sleep_duration_minutes, sleep_quality_score, recorded_at
            FROM sleep_analytics
            ORDER BY resident_id, recorded_at DESC
        )
        SELECT r.name, r.flat_no, s.sleep_duration_minutes, s.sleep_quality_score
        FROM residents r
        LEFT JOIN latest_sleep s ON r.id = s.resident_id
        WHERE r.community_id = %s
        ORDER BY r.flat_no, r.name;
        """
    else:
        sql = """
        WITH latest_health AS (
            SELECT DISTINCT ON (resident_id)
                resident_id, bp_systolic, bp_diastolic, sugar_level, recorded_at
            FROM health_reports
            ORDER BY resident_id, recorded_at DESC
        ),
        latest_activity AS (
            SELECT DISTINCT ON (resident_id)
                resident_id, steps_count, recorded_at
            FROM activity_metrics
            ORDER BY resident_id, recorded_at DESC
        ),
        latest_sleep AS (
            SELECT DISTINCT ON (resident_id)
                resident_id, sleep_duration_minutes, sleep_quality_score, recorded_at
            FROM sleep_analytics
            ORDER BY resident_id, recorded_at DESC
        )
        SELECT
            r.name,
            r.flat_no,
            h.bp_systolic,
            h.bp_diastolic,
            h.sugar_level,
            a.steps_count,
            s.sleep_duration_minutes,
            s.sleep_quality_score
        FROM residents r
        LEFT JOIN latest_health h ON r.id = h.resident_id
        LEFT JOIN latest_activity a ON r.id = a.resident_id
        LEFT JOIN latest_sleep s ON r.id = s.resident_id
        WHERE r.community_id = %s
        ORDER BY r.flat_no, r.name;
        """

    result = run_query(sql, (community_id,))
    return {
        "query": "",
        "plan": plan,
        "sql": sql,
        "result": result,
        "answer": _format_resident_metric_summary_answer(metric, result),
    }


def _format_resident_metric_summary_answer(metric: str, result: list[tuple]) -> str:
    if not result:
        return "I couldn't find resident metric records in this community."

    if metric == "bp":
        lines = ["Resident blood pressure readings:"]
        for name, flat_no, systolic, diastolic, _sugar in result:
            bp_text = f"{systolic}/{diastolic} mmHg" if systolic is not None and diastolic is not None else "not recorded"
            lines.append(f"- {name} ({flat_no or 'room not recorded'}): {bp_text}")
        return "\n".join(lines)

    if metric == "sugar":
        lines = ["Resident sugar levels:"]
        for name, flat_no, _systolic, _diastolic, sugar in result:
            sugar_text = f"{sugar}" if sugar is not None else "not recorded"
            lines.append(f"- {name} ({flat_no or 'room not recorded'}): {sugar_text}")
        return "\n".join(lines)

    if metric == "steps":
        lines = ["Resident step counts:"]
        for name, flat_no, steps in result:
            steps_text = f"{steps} steps" if steps is not None else "not recorded"
            lines.append(f"- {name} ({flat_no or 'room not recorded'}): {steps_text}")
        return "\n".join(lines)

    if metric == "sleep_quality":
        lines = ["Resident sleep quality scores:"]
        for name, flat_no, _duration, score in result:
            score_text = f"{score}" if score is not None else "not recorded"
            lines.append(f"- {name} ({flat_no or 'room not recorded'}): {score_text}")
        return "\n".join(lines)

    if metric == "sleep_duration":
        lines = ["Resident sleep durations:"]
        for name, flat_no, duration, _score in result:
            duration_text = f"{duration} minutes" if duration is not None else "not recorded"
            lines.append(f"- {name} ({flat_no or 'room not recorded'}): {duration_text}")
        return "\n".join(lines)

    lines = ["Resident health metrics:"]
    for row in result:
        name, flat_no, systolic, diastolic, sugar, steps, sleep_duration, sleep_score = row
        bp_text = f"{systolic}/{diastolic} mmHg" if systolic is not None and diastolic is not None else "BP not recorded"
        sugar_text = f"sugar {sugar}" if sugar is not None else "sugar not recorded"
        steps_text = f"steps {steps}" if steps is not None else "steps not recorded"
        sleep_text = (
            f"sleep {sleep_duration} minutes, score {sleep_score}"
            if sleep_duration is not None or sleep_score is not None
            else "sleep not recorded"
        )
        lines.append(f"- {name} ({flat_no or 'room not recorded'}): {bp_text}; {sugar_text}; {steps_text}; {sleep_text}.")
    return "\n".join(lines)


def _detect_named_resident_metric(query: str) -> str | None:
    q_lower = query.lower().strip()

    if _is_resident_collection_query(q_lower) or _has_ranking_request(q_lower):
        return None

    for metric, terms in _NAMED_RESIDENT_METRIC_TERMS:
        if any(term in q_lower for term in terms):
            return metric
    return None


def _is_care_assessment_query(query: str) -> bool:
    q_lower = query.lower()
    return any(keyword in q_lower for keyword in _CARE_ASSESSMENT_KEYWORDS)


def _contains_care_phrase(q_lower: str, phrases: list[str]) -> bool:
    return any(
        re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", q_lower)
        for phrase in phrases
    )


def _find_named_resident_in_query(query: str, community_id: int) -> str | None:
    q_lower = query.lower()
    try:
        rows = run_query(
            """
            SELECT name
            FROM residents
            WHERE community_id = %s
            ORDER BY LENGTH(name) DESC;
            """,
            (community_id,),
        )
    except Exception:
        rows = []

    for row in rows:
        resident_name = str(row[0]).strip()
        if resident_name and resident_name.lower() in q_lower:
            return resident_name

    return _extract_resident_name(query)


def _format_named_resident_metric_answer(metric: str, row: tuple) -> str:
    (
        name,
        flat_no,
        age,
        _history,
        _medication,
        bp_systolic,
        bp_diastolic,
        sugar_level,
        steps_count,
        sleep_duration_minutes,
        sleep_quality_score,
    ) = row

    resident_label = f"{name} ({flat_no or 'room not recorded'}, {age} years)"
    bp_text = (
        f"{bp_systolic}/{bp_diastolic} mmHg"
        if bp_systolic is not None and bp_diastolic is not None
        else "not recorded"
    )
    sugar_text = f"{sugar_level}" if sugar_level is not None else "not recorded"
    steps_text = f"{steps_count} steps" if steps_count is not None else "not recorded"
    sleep_duration_text = (
        f"{sleep_duration_minutes} minutes"
        if sleep_duration_minutes is not None
        else "not recorded"
    )
    sleep_quality_text = (
        f"{sleep_quality_score}"
        if sleep_quality_score is not None
        else "not recorded"
    )

    if metric == "bp":
        return f"{name}'s latest blood pressure is {bp_text}."
    if metric == "sugar":
        return f"{name}'s latest sugar level is {sugar_text}."
    if metric == "steps":
        return f"{name}'s latest step count is {steps_text}."
    if metric == "sleep_duration":
        return f"{name}'s latest sleep duration is {sleep_duration_text}."
    if metric == "sleep_quality":
        return f"{name}'s latest sleep quality score is {sleep_quality_text}."
    if metric == "sleep":
        return (
            f"{name}'s latest sleep metrics are: duration {sleep_duration_text}; "
            f"quality score {sleep_quality_text}."
        )

    return "\n".join([
        f"{resident_label} latest recorded metrics:",
        f"- Blood pressure: {bp_text}",
        f"- Sugar level: {sugar_text}",
        f"- Step count: {steps_text}",
        f"- Sleep duration: {sleep_duration_text}",
        f"- Sleep quality score: {sleep_quality_text}",
    ])


def _run_named_resident_metric(query: str, metric: str, community_id: int) -> dict | None:
    resident_name = _find_named_resident_in_query(query, community_id)
    if not resident_name:
        return None

    sql = """
    WITH target_resident AS (
        SELECT id, name, flat_no, age, health_medical_history, medical_intake_prescribed
        FROM residents
        WHERE community_id = %s
          AND name ILIKE %s
        ORDER BY name
        LIMIT 1
    ),
    latest_health AS (
        SELECT DISTINCT ON (resident_id)
            resident_id, bp_systolic, bp_diastolic, sugar_level, recorded_at
        FROM health_reports
        ORDER BY resident_id, recorded_at DESC
    ),
    latest_activity AS (
        SELECT DISTINCT ON (resident_id)
            resident_id, steps_count, recorded_at
        FROM activity_metrics
        ORDER BY resident_id, recorded_at DESC
    ),
    latest_sleep AS (
        SELECT DISTINCT ON (resident_id)
            resident_id, sleep_duration_minutes, sleep_quality_score, recorded_at
        FROM sleep_analytics
        ORDER BY resident_id, recorded_at DESC
    )
    SELECT
        r.name,
        r.flat_no,
        r.age,
        r.health_medical_history,
        r.medical_intake_prescribed,
        h.bp_systolic,
        h.bp_diastolic,
        h.sugar_level,
        a.steps_count,
        s.sleep_duration_minutes,
        s.sleep_quality_score
    FROM target_resident r
    LEFT JOIN latest_health h ON r.id = h.resident_id
    LEFT JOIN latest_activity a ON r.id = a.resident_id
    LEFT JOIN latest_sleep s ON r.id = s.resident_id;
    """
    params = (community_id, f"%{resident_name}%")
    result = run_query(sql, params)

    plan = {
        "_macro": "named_resident_metric",
        "_metric": metric,
        "resident_name": resident_name,
    }

    if not result:
        return {
            "query": query,
            "plan": plan,
            "sql": sql,
            "result": result,
            "answer": f"I couldn't find matching resident records for '{resident_name}' in this community.",
        }

    return {
        "query": query,
        "plan": plan,
        "sql": sql,
        "result": result,
        "answer": _format_named_resident_metric_answer(metric, result[0]),
    }


def _ordinal_label(position: int) -> str:
    labels = {
        1: "1st",
        2: "2nd",
        3: "3rd",
    }
    if position in labels:
        return labels[position]
    return f"{position}th"


def _parse_ranking_window(query: str, order_direction: str) -> dict:
    q_lower = query.lower()

    ordinal_match = re.search(r"\b(\d+)(?:st|nd|rd|th)\b", q_lower)
    if ordinal_match:
        position = int(ordinal_match.group(1))
        return {
            "limit": 1,
            "offset": max(position - 1, 0),
            "rank_position": position,
            "is_rank_list": False,
        }

    if re.search(r"\brunner[-\s]?up\b", q_lower):
        return {
            "limit": 1,
            "offset": 1,
            "rank_position": 2,
            "is_rank_list": False,
        }

    for word, position in _ORDINAL_WORDS.items():
        if re.search(rf"\b{word}\b", q_lower):
            return {
                "limit": 1,
                "offset": max(position - 1, 0),
                "rank_position": position,
                "is_rank_list": False,
            }

    list_count = None
    if order_direction == "DESC":
        list_match = re.search(r"\b(?:top|best|highest|most)\s+(\d+)\b", q_lower)
    else:
        list_match = re.search(r"\b(?:bottom|worst|lowest|least|fewest)\s+(\d+)\b", q_lower)

    if list_match:
        list_count = int(list_match.group(1))
    else:
        list_word_match = None
        if order_direction == "DESC":
            list_word_match = re.search(r"\b(?:top|best|highest|most)\s+([a-z]+)\b", q_lower)
        else:
            list_word_match = re.search(r"\b(?:bottom|worst|lowest|least|fewest)\s+([a-z]+)\b", q_lower)
        if list_word_match:
            list_count = _NUMBER_WORDS.get(list_word_match.group(1))

    if list_count:
        limit = max(list_count, 1)
        return {
            "limit": limit,
            "offset": 0,
            "rank_position": None,
            "is_rank_list": limit > 1,
        }

    return {
        "limit": 1,
        "offset": 0,
        "rank_position": 1,
        "is_rank_list": False,
    }


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
            ranking_window = _parse_ranking_window(query, order_direction)
            return {
                "table": rule["table"],
                "column": rule["column"],
                "filters": [],
                "order_by": rule["order_by"],
                "order_direction": order_direction,
                "limit": ranking_window["limit"],
                "offset": ranking_window["offset"],
                "_metric_name": rule["name"],
                "_metric_label": rule["label"],
                "_rank_position": ranking_window["rank_position"],
                "_is_rank_list": ranking_window["is_rank_list"],
            }
    return None


def _format_metric_ranking_answer(query: str, plan: dict, result: list[tuple]) -> str | None:
    if not result:
        return None

    metric_label = plan.get("_metric_label", "metric")
    q_lower = query.lower()

    def format_metric_value(value) -> str:
        if plan.get("_metric_name") == "bp_systolic":
            return f"{value} mmHg"
        if plan.get("_metric_name") == "sleep_duration_minutes":
            return f"{value} minutes"
        return str(value)

    if any(re.search(pattern, q_lower) for pattern in _ASC_RANKING_PATTERNS):
        qualifier = "worst" if "sleep" in metric_label else "lowest"
    else:
        qualifier = "best" if "sleep" in metric_label else "highest"

    if plan.get("_is_rank_list"):
        lines = []
        start_position = int(plan.get("offset", 0)) + 1
        for idx, row in enumerate(result, start=start_position):
            if len(row) < 2:
                continue
            resident_name = str(row[0]).strip()
            lines.append(f"{_ordinal_label(idx)}: {resident_name} - {format_metric_value(row[1])}")
        if not lines:
            return None
        return f"The {qualifier} {metric_label} rankings are:\n" + "\n".join(lines)

    row = result[0]
    if len(row) < 2:
        return None

    resident_name = str(row[0]).strip()
    metric_text = format_metric_value(row[1])
    rank_position = plan.get("_rank_position") or (int(plan.get("offset", 0)) + 1)
    if rank_position and int(rank_position) > 1:
        qualifier = f"{_ordinal_label(int(rank_position))} {qualifier}"

    return f"The resident with the {qualifier} {metric_label} is {resident_name}, with {metric_label} {metric_text}."


def _format_empty_metric_ranking_answer(plan: dict) -> str:
    metric_label = plan.get("_metric_label", "metric")
    rank_position = plan.get("_rank_position")
    if rank_position:
        return f"I couldn't find a {_ordinal_label(int(rank_position))} ranked resident for {metric_label}."
    return f"I couldn't find matching {metric_label} records."


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric_text(value, suffix: str = "") -> str:
    if value is None:
        return "not recorded"
    return f"{value}{suffix}"


def _score_care_row(row: tuple) -> dict:
    (
        resident_id,
        name,
        age,
        medical_history,
        bp_systolic,
        bp_diastolic,
        sugar_level,
        steps_count,
        sleep_duration_minutes,
        sleep_quality_score,
    ) = row

    score = 0
    reasons = []

    def add(points: int, reason: str):
        nonlocal score
        score += points
        reasons.append(reason)

    age_value = _to_float(age)
    systolic = _to_float(bp_systolic)
    diastolic = _to_float(bp_diastolic)
    sugar = _to_float(sugar_level)
    steps = _to_float(steps_count)
    sleep_minutes = _to_float(sleep_duration_minutes)
    sleep_score = _to_float(sleep_quality_score)

    if age_value is not None:
        if age_value >= 85:
            add(2, f"age {int(age_value)}")
        elif age_value >= 75:
            add(1, f"age {int(age_value)}")

    if systolic is not None or diastolic is not None:
        if (systolic is not None and systolic >= 160) or (diastolic is not None and diastolic >= 100):
            add(3, f"very high BP {_metric_text(bp_systolic)}/{_metric_text(bp_diastolic)}")
        elif (systolic is not None and systolic >= 140) or (diastolic is not None and diastolic >= 90):
            add(2, f"elevated BP {_metric_text(bp_systolic)}/{_metric_text(bp_diastolic)}")
        elif (systolic is not None and systolic >= 130) or (diastolic is not None and diastolic >= 85):
            add(1, f"borderline BP {_metric_text(bp_systolic)}/{_metric_text(bp_diastolic)}")

    if sugar is not None:
        if sugar >= 180:
            add(3, f"very high sugar {sugar_level}")
        elif sugar >= 140:
            add(2, f"high sugar {sugar_level}")
        elif sugar >= 125:
            add(1, f"borderline sugar {sugar_level}")

    if sleep_score is not None:
        if sleep_score < 50:
            add(2, f"low sleep score {sleep_quality_score}")
        elif sleep_score < 60:
            add(1, f"borderline sleep score {sleep_quality_score}")

    if sleep_minutes is not None:
        if sleep_minutes < 300:
            add(2, f"short sleep duration {sleep_duration_minutes} minutes")
        elif sleep_minutes < 360:
            add(1, f"reduced sleep duration {sleep_duration_minutes} minutes")

    if steps is not None:
        if steps < 2500:
            add(2, f"low activity {steps_count} steps")
        elif steps < 3500:
            add(1, f"reduced activity {steps_count} steps")

    history_text = str(medical_history or "").lower()
    history_rules = [
        ("diabetes", "diabetes history"),
        ("hypertension", "hypertension history"),
        ("cardiovascular", "cardiovascular history"),
        ("cardiac", "cardiac monitoring history"),
        ("post-surgery", "post-surgery support"),
        ("asthma", "asthma history"),
        ("osteoporosis", "osteoporosis history"),
    ]
    for keyword, reason in history_rules:
        if keyword in history_text:
            add(1, reason)

    if score >= 9:
        priority = "High"
    elif score >= 5:
        priority = "Moderate"
    else:
        priority = "Routine"

    return {
        "resident_id": resident_id,
        "name": name,
        "age": age,
        "medical_history": medical_history,
        "bp_systolic": bp_systolic,
        "bp_diastolic": bp_diastolic,
        "sugar_level": sugar_level,
        "steps_count": steps_count,
        "sleep_duration_minutes": sleep_duration_minutes,
        "sleep_quality_score": sleep_quality_score,
        "care_score": score,
        "care_priority": priority,
        "reasons": reasons or ["no major risk signals in the recorded metrics"],
    }


def _sort_care_assessments(assessments: list[dict], query: str) -> list[dict]:
    q_lower = query.lower()
    wants_low_risk = (
        _contains_care_phrase(q_lower, _LOW_RISK_CARE_PHRASES)
        and not _contains_care_phrase(q_lower, _HIGH_RISK_CARE_PHRASES)
    )
    if wants_low_risk:
        return sorted(assessments, key=lambda item: (item["care_score"], item["name"]))
    return sorted(assessments, key=lambda item: (-item["care_score"], item["name"]))

def _requested_care_display_count(q_lower: str) -> int:
    number_words = "|".join(_NUMBER_WORDS.keys())

    digit_match = re.search(
        r"\b(?:only|just|top|first|show|give|list)(?:\s+me)?(?:\s+the)?\s+(\d+)\b",
        q_lower,
    )
    if digit_match:
        return max(1, int(digit_match.group(1)))

    word_match = re.search(
        rf"\b(?:only|just|top|first|show|give|list)(?:\s+me)?(?:\s+the)?\s+({number_words})\b",
        q_lower,
    )
    if word_match:
        return max(1, _NUMBER_WORDS[word_match.group(1)])

    if any(phrase in q_lower for phrase in ["only one", "just one", "single resident", "one resident", "one patient"]):
        return 1

    if re.search(
        r"\b(?:who(?:'s|s|\s+is)|which\s+resident\s+is)\s+(?:the\s+)?"
        r"(?:healthiest|most\s+healthy|unhealthiest|most\s+unhealthy|not\s+healthy|"
        r"least\s+healthy|best\s+health|worst\s+health|poorest\s+health|poor\s+health|"
        r"most\s+stable|least\s+stable)\b",
        q_lower,
    ):
        return 1

    if _contains_care_phrase(q_lower, _BROAD_CARE_PHRASES):
        return 15

    return 5


def _care_ranking_label(q_lower: str, wants_low_risk: bool) -> str:
    if wants_low_risk and _contains_care_phrase(q_lower, _HEALTHIEST_CARE_PHRASES):
        return "healthiest"
    if wants_low_risk:
        return "lowest-priority"
    if _contains_care_phrase(q_lower, _UNHEALTHY_CARE_PHRASES):
        return "least-healthy"
    return "highest-priority"

def _format_care_assessment_answer(query: str, assessments: list[dict]) -> str:
    if not assessments:
        return "I couldn't find resident records with linked health, activity, and sleep metrics."

    q_lower = query.lower()
    sorted_items = _sort_care_assessments(assessments, query)
    wants_low_risk = (
        _contains_care_phrase(q_lower, _LOW_RISK_CARE_PHRASES)
        and not _contains_care_phrase(q_lower, _HIGH_RISK_CARE_PHRASES)
    )
    display_count = _requested_care_display_count(q_lower)
    visible_items = sorted_items[:display_count]

    priority_label = _care_ranking_label(q_lower, wants_low_risk)
    resident_label = "resident" if len(visible_items) == 1 else "residents"


    lines = [
        f"I assessed {len(assessments)} residents in this community using recorded BP, sugar, sleep, steps, age, and medical history.",
        f"Showing the {len(visible_items)} {priority_label} {resident_label}:",
    ]

    for idx, item in enumerate(visible_items, start=1):
        bp = f"{_metric_text(item['bp_systolic'])}/{_metric_text(item['bp_diastolic'])}"
        metrics = (
            f"BP {bp}, sugar {_metric_text(item['sugar_level'])}, "
            f"sleep score {_metric_text(item['sleep_quality_score'])}, "
            f"steps {_metric_text(item['steps_count'])}"
        )
        reasons = "; ".join(item["reasons"][:4])
        lines.append(
            f"{idx}. {item['name']} - {item['care_priority']} priority "
            f"(score {item['care_score']}). {metrics}. Reasons: {reasons}."
        )

    lines.append("This is a data-prioritization heuristic from recorded values, not a diagnosis.")
    return "\n".join(lines)


def _run_care_assessment(query: str, community_id: int = 1) -> dict:
    sql = """
    WITH latest_health AS (
        SELECT DISTINCT ON (resident_id)
            resident_id, bp_systolic, bp_diastolic, sugar_level, recorded_at
        FROM health_reports
        ORDER BY resident_id, recorded_at DESC
    ),
    latest_activity AS (
        SELECT DISTINCT ON (resident_id)
            resident_id, steps_count, recorded_at
        FROM activity_metrics
        ORDER BY resident_id, recorded_at DESC
    ),
    latest_sleep AS (
        SELECT DISTINCT ON (resident_id)
            resident_id, sleep_duration_minutes, sleep_quality_score, recorded_at
        FROM sleep_analytics
        ORDER BY resident_id, recorded_at DESC
    )
    SELECT
        r.id,
        r.name,
        r.age,
        r.health_medical_history,
        h.bp_systolic,
        h.bp_diastolic,
        h.sugar_level,
        a.steps_count,
        s.sleep_duration_minutes,
        s.sleep_quality_score
    FROM residents r
    LEFT JOIN latest_health h ON r.id = h.resident_id
    LEFT JOIN latest_activity a ON r.id = a.resident_id
    LEFT JOIN latest_sleep s ON r.id = s.resident_id
    WHERE r.community_id = %s
    ORDER BY r.id;
    """
    rows = run_query(sql, (community_id,))
    assessments = [_score_care_row(row) for row in rows]
    sorted_assessments = _sort_care_assessments(assessments, query)
    return {
        "query": query,
        "plan": {"macro": "deterministic_care_assessment"},
        "sql": sql,
        "result": sorted_assessments,
        "answer": _format_care_assessment_answer(query, assessments),
    }


_COMMUNITY_SCOPED_TABLES = {"residents", "health_reports", "activity_metrics", "sleep_analytics"}


def build_sql(plan: dict, community_id: int = 1) -> tuple[str, list]:
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
    offset = plan.get("offset", 0)
    
    # Handle auto-join for resident-scoped tables.
    # Community isolation is forced here instead of being delegated to the LLM.
    table_name = str(table).strip()
    from_clause = table_name
    # DEFENSIVE: Only attempt .get() if f is actually a dictionary
    filters_list = plan.get("filters", [])
    if not isinstance(filters_list, list):
        filters_list = []
        
    has_resident_filter = any(
        isinstance(f, dict) and "residents." in str(f.get("column", "")) 
        for f in filters_list
    )
    
    if table_name in _COMMUNITY_SCOPED_TABLES:
        if table_name != "residents":
            from_clause = f"{table_name} JOIN residents ON {table_name}.resident_id = residents.id"
    elif "residents." in column or has_resident_filter:
        from_clause = f"{table_name} JOIN residents ON {table_name}.resident_id = residents.id"

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
            if str(col).lower() in {"community_id", "residents.community_id"}:
                continue
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
    try:
        offset = int(offset)
    except (ValueError, TypeError):
        offset = 0
    offset = max(offset, 0)

    if "residents" in from_clause:
        conditions.append("residents.community_id = %s")
        params.append(community_id)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    if order_by:
        sql += f" ORDER BY {order_by} {order_dir}"
        if "residents" in from_clause:
            sql += ", residents.name ASC"
    sql += f" LIMIT {limit}"
    if offset:
        sql += f" OFFSET {offset}"
    
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

def handle_sql(query: str, community_id: int = 1) -> dict:
    try:
        device_status_plan = _detect_device_status_plan(query)
        if device_status_plan:
            logger.info(f"Using deterministic device status plan: {device_status_plan}")
            response = _run_device_status(device_status_plan)
            response["query"] = query
            return response

        resident_list_plan = _detect_resident_list_plan(query)
        if resident_list_plan:
            logger.info(f"Using deterministic resident list plan: {resident_list_plan}")
            sql, params = build_sql(resident_list_plan, community_id)
            result = run_query(sql, params)

            return {
                "query": query,
                "plan": resident_list_plan,
                "sql": sql,
                "result": result,
                "answer": _format_resident_list_answer(result),
            }

        resident_average_metric_plan = _detect_resident_average_metric_plan(query)
        if resident_average_metric_plan:
            logger.info(f"Using deterministic resident average metric plan: {resident_average_metric_plan}")
            response = _run_resident_average_metric(resident_average_metric_plan, community_id)
            response["query"] = query
            return response

        resident_metric_summary_plan = _detect_resident_metric_summary_plan(query)
        if resident_metric_summary_plan:
            logger.info(f"Using deterministic resident metric summary plan: {resident_metric_summary_plan}")
            response = _run_resident_metric_summary(resident_metric_summary_plan, community_id)
            response["query"] = query
            return response

        resident_aggregate_plan = _detect_resident_aggregate_plan(query)
        if resident_aggregate_plan:
            logger.info(f"Using deterministic resident aggregate plan: {resident_aggregate_plan}")
            if resident_aggregate_plan.get("_macro") == "resident_age_ranking":
                sql, params = build_sql(resident_aggregate_plan, community_id)
                result = run_query(sql, params)
                return {
                    "query": query,
                    "plan": resident_aggregate_plan,
                    "sql": sql,
                    "result": result,
                    "answer": _format_resident_age_ranking_answer(resident_aggregate_plan, result),
                }

            response = _run_resident_aggregate(resident_aggregate_plan, community_id)
            response["query"] = query
            return response

        named_metric = _detect_named_resident_metric(query)
        if named_metric:
            named_metric_response = _run_named_resident_metric(query, named_metric, community_id)
            if named_metric_response:
                logger.info(f"Using deterministic named resident metric plan: {named_metric_response.get('plan')}")
                return named_metric_response

        direct_profile_plan = None if _is_care_assessment_query(query) else _detect_resident_profile_plan(query)
        if direct_profile_plan:
            logger.info(f"Using deterministic resident profile plan: {direct_profile_plan}")
            sql, params = build_sql(direct_profile_plan, community_id)
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
                num_predict=_SYNTHESIS_MAX_TOKENS,
            )

            return {
                "query": query,
                "plan": direct_profile_plan,
                "sql": sql,
                "result": result,
                "answer": answer,
            }

        resident_collection_profile_plan = _detect_resident_collection_profile_plan(query)
        if resident_collection_profile_plan:
            logger.info(f"Using deterministic resident collection profile plan: {resident_collection_profile_plan}")
            sql, params = build_sql(resident_collection_profile_plan, community_id)
            result = run_query(sql, params)

            return {
                "query": query,
                "plan": resident_collection_profile_plan,
                "sql": sql,
                "result": result,
                "answer": _format_resident_collection_profile_answer(resident_collection_profile_plan, result),
            }

        direct_metric_plan = _detect_metric_ranking_plan(query)
        if direct_metric_plan:
            logger.info(f"Using deterministic metric ranking plan: {direct_metric_plan}")
            sql, params = build_sql(direct_metric_plan, community_id)
            result = run_query(sql, params)

            if not result:
                return {
                    "query": query,
                    "plan": direct_metric_plan,
                    "sql": sql,
                    "result": result,
                    "answer": _format_empty_metric_ranking_answer(direct_metric_plan),
                }

            answer = _format_metric_ranking_answer(query, direct_metric_plan, result) or ask_llm(
                f"User Query: {query}\nRetrieved Database Data: {result}\nProfessional Summary:",
                system_prompt=_SYNTHESIS_SYSTEM_PROMPT,
                num_predict=_SYNTHESIS_MAX_TOKENS,
            )

            return {
                "query": query,
                "plan": direct_metric_plan,
                "sql": sql,
                "result": result,
                "answer": answer,
            }

        # MACRO BYPASS: Handle complex multi-metric care analytics deterministically.
        if _is_care_assessment_query(query):
            logger.info("Executing deterministic care assessment macro...")
            return _run_care_assessment(query, community_id)

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
        sql, params = build_sql(plan, community_id)
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
            num_predict=_SYNTHESIS_MAX_TOKENS,
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
