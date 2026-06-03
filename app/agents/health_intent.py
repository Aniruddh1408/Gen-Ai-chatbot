# ===========================================================================
# This file helps the assistant understand free-form health questions. It uses
# one AI call to read a question like "did Anil sleep worse last week?" and turn
# it into a tidy checklist (which resident, which metric, which dates). That
# checklist then drives the safe, fixed database queries. If anything goes
# wrong, it quietly gives up so the simpler keyword matching can take over.
# ===========================================================================
"""LLM-backed intent extraction for resident health-data questions.

The deterministic sensor handlers in ``app/retrievers/_sql/sensors.py`` recognise
intent with regexes, which can only match phrasings someone enumerated. This
module adds a flexible understanding layer: one LLM call turns a free-text
health question into a small, validated spec (domain + resident + time window +
comparison + date). The spec then drives the SAME deterministic,
community-scoped SQL builders, so we gain phrasing-robustness without giving up
safety or grounding (the LLM never writes SQL or invents resident data — it only
fills slots, and resident names are re-checked against the roster downstream).

Fail-safe by design: any problem (LLM unreachable, timeout, malformed JSON,
unexpected values) returns ``None``, and the caller falls back to the regex
handlers. That keeps the system working offline and keeps the existing tests
deterministic.
"""
from __future__ import annotations

import datetime
import json

from app.core.logger import get_logger

logger = get_logger("health_intent")

# The domains that map onto a deterministic sensor builder. "unsupported" is a
# routing signal (not a builder): the question asks for a metric KuboCare does
# not measure, and is handed to the existing honest "not tracked" handler.
DOMAINS = ("sleep", "vitals", "wellness", "incidents", "holistic", "unsupported")
_COMPARISONS = ("least", "most", "trend")

# Intent extraction is on the hot path for every health question, so cap it
# tightly: a healthy server answers this small JSON call in ~1s; if it can't,
# we'd rather fall back to the regex handlers than make the user wait.
_INTENT_TIMEOUT_SECONDS = 8.0


def _system_prompt(today: str) -> str:
    return (
        "You extract the intent of a question about an elderly-care resident's "
        f"health-monitoring data. Today is {today}.\n\n"
        "Return ONLY one JSON object (no prose, no markdown) with these fields:\n"
        '- "domain": one of "sleep", "vitals", "wellness", "incidents", '
        '"holistic", "unsupported", or null if the question is NOT about '
        "resident health-monitoring data.\n"
        "    sleep = how a resident slept (duration, stages, a specific night, "
        "or a comparison across nights).\n"
        "    vitals = heart rate / respiration / pulse readings.\n"
        "    wellness = wellness scores (sleep/activity/vitals/environment).\n"
        "    incidents = falls, fall alerts, out-of-bed/out-of-room events, "
        "alerts or notifications.\n"
        "    holistic = an overall 'how is X doing / is X okay / does X need "
        "care' summary.\n"
        "    unsupported = asks for a metric KuboCare does NOT measure: blood "
        "pressure/BP, blood sugar/glucose, cholesterol, weight/BMI, oxygen/"
        "SpO2, body temperature, or medications/doses.\n"
        '- "resident": the resident name exactly as written, or null.\n'
        '- "comparison": "least" (worst/lowest/fewest/shortest), "most" '
        "(best/highest/longest), \"trend\" (history/list across days/compare/"
        'each night), or null. Only for sleep/vitals/wellness.\n'
        '- "window_days": integer number of days the question spans, or null. '
        'Map "a week"/"this week"/"last week"/"past week"=7, "two weeks"/'
        '"fortnight"=14, "a month"/"this month"=30; "15 days"->15, "last 10 '
        'days"->10. Leave null if no clear span is given.\n'
        '- "relative_days_ago": integer for a SINGLE day named relative to '
        'today — "today"=0, "yesterday"/"last night"=1, "3 days ago"=3 — else '
        "null. Do NOT compute a calendar date yourself; just give the integer.\n"
        '- "date": ONLY for an explicit calendar date like "May 30" or '
        '"2026-05-12", as "YYYY-MM-DD"; else null.\n'
        '- "active_only": true only if the question asks for unresolved/open/'
        "active/in-progress events (incidents only), else false.\n"
        '- "falls_only": true only if the question is specifically about falls '
        "rather than all incidents (incidents only), else false.\n\n"
        "Examples:\n"
        'Q: "give sleep data of 1 week of anil sharma" -> '
        '{"domain":"sleep","resident":"anil sharma","comparison":"trend",'
        '"window_days":7,"relative_days_ago":null,"date":null,'
        '"active_only":false,"falls_only":false}\n'
        'Q: "meera worst sleep in the last week" -> '
        '{"domain":"sleep","resident":"meera","comparison":"least",'
        '"window_days":7,"relative_days_ago":null,"date":null,'
        '"active_only":false,"falls_only":false}\n'
        'Q: "how did ravi sleep 3 days ago" -> '
        '{"domain":"sleep","resident":"ravi","comparison":null,'
        '"window_days":null,"relative_days_ago":3,"date":null,'
        '"active_only":false,"falls_only":false}\n'
        'Q: "whats anils blood pressure" -> '
        '{"domain":"unsupported","resident":"anil","comparison":null,'
        '"window_days":null,"relative_days_ago":null,"date":null,'
        '"active_only":false,"falls_only":false}\n'
        'Q: "any unresolved falls this month" -> '
        '{"domain":"incidents","resident":null,"comparison":null,'
        '"window_days":30,"relative_days_ago":null,"date":null,'
        '"active_only":true,"falls_only":true}'
    )


