"""Keyword, regex-pattern, and rule-table constants for sql_retriever.

Pure data only (no DB/LLM). Moved verbatim out of sql_retriever.py; re-exported
there via star import so existing references keep working unchanged.
"""
from app.core.community import LOCAL_DEMO_COMMUNITIES


__all__ = [
    "_RESIDENT_PROFILE_RULES",
    "_RESIDENT_LIST_PATTERNS",
    "_RESIDENT_LIST_METRIC_TERMS",
    "_RESIDENT_COLLECTION_TERMS",
    "_RANKING_TERMS",
    "_NON_RESIDENT_NAME_CANDIDATES",
    "_KNOWN_COMMUNITY_NAMES",
    "_METRIC_RANKING_RULES",
    "_RESIDENT_AVERAGE_METRIC_RULES",
    "_DEVICE_METRIC_LABELS",
    "_DEVICE_SIGNAL_REVIEW_THRESHOLD",
    "_DEVICE_UPTIME_REVIEW_THRESHOLD",
    "_DEVICE_CPU_REVIEW_THRESHOLD",
    "_DEVICE_ISSUE_WORDS",
    "_DEVICE_ISSUE_PHRASES",
    "_NAMED_RESIDENT_METRIC_TERMS",
    "_CARE_ASSESSMENT_KEYWORDS",
    "_LOW_RISK_CARE_PHRASES",
    "_HIGH_RISK_CARE_PHRASES",
    "_HEALTHIEST_CARE_PHRASES",
    "_UNHEALTHY_CARE_PHRASES",
    "_BROAD_CARE_PHRASES",
    "_SINGULAR_CARE_RANKING_PHRASES",
    "_ASC_RANKING_PATTERNS",
    "_DESC_RANKING_PATTERNS",
    "_ORDINAL_WORDS",
    "_NUMBER_WORDS",
    "_RESIDENT_NAME_STOPWORDS",
    "_RESIDENT_TEXT_SEARCH_RULES",
    "_THRESHOLD_PATTERNS",
    "_METRIC_THRESHOLD_RULES",
    "_QUALITATIVE_THRESHOLD_RULES",
    "_VISUAL_KEYWORDS",
]


