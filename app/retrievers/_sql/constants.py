"""Keyword, regex-pattern, and rule-table constants for sql_retriever.

Pure data only (no DB/LLM). Re-exported through sql_retriever via star import
so existing references keep working.

# Scope note
This module is scoped to the **core seeded entities only**: organisation,
community, community_user_mapping, roles, users, rooms, objects,
resident_profile, room_resident_mapping. Resident-side queries (profile
lookups, lists, age, medical-history text search, count / oldest / youngest)
all live in this set.

Vitals, sleep_sessions, wellness_metrics, activity_log and other sensor /
metric tables are NOT touched here. When that data is seeded later, this
file will grow back to include their rule tables — but anything that doesn't
have a real backing column in the production schema stays out.
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
    "_ASC_RANKING_PATTERNS",
    "_DESC_RANKING_PATTERNS",
    "_ORDINAL_WORDS",
    "_NUMBER_WORDS",
    "_RESIDENT_NAME_STOPWORDS",
    "_RESIDENT_TEXT_SEARCH_RULES",
    "_VISUAL_KEYWORDS",
]


# Computing age inline avoids storing it (it would drift). dob is text in the
# production schema (per data/schema.sql), so it's cast to date first.
#
# AGE() with one argument uses CURRENT_DATE implicitly — same result as the
# two-argument form, but no comma INSIDE the function call. The plan-identifier
# safety validator splits the projection on commas to validate each column;
# any comma inside a function call would split mid-expression and fail.
_AGE_FROM_DOB_SQL = (
    "EXTRACT(YEAR FROM AGE(resident_profile.dob::date))::int"
)


_RESIDENT_PROFILE_RULES = [
    {
        "name": "age",
        "patterns": [
            r"\bage\b", r"\bages\b", r"\bhow old\b",
            r"\bold is\b", r"\bolder\b", r"\byounger\b",
        ],
        # Computed expression aliased as 'age' so formatters can refer to it
        # like a real column.
        "column": f"resident_profile.name, {_AGE_FROM_DOB_SQL} AS age",
    },
    {
        "name": "flat_number",
        "patterns": [
            r"\bflat\b", r"\bflats\b", r"\bflat no\b", r"\bflat number\b",
            r"\broom\b", r"\brooms\b",
            r"\bwhere\s+(?:does|is)\b",
            r"\bstay\b", r"\bstaying\b", r"\blive\b", r"\bliving\b",
            r"\bassigned\b",
        ],
        "column": "resident_profile.name, resident_profile.flat_number",
    },
    {
        "name": "medical_history",
        "patterns": [r"\bmedical history\b", r"\bhealth history\b", r"\bhistory\b"],
        "column": "resident_profile.name, resident_profile.medical_history",
    },
    {
        "name": "details",
        "patterns": [
            r"\bdetails?\b", r"\binfo\b", r"\binformation\b", r"\bprofile\b",
            r"\btell\s+me\s+about\b", r"\bwho\s+is\b",
        ],
        "column": (
            "resident_profile.name, resident_profile.id, "
            "resident_profile.flat_number, "
            f"{_AGE_FROM_DOB_SQL} AS age, "
            "resident_profile.medical_history"
        ),
    },
    {
        "name": "name",
        "patterns": [r"\bname\b"],
        "column": "resident_profile.name, resident_profile.id",
    },
]


_RESIDENT_LIST_PATTERNS = [
    r"\b(?:list|show|display|get)\b(?:\s+me)?(?:\s+the)?(?:\s+all)?\s+(?:residents|patients)\b",
    r"\bgive\s+me\s+(?:the\s+)?list\s+of\s+(?:the\s+)?(?:residents|patients)\b",
    r"\b(?:list|show|display|get)\b(?:\s+me)?(?:\s+the)?\s+list\s+of\s+(?:the\s+)?(?:residents|patients)\b",
    r"\b(?:the\s+)?list\s+of\s+(?:the\s+)?(?:residents|patients)\b",
    r"\bwho\s+are\s+(?:the\s+)?(?:residents|patients)\b",
]


# Words that mean "user wants per-resident output beyond just names". The
# resident-list handler bails when one of these is present so the more
# specific collection-profile / metric handlers can fire instead.
_RESIDENT_LIST_METRIC_TERMS = {
    "age", "ages", "old", "flat", "flats", "room", "rooms",
    "medical", "history", "histories", "detail", "details", "health",
    "highest", "lowest", "best", "worst", "top", "bottom",
}

_RESIDENT_COLLECTION_TERMS = {
    "residents", "patients", "they", "them", "their", "theirs", "these", "those",
}

_RANKING_TERMS = {
    "best", "worst", "highest", "lowest", "top", "bottom",
    "most", "least", "fewest", "oldest", "eldest", "youngest",
    "runner-up", "runner up",
}

_NON_RESIDENT_NAME_CANDIDATES = {
    "oldest", "eldest", "youngest",
    "the oldest", "the eldest", "the youngest",
}

_KNOWN_COMMUNITY_NAMES = {
    name.lower() for name in LOCAL_DEMO_COMMUNITIES.values()
}


_ASC_RANKING_PATTERNS = [
    r"\bworst\b", r"\blowest\b", r"\bleast\b", r"\bfewest\b",
    r"\bbottom\b", r"\bshortest\b",
]

_DESC_RANKING_PATTERNS = [
    r"\bbest\b", r"\bhighest\b", r"\bmost\b", r"\btop\b",
    r"\blongest\b", r"\brunner[-\s]?up\b",
]

_ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


# Stopwords kept broad so the name extractor doesn't confuse metric words
# (bp / sugar / steps / sleep) with resident names even though those metrics
# aren't queryable yet — protects forward compatibility when vitals land.
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


# Medical-condition text search against resident_profile.medical_history.
# Drug-name rules (metformin / amlodipine / etc.) were dropped because the
# production schema has no medical_intake_prescribed column — those queries
# fall through to the LLM SQL planner.
_RESIDENT_TEXT_SEARCH_RULES = [
    {
        "label": "hypertension",
        "patterns": [r"\bhypertension\b"],
        "columns": ["resident_profile.medical_history"],
        "terms": ["hypertension"],
    },
    {
        "label": "diabetes",
        "patterns": [r"\bdiabetes\b", r"\btype\s+2\s+diabetes\b"],
        "columns": ["resident_profile.medical_history"],
        "terms": ["diabetes"],
        "exclude_terms": ["pre-diabetes", "prediabetes"],
    },
    {
        "label": "pre-diabetes",
        "patterns": [r"\bpre[-\s]?diabetes\b", r"\bprediabetes\b"],
        "columns": ["resident_profile.medical_history"],
        "terms": ["pre-diabetes", "prediabetes"],
    },
    {
        "label": "arthritis",
        "patterns": [r"\barthritis\b", r"\bjoint pain\b"],
        "columns": ["resident_profile.medical_history"],
        "terms": ["arthritis", "joint pain"],
    },
    {
        "label": "asthma",
        "patterns": [r"\basthma\b"],
        "columns": ["resident_profile.medical_history"],
        "terms": ["asthma"],
    },
    {
        "label": "cardiac or cardiovascular history",
        "patterns": [r"\bcardiac\b", r"\bcardiovascular\b", r"\bheart\b"],
        "columns": ["resident_profile.medical_history"],
        "terms": ["cardiac", "cardiovascular"],
    },
    {
        "label": "osteoporosis",
        "patterns": [r"\bosteoporosis\b"],
        "columns": ["resident_profile.medical_history"],
        "terms": ["osteoporosis"],
    },
    {
        "label": "thyroid disorder",
        "patterns": [r"\bthyroid\b"],
        "columns": ["resident_profile.medical_history"],
        "terms": ["thyroid"],
    },
    {
        "label": "post-surgery support",
        "patterns": [r"\bpost[-\s]?surgery\b", r"\bsurgery\b", r"\bmobility support\b"],
        "columns": ["resident_profile.medical_history"],
        "terms": ["post-surgery", "post surgery", "mobility support"],
    },
    {
        "label": "no major chronic illness",
        "patterns": [r"\bno major chronic illness\b", r"\bno major illness\b"],
        "columns": ["resident_profile.medical_history"],
        "terms": ["no major chronic illness", "no major illness"],
    },
]


# Chart-trigger keywords are still checked in handle_sql's tail. Visual
# output is not tied to any metric table; keeping these lets the LLM
# planner's chart-aware path work once metric data is seeded.
_VISUAL_KEYWORDS = [
    "chart", "graph", "plot", "visualize", "visualization",
    "show stats", "comparison", "pie", "bar chart", "line graph",
    "doughnut", "donut",
]