def _coerce(spec: dict) -> dict | None:
    """Validate and normalise the raw LLM JSON into a safe spec, or None."""
    if not isinstance(spec, dict):
        return None
    domain = spec.get("domain")
    if domain not in DOMAINS:
        return None  # not a health-data question we can serve deterministically

    resident = spec.get("resident")
    if resident is not None and not isinstance(resident, str):
        resident = None
    resident = resident.strip() if isinstance(resident, str) and resident.strip() else None

    comparison = spec.get("comparison")
    if comparison not in _COMPARISONS:
        comparison = None

    window_days = spec.get("window_days")
    if isinstance(window_days, bool) or not isinstance(window_days, int) or window_days <= 0:
        window_days = None

    relative_days_ago = spec.get("relative_days_ago")
    if (
        isinstance(relative_days_ago, bool)
        or not isinstance(relative_days_ago, int)
        or relative_days_ago < 0
        or relative_days_ago > 3650
    ):
        relative_days_ago = None

    date = spec.get("date")
    parsed_date = None
    if isinstance(date, str):
        try:
            parsed_date = datetime.date.fromisoformat(date.strip())
        except ValueError:
            parsed_date = None

    return {
        "domain": domain,
        "resident": resident,
        "comparison": comparison,
        "window_days": window_days,
        "relative_days_ago": relative_days_ago,
        "date": parsed_date,
        "active_only": bool(spec.get("active_only")),
        "falls_only": bool(spec.get("falls_only")),
    }


def _resolve_dates(spec: dict, today: datetime.date) -> dict:
    """Turn the model's relative/explicit date hints into a concrete past date.

    The model only ever returns an integer offset (``relative_days_ago``) — the
    calendar arithmetic happens HERE, in Python, because 7B models are
    unreliable at it. An explicit calendar date that lands in the future is
    almost always a model mistake (wrong month/year), so we drop it rather than
    answer the wrong night.
    """
    rel = spec.get("relative_days_ago")
    if rel is not None:
        spec["date"] = today - datetime.timedelta(days=rel)
    elif spec.get("date") and spec["date"] > today:
        spec["date"] = None
    return spec


def extract_health_intent(query: str) -> dict | None:
    """Return a validated health-intent spec for ``query``, or None.

    None means "couldn't understand this as a health-data question" OR "the LLM
    was unavailable" — both cases let the caller fall back to the regex
    handlers, so this can only ever ADD understanding, never remove it.
    """
    try:
        from app.llm.client import ask_with_messages

        today = datetime.date.today().isoformat()
        raw = ask_with_messages(
            _system_prompt(today),
            query,
            response_format="json",
            num_predict=160,
            temperature=0.0,
            timeout=_INTENT_TIMEOUT_SECONDS,
        )
        spec = json.loads(raw)
    except Exception as exc:  # noqa: BLE001 — fail safe on any LLM/parse error
        logger.info(f"health-intent extraction unavailable: {type(exc).__name__}")
        return None

    coerced = _coerce(spec)
    if coerced is not None:
        coerced = _resolve_dates(coerced, datetime.date.today())
        logger.info(f"health-intent spec: {coerced}")
    return coerced