_RESIDENT_PROFILE_RULES = [
    {
        "name": "age",
        "patterns": [r"\bage\b", r"\bages\b", r"\bhow old\b", r"\bold is\b", r"\bolder\b", r"\byounger\b"],
        "column": "residents.name, residents.age",
    },
    {
        "name": "flat_no",
        "patterns": [
            r"\bflat\b",
            r"\bflats\b",
            r"\bflat no\b",
            r"\bflat number\b",
            r"\broom\b",
            r"\brooms\b",
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
        "patterns": [r"\bprescribed\b", r"\bintake\b", r"\bmedication\b", r"\bmedications\b", r"\btreatment plan\b"],
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
    "health",
    "metric",
    "metrics",
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
    "eldest",
    "youngest",
    "runner-up",
    "runner up",
}

_NON_RESIDENT_NAME_CANDIDATES = {
    "oldest",
    "eldest",
    "youngest",
    "the oldest",
    "the eldest",
    "the youngest",
}
_KNOWN_COMMUNITY_NAMES = {
    name.lower()
    for name in LOCAL_DEMO_COMMUNITIES.values()
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
        WITH scoped_health AS (
            SELECT h.resident_id, h.sugar_level, h.recorded_at
            FROM health_reports h
            JOIN residents r ON r.id = h.resident_id
            WHERE r.community_id = %s
        ),
        health_window AS (
            SELECT *
            FROM scoped_health
            WHERE recorded_at::date >= (
                SELECT MAX(recorded_at)::date
                FROM scoped_health
            ) - INTERVAL '19 days'
        )
        SELECT ROUND(AVG(sugar_level)::numeric, 1)
        FROM health_window;
        """,
        "label": "sugar level",
        "suffix": "",
    },
    {
        "metric": "steps",
        "patterns": [r"\bsteps\b", r"\bstep count\b", r"\bstep counts\b", r"\bactivity\b"],
        "sql": """
        WITH scoped_activity AS (
            SELECT a.resident_id, a.steps_count, a.recorded_at
            FROM activity_metrics a
            JOIN residents r ON r.id = a.resident_id
            WHERE r.community_id = %s
        ),
        activity_window AS (
            SELECT *
            FROM scoped_activity
            WHERE recorded_at::date >= (
                SELECT MAX(recorded_at)::date
                FROM scoped_activity
            ) - INTERVAL '19 days'
        )
        SELECT ROUND(AVG(steps_count)::numeric, 1)
        FROM activity_window;
        """,
        "label": "step count",
        "suffix": " steps",
    },
    {
        "metric": "sleep_duration",
        "patterns": [r"\bsleep duration\b", r"\bsleep time\b", r"\bslept\b"],
        "sql": """
        WITH scoped_sleep AS (
            SELECT s.resident_id, s.sleep_duration_minutes, s.recorded_at
            FROM sleep_analytics s
            JOIN residents r ON r.id = s.resident_id
            WHERE r.community_id = %s
        ),
        sleep_window AS (
            SELECT *
            FROM scoped_sleep
            WHERE recorded_at::date >= (
                SELECT MAX(recorded_at)::date
                FROM scoped_sleep
            ) - INTERVAL '19 days'
        )
        SELECT ROUND(AVG(sleep_duration_minutes)::numeric, 1)
        FROM sleep_window;
        """,
        "label": "sleep duration",
        "suffix": " minutes",
    },
    {
        "metric": "sleep_quality",
        "patterns": [r"\bsleep score\b", r"\bsleep scores\b", r"\bsleep quality\b"],
        "sql": """
        WITH scoped_sleep AS (
            SELECT s.resident_id, s.sleep_quality_score, s.recorded_at
            FROM sleep_analytics s
            JOIN residents r ON r.id = s.resident_id
            WHERE r.community_id = %s
        ),
        sleep_window AS (
            SELECT *
            FROM scoped_sleep
            WHERE recorded_at::date >= (
                SELECT MAX(recorded_at)::date
                FROM scoped_sleep
            ) - INTERVAL '19 days'
        )
        SELECT ROUND(AVG(sleep_quality_score)::numeric, 1)
        FROM sleep_window;
        """,
        "label": "sleep score",
        "suffix": "",
    },
    {
        "metric": "bp",
        "patterns": [r"\bbp\b", r"\bblood pressure\b"],
        "sql": """
        WITH scoped_health AS (
            SELECT h.resident_id, h.bp_systolic, h.bp_diastolic, h.recorded_at
            FROM health_reports h
            JOIN residents r ON r.id = h.resident_id
            WHERE r.community_id = %s
        ),
        health_window AS (
            SELECT *
            FROM scoped_health
            WHERE recorded_at::date >= (
                SELECT MAX(recorded_at)::date
                FROM scoped_health
            ) - INTERVAL '19 days'
        )
        SELECT
            ROUND(AVG(bp_systolic)::numeric, 1),
            ROUND(AVG(bp_diastolic)::numeric, 1)
        FROM health_window;
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

_DEVICE_SIGNAL_REVIEW_THRESHOLD = -75.0
_DEVICE_UPTIME_REVIEW_THRESHOLD = 95.0
_DEVICE_CPU_REVIEW_THRESHOLD = 50.0

_DEVICE_ISSUE_WORDS = [
    "issue",
    "issues",
    "problem",
    "problems",
    "fault",
    "faulty",
    "error",
    "errors",
    "offline",
    "down",
    "broken",
    "unstable",
    "degraded",
    "alert",
    "alerts",
    "anomaly",
    "anomalies",
    "concerning",
    "bad",
    "poor",
]

_DEVICE_ISSUE_PHRASES = [
    "not working",
    "not responding",
    "has issues",
    "have issues",
    "having issues",
    "has a problem",
    "have a problem",
    "acting up",
]

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
    "health status",
    "health condition",
    "wellness status",
    "health metrics",
    "all metrics",
    "comprehensive",
    "needs care",
    "need care",
    "needing care",
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
    "needing care",
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

_SINGULAR_CARE_RANKING_PHRASES = [
    "most care",
    "most acre",
    "requires most care",
    "requires most acre",
    "highest care",
    "highest priority",
    "highest risk",
    "most at risk",
    "least care",
    "least acre",
    "requires least care",
    "requires least acre",
    "lowest care",
    "lowest priority",
    "least priority",
    "lowest risk",
    "least risk",
    "healthiest",
    "most healthy",
    "best health",
    "best overall health",
    "most stable",
    "unhealthiest",
    "most unhealthy",
    "least healthy",
    "worst health",
    "poorest health",
    "poor health",
    "least stable",
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

_RESIDENT_NAME_STOPWORDS = {
    "resident", "residents", "patient", "patients", "community", "this", "that",
    "these", "those", "all", "their", "his", "her", "him", "them", "who",
    "what", "which", "where", "when", "why", "how", "is", "are", "was",
    "were", "the", "a", "an", "has", "have", "with",
    "and", "or",
    "list", "show", "display", "give", "get", "tell", "on", "takes", "taking",
    "me", "my", "find", "see", "check",
    "above", "below", "over", "under", "less", "more", "greater", "fewer",
    "medical", "history", "medication", "prescribed", "details", "room",
    "rooms", "flat", "flats", "age", "ages",
    "bp", "blood", "pressure", "sugar", "glucose", "level", "levels",
    "steps", "step", "sleep", "score", "scores", "quality", "duration",
    "chart", "graph", "pie", "bar", "line",
}

_RESIDENT_TEXT_SEARCH_RULES = [
    {
        "label": "hypertension",
        "patterns": [r"\bhypertension\b"],
        "columns": ["r.health_medical_history"],
        "terms": ["hypertension"],
    },
    {
        "label": "diabetes",
        "patterns": [r"\bdiabetes\b", r"\btype\s+2\s+diabetes\b"],
        "columns": ["r.health_medical_history"],
        "terms": ["diabetes"],
        "exclude_terms": ["pre-diabetes", "prediabetes"],
    },
    {
        "label": "pre-diabetes",
        "patterns": [r"\bpre[-\s]?diabetes\b", r"\bprediabetes\b"],
        "columns": ["r.health_medical_history"],
        "terms": ["pre-diabetes", "prediabetes"],
    },
    {
        "label": "arthritis",
        "patterns": [r"\barthritis\b", r"\bjoint pain\b"],
        "columns": ["r.health_medical_history"],
        "terms": ["arthritis", "joint pain"],
    },
    {
        "label": "asthma",
        "patterns": [r"\basthma\b"],
        "columns": ["r.health_medical_history"],
        "terms": ["asthma"],
    },
    {
        "label": "cardiac or cardiovascular history",
        "patterns": [r"\bcardiac\b", r"\bcardiovascular\b", r"\bheart\b"],
        "columns": ["r.health_medical_history"],
        "terms": ["cardiac", "cardiovascular"],
    },
    {
        "label": "osteoporosis",
        "patterns": [r"\bosteoporosis\b"],
        "columns": ["r.health_medical_history"],
        "terms": ["osteoporosis"],
    },
    {
        "label": "thyroid disorder",
        "patterns": [r"\bthyroid\b"],
        "columns": ["r.health_medical_history"],
        "terms": ["thyroid"],
    },
    {
        "label": "post-surgery support",
        "patterns": [r"\bpost[-\s]?surgery\b", r"\bsurgery\b", r"\bmobility support\b"],
        "columns": ["r.health_medical_history"],
        "terms": ["post-surgery", "post surgery", "mobility support"],
    },
    {
        "label": "Metformin",
        "patterns": [r"\bmetformin\b"],
        "columns": ["r.medical_intake_prescribed"],
        "terms": ["metformin"],
    },
    {
        "label": "Amlodipine",
        "patterns": [r"\bamlodipine\b"],
        "columns": ["r.medical_intake_prescribed"],
        "terms": ["amlodipine"],
    },
    {
        "label": "Atorvastatin",
        "patterns": [r"\batorvastatin\b"],
        "columns": ["r.medical_intake_prescribed"],
        "terms": ["atorvastatin"],
    },
    {
        "label": "Calcium or Vitamin D",
        "patterns": [r"\bcalcium\b", r"\bvitamin\s+d\b"],
        "columns": ["r.medical_intake_prescribed"],
        "terms": ["calcium", "vitamin d"],
    },
    {
        "label": "Levothyroxine",
        "patterns": [r"\blevothyroxine\b"],
        "columns": ["r.medical_intake_prescribed"],
        "terms": ["levothyroxine"],
    },
    {
        "label": "Salbutamol inhaler",
        "patterns": [r"\bsalbutamol\b", r"\binhaler\b"],
        "columns": ["r.medical_intake_prescribed"],
        "terms": ["salbutamol", "inhaler"],
    },
    {
        "label": "Paracetamol",
        "patterns": [r"\bparacetamol\b"],
        "columns": ["r.medical_intake_prescribed"],
        "terms": ["paracetamol"],
    },
    {
        "label": "Telmisartan",
        "patterns": [r"\btelmisartan\b"],
        "columns": ["r.medical_intake_prescribed"],
        "terms": ["telmisartan"],
    },
    {
        "label": "Aspirin",
        "patterns": [r"\baspirin\b"],
        "columns": ["r.medical_intake_prescribed"],
        "terms": ["aspirin"],
    },
    {
        "label": "diet and exercise plan",
        "patterns": [r"\bdiet\b", r"\bexercise plan\b", r"\blifestyle monitoring\b"],
        "columns": ["r.health_medical_history", "r.medical_intake_prescribed"],
        "terms": ["diet", "exercise plan", "lifestyle monitoring"],
    },
    {
        "label": "no major chronic illness",
        "patterns": [r"\bno major chronic illness\b", r"\bno major illness\b"],
        "columns": ["r.health_medical_history"],
        "terms": ["no major chronic illness", "no major illness"],
    },
]

_THRESHOLD_PATTERNS = [
    (r"\b(?:above|over|greater\s+than|more\s+than|higher\s+than)\s+(\d+(?:\.\d+)?)\b", ">", "above"),
    (r"\b(?:at\s+least|minimum|min)\s+(\d+(?:\.\d+)?)\b", ">=", "at least"),
    (r"\b(?:below|under|less\s+than|fewer\s+than|lower\s+than)\s+(\d+(?:\.\d+)?)\b", "<", "below"),
    (r"\b(?:at\s+most|maximum|max|no\s+more\s+than)\s+(\d+(?:\.\d+)?)\b", "<=", "at most"),
]

_METRIC_THRESHOLD_RULES = [
    {
        "metric": "sleep_quality",
        "patterns": [r"\bsleep score\b", r"\bsleep quality\b", r"\bsleep quality score\b"],
        "label": "sleep quality score",
        "kind": "sleep",
        "column": "s.sleep_quality_score",
        "value_column": "s.sleep_quality_score",
        "unit": "",
    },
    {
        "metric": "sleep_duration",
        "patterns": [r"\bslept\b", r"\bsleep duration\b", r"\bsleep time\b", r"\bminutes\b"],
        "label": "sleep duration",
        "kind": "sleep",
        "column": "s.sleep_duration_minutes",
        "value_column": "s.sleep_duration_minutes",
        "unit": " minutes",
    },
    {
        "metric": "bp",
        "patterns": [r"\bbp\b", r"\bblood pressure\b", r"\bsystolic\b"],
        "label": "systolic blood pressure",
        "kind": "health",
        "column": "h.bp_systolic",
        "value_column": "h.bp_systolic",
        "unit": " mmHg",
    },
    {
        "metric": "sugar",
        "patterns": [r"\bsugar\b", r"\bglucose\b"],
        "label": "sugar level",
        "kind": "health",
        "column": "h.sugar_level",
        "value_column": "h.sugar_level",
        "unit": "",
    },
    {
        "metric": "steps",
        "patterns": [r"\bsteps\b", r"\bstep count\b", r"\bwalked\b", r"\bwalking\b"],
        "label": "step count",
        "kind": "activity",
        "column": "a.steps_count",
        "value_column": "a.steps_count",
        "unit": " steps",
    },
    {
        "metric": "age",
        "patterns": [r"\bage\b", r"\bold\b"],
        "label": "age",
        "kind": "resident",
        "column": "r.age",
        "value_column": "r.age",
        "unit": " years",
    },
]

_QUALITATIVE_THRESHOLD_RULES = [
    {
        "patterns": [r"\b(?:high|elevated|raised)\s+(?:bp|blood pressure)\b", r"\b(?:bp|blood pressure)\s+(?:is\s+)?(?:high|elevated|raised)\b"],
        "plan": {
            "metric": "bp",
            "label": "high blood pressure",
            "kind": "health",
            "column": "h.bp_systolic",
            "value_column": "h.bp_systolic",
            "operator": ">=",
            "value": 140,
            "unit": " mmHg",
            "bp_any_thresholds": [("h.bp_systolic", 140), ("h.bp_diastolic", 90)],
            "comparison_text": "high blood pressure (systolic >= 140 or diastolic >= 90)",
        },
    },
    {
        "patterns": [r"\b(?:low)\s+(?:bp|blood pressure)\b", r"\b(?:bp|blood pressure)\s+(?:is\s+)?low\b"],
        "plan": {
            "metric": "bp",
            "label": "low blood pressure",
            "kind": "health",
            "column": "h.bp_systolic",
            "value_column": "h.bp_systolic",
            "operator": "<",
            "value": 90,
            "unit": " mmHg",
            "bp_any_thresholds": [("h.bp_systolic", 90), ("h.bp_diastolic", 60)],
            "comparison_text": "low blood pressure (systolic < 90 or diastolic < 60)",
        },
    },
    {
        "patterns": [r"\b(?:high|elevated|raised)\s+(?:sugar|glucose)\b", r"\b(?:sugar|glucose)\s+(?:is\s+)?(?:high|elevated|raised)\b"],
        "plan": {
            "metric": "sugar",
            "label": "sugar level",
            "kind": "health",
            "column": "h.sugar_level",
            "value_column": "h.sugar_level",
            "operator": ">=",
            "value": 140,
            "unit": "",
        },
    },
    {
        "patterns": [r"\b(?:low|poor)\s+(?:sleep score|sleep quality|sleep quality score)\b"],
        "plan": {
            "metric": "sleep_quality",
            "label": "sleep quality score",
            "kind": "sleep",
            "column": "s.sleep_quality_score",
            "value_column": "s.sleep_quality_score",
            "operator": "<",
            "value": 50,
            "unit": "",
        },
    },
    {
        "patterns": [r"\b(?:low|poor)\s+(?:activity|steps|step count)\b", r"\b(?:inactive|low activity)\b"],
        "plan": {
            "metric": "steps",
            "label": "step count",
            "kind": "activity",
            "column": "a.steps_count",
            "value_column": "a.steps_count",
            "operator": "<",
            "value": 2500,
            "unit": " steps",
        },
    },
    {
        "patterns": [r"\b(?:short|low|reduced)\s+sleep(?:\s+duration|\s+time)?\b"],
        "plan": {
            "metric": "sleep_duration",
            "label": "sleep duration",
            "kind": "sleep",
            "column": "s.sleep_duration_minutes",
            "value_column": "s.sleep_duration_minutes",
            "operator": "<",
            "value": 360,
            "unit": " minutes",
        },
    },
]

_VISUAL_KEYWORDS = ["chart", "graph", "plot", "visualize", "visualization", "show stats", "comparison", "pie", "bar chart", "line graph", "doughnut", "donut"]
