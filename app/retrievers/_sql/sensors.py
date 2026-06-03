# ===========================================================================
# This file answers questions about a resident's day-to-day signals: falls and
# alerts, heart rate and breathing, last night's sleep, and wellness scores.
# It can answer for one named resident ("how did Anil sleep?") or for the whole
# community ("any falls this week?"), and it always sticks to the facts in the
# records. "How is X doing?" gets a short all-round summary.
# ===========================================================================
"""Deterministic SQL handlers for sensor / incident questions.

Why this module exists
----------------------
The LLM SQL planner can build incident/vitals/sleep/wellness queries in
principle (the schema lives in kubocare_schema.SCHEMA and includes the
canonical JOIN snippets). In practice it fails three predictable ways:

  1. Sometimes the planner remembers the legacy ``residents`` table name
     and emits ``residents.name`` — the safety validator (correctly)
     rejects it, the user sees a generic technical error.
  2. Sometimes it emits a sensor-table FROM with resident-side columns in
     the projection, but build_sql only knows how to add the
     resident_profile -> room chain; the sensor table stays unjoined,
     Postgres errors with "missing FROM-clause entry".
  3. Sometimes it filters ``board = 'Anil Sharma'`` — board is an opaque
     OBJ-XXXXX device id, so the query returns zero rows and the user
     sees "no records found" even though the data exists.

Each of these failures destroys user trust in the system. The fix is the
same pattern the resident-profile rules use: deterministic detection +
hand-rolled, community-scoped SQL for the load-bearing question shapes,
falling through to the LLM planner only for genuinely off-script queries.

What's covered
--------------
- Fall / incident lookups (per-resident and community-wide)
- Active / unresolved alert lookups
- Vitals (heart rate, respiration rate) latest reading per resident
- Sleep session breakdown for the most recent night
- Wellness score (per-resident, all four types)

Every query is bound to the caller's community_id by adding a
rooms.community_id = %s predicate, defended on top by the safety
validator at the bottom of each builder. Resident-name filtering uses
ILIKE so partial inputs ("Anil") match canonical rows ("Anil Sharma").
"""
from __future__ import annotations

import re

from app.core.db import run_query
from app.core.logger import get_logger
from app.retrievers._sql.constants import _RESIDENT_NAME_STOPWORDS
from app.retrievers._sql.names import (
    _extract_excluded_resident_name,
    _extract_resident_id,
    _extract_resident_name,
)
from app.retrievers._sql.safety import _validate_read_only_sql
from app.retrievers._sql.screening import (
    classify_fall_pattern,
    classify_hr,
    classify_rr,
    classify_sleep_duration,
    classify_wellness_score,
    worst_band,
)

logger = get_logger("sql_retriever.sensors")


# ---------------------------------------------------------------------------
# JOIN chain snippets — encoded once so handlers all use the same shape and a
# schema change only needs one edit. These match the chains in
# kubocare_schema.CANONICAL_JOINS but are inlined as strings here so the SQL
# can be assembled without a templating layer.
#
# board -> objects -> rooms -> rrm -> resident_profile is the load-bearing
# sensor-side join. For incidents (no board, just room_id) we skip objects
# and join directly from rooms.
# ---------------------------------------------------------------------------

_BOARD_TO_RESIDENT_JOIN = (
    "JOIN objects o "
    "  ON o.object_id = {sensor}.board "
    " AND COALESCE(o.is_deleted, false) = false "
    "JOIN rooms r "
    "  ON r.id = o.room_id "
    " AND COALESCE(r.is_deleted, false) = false "
    "JOIN room_resident_mapping rrm "
    "  ON rrm.room_id = r.id "
    " AND COALESCE(rrm.is_deleted, false) = false "
    "JOIN resident_profile rp "
    "  ON rp.id = rrm.resident_id "
    " AND COALESCE(rp.is_deleted, false) = false"
)

_ROOM_TO_RESIDENT_JOIN = (
    "JOIN rooms r "
    "  ON r.id = {table}.room_id "
    " AND COALESCE(r.is_deleted, false) = false "
    "LEFT JOIN room_resident_mapping rrm "
    "  ON rrm.room_id = r.id "
    " AND COALESCE(rrm.is_deleted, false) = false "
    "LEFT JOIN resident_profile rp "
    "  ON rp.id = rrm.resident_id "
    " AND COALESCE(rp.is_deleted, false) = false"
)


# ---------------------------------------------------------------------------
# Pattern sets — keep these narrow. A pattern firing here commits the request
# to the sensor pipeline; anything ambiguous should be left for the router /
# LLM planner to handle.
# ---------------------------------------------------------------------------

# "fall", "fell", "fallen" → falls/incidents about falling specifically.
_FALL_TERM_RE = re.compile(r"\b(?:fall|falls|fell|fallen)\b", re.IGNORECASE)

# Any incident-shaped vocabulary (broader than falls — covers movement,
# out-of-bed, suspected alerts, etc).
_INCIDENT_TERM_RE = re.compile(
    r"\b(?:incident|incidents|alert|alerts|notification|notifications|"
    r"out\s+of\s+bed|out\s+of\s+room)\b",
    re.IGNORECASE,
)

# "active", "unresolved", "open", "in progress" — markers that the user
# wants only unresolved events (status = false).
_ACTIVE_ALERT_RE = re.compile(
    r"\b(?:active|unresolved|open|in[-\s]progress|ongoing|pending)\b",
    re.IGNORECASE,
)

# "Did X have a fall", "has X fallen", "did X fall" — phrasing that NAMES a
# specific resident. When the roster matcher can't resolve X, we should say
# "couldn't find that resident" rather than silently dump community-wide
# results — otherwise the user thinks Bruce Wayne is in the building.
#
# Case-insensitive so "did bruce wayne ..." also matches. The captured
# group is run through _RESIDENT_NAME_STOPWORDS in the handler before
# treating it as a resident name (filters out "anyone"/"the resident"/etc).
_NAMED_RESIDENT_FALL_RE = re.compile(
    r"\b(?:did|has|have|does)\s+(?:resident\s+|patient\s+)?"
    # Name capture — at most 3 tokens, but each subsequent token must NOT
    # be a structural keyword that would otherwise be greedily swallowed
    # (have/had/has/a/the/any/recently/lately). Without these guards the
    # regex grabs "Bruce Wayne have" instead of "Bruce Wayne".
    r"([a-z]+(?:\s+(?!(?:have|had|has|a|the|any|recently|lately)\b)[a-z]+){0,2})"
    r"\s+(?:have|had|has)?\s*(?:a\s+)?(?:fall|fallen|fell|incident)\b",
    re.IGNORECASE,
)

# Heart rate / respiration / vitals — restricted to vocabulary that
# unambiguously means "vitals time-series", not generic resident profile.
_VITALS_TERM_RE = re.compile(
    r"\b(?:heart\s+rate|hr|respiration(?:\s+rate)?|rr|pulse|vitals?|"
    r"vital\s+signs)\b",
    re.IGNORECASE,
)

# Sleep session — "how did X sleep", "X's sleep last night", etc.
_SLEEP_TERM_RE = re.compile(r"\b(?:sleep|slept|sleeping)\b", re.IGNORECASE)
_SLEEP_SESSION_RE = re.compile(
    r"\b(?:how\s+(?:did|does|is)|last\s+night|tonight|deep\s+sleep|"
    r"sleep\s+stage|sleep\s+stages|rem|sleep\s+breakdown|sleep\s+pattern)\b",
    re.IGNORECASE,
)
# Multi-night sleep questions. "less/least/worst" → the night with the LEAST
# sleep; "most/best/longest" → the MOST; trend/compare/"last week"/"each night"
# → list every night so a caregiver can compare across the window. Bare "how
# did X sleep" (no comparator) stays on the single most-recent-night path.
_SLEEP_LEAST_RE = re.compile(
    r"\b(?:less|least|worst|lowest|shortest|fewest|worse)\b", re.IGNORECASE
)
_SLEEP_MOST_RE = re.compile(
    r"\b(?:most|best|longest|highest|deepest|better)\b", re.IGNORECASE
)
_SLEEP_HISTORY_RE = re.compile(
    r"\b(?:trend|trends|history|each\s+night|every\s+night|all\s+(?:the\s+)?nights|"
    r"over\s+the\s+(?:last|past)|"
    # any "week"/"weeks" reference: "this/last/past/the/1/a/one/two/2/few/several
    # weeks", and bare "weekly"/"fortnight".
    r"(?:this|last|past|the|one|1|a|two|2|few|several|couple\s+of)\s+weeks?|"
    r"weekly|fortnight|"
    # explicit day spans: "7 days", "last 14 days", "15 days", etc.
    r"\d+\s+days|"
    r"compare|comparison|nightly|by\s+night)\b",
    re.IGNORECASE,
)

# Wellness aggregate score (wellness_metrics).
_WELLNESS_TERM_RE = re.compile(
    r"\b(?:wellness|well[-\s]being)\b",
    re.IGNORECASE,
)

# "when did X fall", "when was the fall", "what time / what day" — the user
# wants the timing of the event, not a yes/no confirmation. Drives a lead that
# states *when* rather than the default "Yes — X has N fall events" framing.
_WHEN_QUERY_RE = re.compile(
    r"\b(?:when|what\s+time|what\s+day|what\s+date)\b", re.IGNORECASE
)

# Time-window phrasing → INTERVAL the SQL filter should use.
_TIME_WINDOW_TODAY_RE = re.compile(r"\b(?:today|now|currently)\b", re.IGNORECASE)
_TIME_WINDOW_YESTERDAY_RE = re.compile(r"\b(?:yesterday|last\s+night|tonight)\b", re.IGNORECASE)
_TIME_WINDOW_MONTH_RE = re.compile(r"\b(?:this\s+month|last\s+month|past\s+month|30\s+days)\b", re.IGNORECASE)

# Explicit calendar dates the user might name ("sleep on May 30", "30 May",
# "2026-05-30"). Relative phrasing ("last night", "yesterday") is deliberately
# NOT handled here — those should keep falling through to the most-recent-night
# default. Only an explicit month+day / ISO date pins a specific night.
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_MONTH_NAMES_RE = (
    "jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|"
    "aug|august|sep|sept|september|oct|october|nov|november|dec|december"
)
_MONTH_DAY_RE = re.compile(
    rf"\b({_MONTH_NAMES_RE})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.IGNORECASE
)
_DAY_MONTH_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_NAMES_RE})\b", re.IGNORECASE
)
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")


def _resident_filter_value(name: str) -> str:
    """Strip possessive ``'s`` so ILIKE matches ``%Anil Sharma%``."""
    return name.replace("'s", "").replace("’s", "").strip()


# ---------------------------------------------------------------------------
# Formatting helpers — kept tiny so the per-handler formatters can focus on
# the prose. All times are rendered in the server's local timezone (the seed
# already uses now()-based offsets, so "today / yesterday" reads correctly).
# ---------------------------------------------------------------------------


def _plural(n: int, singular: str, plural: str | None = None) -> str:
    """`_plural(1, "fall event") → "1 fall event"`,
    `_plural(3, "fall event") → "3 fall events"`. Pass an explicit plural
    for irregular nouns (we don't need any yet but it's free to support)."""
    if n == 1:
        return f"{n} {singular}"
    return f"{n} {plural or singular + 's'}"


def _human_clock(ts) -> str:
    """Format a timestamp as "May 29 at 11:59 AM" — always explicit, since
    care staff scrolling logs later need the date even when the event was
    recent. Adds the year only when it isn't the current one."""
    if ts is None:
        return "an unknown time"
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc) if ts.tzinfo else datetime.now()
    clock = ts.strftime("%I:%M %p").lstrip("0")
    if ts.year == now.year:
        return f"{ts.strftime('%b')} {ts.day} at {clock}"
    return f"{ts.strftime('%b')} {ts.day}, {ts.year} at {clock}"


def _human_date(date) -> str:
    """Format a date as "May 29" — always explicit, with year only when it
    differs from the current one. No relative phrasing like "today" /
    "yesterday", since this is monitoring data."""
    if date is None:
        return "an unknown date"
    from datetime import datetime

    today = datetime.now().date()
    if date.year == today.year:
        return f"{date.strftime('%b')} {date.day}"
    return f"{date.strftime('%b')} {date.day}, {date.year}"


def _extract_target_date(query: str):
    """Pull an explicit calendar date out of the query, or return None.

    Accepts "May 30", "30 May", "30th of May", and ISO "2026-05-30". A
    bare month+day is assumed to be the most recent occurrence: this year,
    unless that date is still in the future (then last year). Relative words
    like "yesterday" / "last night" are intentionally not handled here.
    """
    from datetime import date, datetime

    iso = _ISO_DATE_RE.search(query)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None

    m = _MONTH_DAY_RE.search(query)
    if m:
        month, day = _MONTHS[m.group(1).lower()], int(m.group(2))
    else:
        m = _DAY_MONTH_RE.search(query)
        if not m:
            return None
        month, day = _MONTHS[m.group(2).lower()], int(m.group(1))

    today = datetime.now().date()
    for year in (today.year, today.year - 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None  # e.g. "February 30" — not a real date
        if candidate <= today:
            return candidate
    return None


def _resolve_resident_target(query: str, community_id: int) -> tuple[int | None, str | None]:
    """Return (resident_id, resident_name) for the resident named in the query.

    Resolution order:
      1. Explicit ``resident 7``/``patient id 7`` → numeric id via
         _extract_resident_id (no DB needed).
      2. Pattern-based name extraction (works for the canonical resident-
         profile phrasings: "how old is X", "tell me about X", "X's
         medication"). Returns name only.
      3. **Roster match** — load the community's resident names from the DB
         and look for any of them as a substring in the query. This is the
         load-bearing path for sensor questions like
         "Did Sunita Rao have a fall recently?" or "Anil's pulse" because
         the pattern-based extractor only fires for resident-profile-style
         phrasings.

    Returning a tuple (not just a name) lets handlers fast-path an id
    lookup when the user supplied one, and fall back to ILIKE-by-name
    otherwise.
    """
    resident_id = _extract_resident_id(query)
    if resident_id is not None:
        return resident_id, None

    resident_name = _extract_resident_name(query)
    if resident_name:
        return None, resident_name

    # Lazy import to break a cycle: sql_retriever already imports from
    # this module. The roster matcher only needs community_id and the
    # query text.
    from app.retrievers.sql_retriever import _find_resident_names_in_query

    matches = _find_resident_names_in_query(query, community_id)
    if matches:
        return None, matches[0]
    return None, None


def _has_resident_target(query: str, community_id: int) -> bool:
    """True when the query names a resident (by name or id). When False, the
    handlers fall back to community-wide aggregation (or return None so
    the LLM planner can try)."""
    rid, rname = _resolve_resident_target(query, community_id)
    return rid is not None or bool(rname)


# ===========================================================================
# Incidents / falls / alerts
# ===========================================================================


def _build_incidents_sql(
    query: str,
    community_id: int,
    resident_id: int | None,
    resident_name: str | None,
    exclude_name: str | None = None,
    *,
    interval: str | None = None,
    is_fall_query: bool | None = None,
    is_active_only: bool | None = None,
) -> tuple[str, list, dict]:
    """Build a community-scoped incidents query.

    Decisions encoded (each can be overridden by an explicit keyword arg, which
    the LLM-intent path uses; when an arg is None they're derived from the query
    text exactly as before):
      - "fall/fell/fallen" → restrict event_category to the three fall enums.
        Otherwise allow any event_category (the user said "incidents", not
        "falls").
      - "active/unresolved/open/in progress" → status = false (incidents.status
        is a boolean where true = resolved).
      - resident named → require the room's mapping to land on that resident.
      - default time window is the last 7 days; "today"/"yesterday" /
        "this month" override it. Keeps "show me recent incidents" from
        dumping months of history.
    """
    q_lower = query.lower()
    if is_fall_query is None:
        is_fall_query = bool(_FALL_TERM_RE.search(q_lower))
    if is_active_only is None:
        is_active_only = bool(_ACTIVE_ALERT_RE.search(q_lower))
    is_when_query = bool(_WHEN_QUERY_RE.search(q_lower))

    if interval is None:
        if _TIME_WINDOW_TODAY_RE.search(q_lower):
            interval = "1 day"
        elif _TIME_WINDOW_YESTERDAY_RE.search(q_lower):
            interval = "2 days"
        elif _TIME_WINDOW_MONTH_RE.search(q_lower):
            interval = "30 days"
        else:
            interval = "7 days"

    select_cols = (
        "i.event_category, i.event_outcome, i.event_time, i.status, "
        "rp.name AS resident_name, r.room_name"
    )
    from_clause = "FROM incidents i " + _ROOM_TO_RESIDENT_JOIN.format(table="i")

    conditions = [
        "r.community_id = %s",
        f"i.event_time > now() - INTERVAL '{interval}'",
        "COALESCE(i.is_deleted, false) = false",
    ]
    params: list = [community_id]

    if is_fall_query:
        conditions.append("i.event_category IN ('fall_alert', 'confirmed_fall', 'suspected_alert')")
    if is_active_only:
        conditions.append("i.status = false")
    if resident_id is not None:
        conditions.append("rp.id = %s")
        params.append(resident_id)
    elif resident_name:
        conditions.append("rp.name ILIKE %s")
        params.append(f"%{_resident_filter_value(resident_name)}%")
    elif exclude_name:
        # "other residents" — events that belong to a real resident who is
        # NOT the one in focus. Require a non-null name so unassigned-room
        # events don't masquerade as "another resident".
        conditions.append("rp.name IS NOT NULL")
        conditions.append("rp.name NOT ILIKE %s")
        params.append(f"%{_resident_filter_value(exclude_name)}%")

    sql = (
        f"SELECT {select_cols} {from_clause} "
        f"WHERE {' AND '.join(conditions)} "
        "ORDER BY i.event_time DESC LIMIT 25"
    )
    _validate_read_only_sql(sql)
    return sql, params, {
        "interval": interval,
        "is_fall_query": is_fall_query,
        "is_active_only": is_active_only,
        "is_when_query": is_when_query,
        "resident_name": resident_name,
        "resident_id": resident_id,
        "exclude_name": exclude_name,
    }


def _format_incidents_answer(rows: list, meta: dict) -> str:
    """Conversational incident summary.

    Goal: lead with a sentence that answers the user's question, then list
    the supporting events in a tight bullet form. Stays neutral — no
    clinical interpretation ("severe", "concerning") and no invented
    pronouns. Everything quoted is straight from the row.
    """
    resident_name = meta.get("resident_name")
    is_fall_query = meta.get("is_fall_query")
    is_active_only = meta.get("is_active_only")
    is_when_query = meta.get("is_when_query")
    exclude_name = meta.get("exclude_name")
    interval = meta.get("interval", "7 days")
    window_phrase = {
        "1 day": "today", "2 days": "in the last couple of days",
        "7 days": "in the last week", "30 days": "in the last month",
    }.get(interval, "recently")

    # --- No-result branches ---------------------------------------------------
    if not rows:
        if exclude_name and is_fall_query:
            return f"No — no other residents have had a fall {window_phrase}."
        if exclude_name and is_active_only:
            return "No other residents have active or unresolved alerts right now."
        if exclude_name:
            return f"No — no other residents have any incidents on record {window_phrase}."
        if resident_name and is_fall_query:
            return f"No fall events on record for {resident_name} {window_phrase}."
        if resident_name:
            return f"No incidents on record for {resident_name} {window_phrase}."
        if is_fall_query:
            return f"No falls recorded in this community {window_phrase}."
        if is_active_only:
            return "No active or unresolved alerts in this community."
        return f"No incidents recorded in this community {window_phrase}."

    # --- Result branches ------------------------------------------------------
    count = len(rows)
    active_count = sum(1 for r in rows if r[3] is False)

    # Screening note for resident-scoped fall queries: weigh confirmed_fall
    # heavier than fall_alert, and tell the caregiver whether this looks
    # like a one-off vs a pattern.
    fall_screening = ""
    if is_fall_query and resident_name:
        fall_total = sum(
            1 for r in rows
            if str(r[0]) in ("fall_alert", "confirmed_fall", "suspected_alert")
        )
        confirmed = sum(1 for r in rows if str(r[0]) == "confirmed_fall")
        fall_reading = classify_fall_pattern(fall_total, confirmed)
        if fall_reading and fall_reading.band != "normal":
            fall_screening = f"\n\n{fall_reading.note}"

    if exclude_name and is_fall_query:
        verb = "is" if count == 1 else "are"
        lead = f"Yes — there {verb} {_plural(count, 'fall event')} from other residents {window_phrase}."
    elif exclude_name:
        lead = (
            f"{_plural(count, 'incident').capitalize()} from other residents "
            f"{('is' if count == 1 else 'are')} on record {window_phrase}."
        )
    elif is_active_only:
        lead = (
            f"There's {_plural(count, 'active alert')} in this community right now."
            if count else "No active alerts at the moment."
        )
    elif is_when_query and resident_name:
        # "When did X fall?" — answer with the timing of the most recent
        # event (rows are ordered event_time DESC) instead of the yes/no
        # "Yes — X has N fall events" framing, which doesn't fit a "when"
        # question. The supporting events still follow in the bullet list.
        noun = "fall" if is_fall_query else "incident"
        label = "fall event" if is_fall_query else "incident"
        most_recent_when = _human_clock(rows[0][2])
        if count == 1:
            lead = f"{resident_name}'s most recent {noun} was logged {most_recent_when}."
        else:
            lead = (
                f"{resident_name}'s most recent {noun} was logged {most_recent_when} "
                f"({_plural(count, label)} on record {window_phrase})."
            )
    elif is_fall_query and resident_name:
        lead = (
            f"Yes — {resident_name} has {_plural(count, 'fall event')} on record "
            f"{window_phrase}."
        )
    elif is_fall_query:
        lead = (
            f"{_plural(count, 'fall event').capitalize()} {('has' if count == 1 else 'have')} "
            f"been logged across this community {window_phrase}"
            + (f" ({active_count} still unresolved)." if active_count else ".")
        )
    elif resident_name:
        lead = (
            f"{resident_name} has {_plural(count, 'incident')} on record "
            f"{window_phrase}."
        )
    else:
        lead = (
            f"{_plural(count, 'incident').capitalize()} {('has' if count == 1 else 'have')} "
            f"been logged in this community {window_phrase}"
            + (f" ({active_count} still unresolved)." if active_count else ".")
        )

    lines = [lead, ""]
    for category, outcome, event_time, status, name, room_name in rows:
        when = _human_clock(event_time)
        # incidents.status is the alert's response state (true=resolved by a
        # caregiver, false=open). Render false as "unresolved", not "active" —
        # the fall itself is a point-in-time event; what's open is the alert.
        state = "resolved" if status else "unresolved"
        who = name if name else (room_name or "an unassigned room")
        outcome_text = f" — {outcome}" if outcome else ""
        # Render "fall_alert" → "fall alert" so it reads as English.
        category_text = str(category).replace("_", " ")
        lines.append(f"- {when}: {category_text} for {who} ({state}){outcome_text}")
    return "\n".join(lines) + fall_screening


def _detect_incidents_plan(query: str) -> dict | None:
    """Fire on fall- or incident-shaped questions only."""
    q_lower = query.lower()
    has_fall = bool(_FALL_TERM_RE.search(q_lower))
    has_incident = bool(_INCIDENT_TERM_RE.search(q_lower))
    if not (has_fall or has_incident):
        return None
    # If the user is asking about no_of_falls as a profile field (e.g. "how
    # many falls has X had in total" — the resident_profile.no_of_falls
    # counter) we want them to land on the resident-profile handler. The
    # incident handler covers time-windowed event lookups, not aggregate
    # counters. The "in total"/"so far"/"lifetime" phrasing is the disambiguator.
    if has_fall and re.search(r"\b(?:in\s+total|so\s+far|lifetime|all[-\s]time)\b", q_lower):
        return None
    return {"_macro": "incidents"}


def _step_incidents(query: str, community_id: int) -> dict | None:
    if _detect_incidents_plan(query) is None:
        return None

    # "any other resident / besides X" — exclude the focus resident and report
    # community-wide-minus-them. The excluded name must NOT be treated as the
    # target, so skip target resolution entirely in this mode.
    exclude_name = _extract_excluded_resident_name(query)
    if exclude_name:
        resident_id, resident_name = None, None
    else:
        resident_id, resident_name = _resolve_resident_target(query, community_id)

    # If the user clearly named a specific resident in the question but the
    # roster matcher couldn't resolve them, refuse honestly instead of
    # silently widening to the whole community — otherwise "Did Bruce Wayne
    # have a fall?" returns Anil Sharma's fall events, which is worse than
    # a clean "couldn't find that resident."
    if not exclude_name and resident_id is None and not resident_name:
        named_match = _NAMED_RESIDENT_FALL_RE.search(query)
        if named_match:
            asked = named_match.group(1).strip()
            # Filter out generic owners like "anyone"/"the resident" — the
            # regex captures whatever sits between "did/has" and "fall",
            # and only proper-noun names should trip the refusal path.
            tokens = [w.lower() for w in asked.split()]
            # Indefinite pronouns aren't in _RESIDENT_NAME_STOPWORDS (it's
            # tuned for resident name extraction). Catch them locally so
            # "has anyone fallen?" doesn't produce
            # "I couldn't find Anyone in the roster."
            _indefinite = {
                "anyone", "anybody", "someone", "somebody",
                "everyone", "everybody", "nobody", "no",
            }
            looks_like_name = (
                tokens
                and not any(t in _RESIDENT_NAME_STOPWORDS for t in tokens)
                and not any(t in _indefinite for t in tokens)
            )
            if looks_like_name:
                pretty = asked.strip().title()
                return {
                    "query": query,
                    "plan": {"_macro": "incidents", "missing_resident": pretty},
                    "result": [],
                    "answer": (
                        f"I couldn't find {pretty} in this community's resident roster."
                    ),
                }

    sql, params, meta = _build_incidents_sql(
        query, community_id, resident_id, resident_name, exclude_name
    )
    rows = run_query(sql, params)
    logger.info(f"Deterministic incidents plan: {meta}")
    return {
        "query": query,
        "plan": {"_macro": "incidents", **meta},
        "sql": sql,
        "result": rows,
        "answer": _format_incidents_answer(rows, meta),
    }


# ===========================================================================
# Devices / sensors in rooms
#
# Each room carries KuboCare monitoring sensors (rows in the `objects` table:
# a fall-detection sensor and a vitals/radar sensor, with text ids like
# OBJ-00075). Without this handler "list the devices" and "what device is in
# X's room" fell through to the resident handlers and returned a wrong/empty
# answer. This answers three shapes: a community-wide device list/count, the
# device(s) in a named resident's room, and the device(s) in a named room.
# ===========================================================================

# "device(s)", "sensor(s)", "radar" — the words that mean "monitoring hardware".
_DEVICE_TERM_RE = re.compile(r"\b(?:devices?|sensors?|radar)\b", re.IGNORECASE)
# Each room has ONE KuboCare radar device (object_type 'sensor') that handles
# fall detection, bed algorithms, and vitals together. furniture (the bed) is
# not a device. The legacy split types are kept in the IN-list only so the
# handler still works against un-migrated data. Hard-coded enum literals.
_DEVICE_TYPES_SQL = "('sensor', 'sensor_fds', 'sensor_vitals')"
_DEVICE_TYPE_LABELS = {
    "sensor": "KuboCare radar (fall detection, bed monitoring & vitals)",
    "sensor_fds": "fall-detection sensor",
    "sensor_vitals": "vitals/radar sensor",
}
# "in room 3", "room F-1" — capture the room token after the word "room".
_ROOM_NAME_RE = re.compile(r"\broom\s+([a-z]?-?\d+|[a-z0-9][a-z0-9-]*)\b", re.IGNORECASE)
_DEVICE_COUNT_RE = re.compile(r"\b(?:how\s+many|number\s+of|count\s+of)\b", re.IGNORECASE)
# "are all devices online / active / working?" — a status question that wants a
# yes/no summary, not the full device list.
_DEVICE_STATUS_RE = re.compile(
    r"\b(?:active|inactive|online|offline|working|not\s+working|down|"
    r"responding|operational|functioning|status|health|healthy|up|running|"
    r"connected|disconnected|reachable|live)\b",
    re.IGNORECASE,
)


def _device_label(object_type) -> str:
    return _DEVICE_TYPE_LABELS.get(str(object_type), str(object_type).replace("_", " "))


def _device_status_text(status, device_status) -> str:
    """Render the device's health as a short, plain word."""
    if device_status:
        return str(device_status)
    s = str(status).lower() if status is not None else ""
    if s in ("good", "true"):
        return "online"
    if s in ("no_response", "false"):
        return "not responding"
    return s or "status unknown"


def _device_is_online(status, device_status) -> bool:
    return _device_status_text(status, device_status) == "online"


def _format_devices_status(rows: list, scope_label: str) -> str:
    """Answer "are all devices online?" with a yes/no summary, listing only the
    devices that need attention. Row layout (shared by all scopes):
    [object_id, object_type, device_status, status, room_name, ...]."""
    total = len(rows)
    if total == 0:
        return f"There are no monitoring devices on record in {scope_label}."

    offline = [r for r in rows if not _device_is_online(r[3], r[2])]
    if not offline:
        if total == 1:
            return f"Yes — the KuboCare radar in {scope_label} is online."
        return f"Yes — all {total} KuboCare radar devices in {scope_label} are online."

    online_n = total - len(offline)
    lines = [
        f"No — {online_n} of {total} devices in {scope_label} are online; "
        f"{len(offline)} need attention:",
        "",
    ]
    for object_id, object_type, device_status, status, room_name, *_ in offline:
        where = f"{room_name} " if room_name else ""
        lines.append(f"- {where}({object_id}) — {_device_status_text(status, device_status)}")
    return "\n".join(lines)


def _detect_device_plan(query: str) -> bool:
    return bool(_DEVICE_TERM_RE.search(query.lower()))


def _resolve_device_resident(query: str, community_id: int) -> tuple[int | None, str | None]:
    """Resolve a resident named in a device question, using the roster matcher
    (robust to "Hari Menon's" / "hari menons"). Returns (id, canonical_name)."""
    resident_id = _extract_resident_id(query)
    if resident_id is not None:
        return resident_id, None
    from app.retrievers.sql_retriever import _find_resident_names_in_query

    matches = _find_resident_names_in_query(query, community_id)
    if matches:
        return None, matches[0]
    return None, None


def _format_devices_for_resident(name: str, rows: list) -> str:
    if not rows:
        return (
            f"I couldn't find any monitoring devices linked to {name}'s room "
            "in the records."
        )
    room_name = rows[0][4] or "their room"
    count = len(rows)
    noun = "device" if count == 1 else "devices"
    lines = [f"{name}'s room ({room_name}) has {count} monitoring {noun}:", ""]
    for object_id, object_type, device_status, status, _room in rows:
        lines.append(
            f"- {object_id} — {_device_label(object_type)} "
            f"({_device_status_text(status, device_status)})"
        )
    return "\n".join(lines)


def _format_devices_for_room(room_label: str, rows: list) -> str:
    if not rows:
        return f"I couldn't find any monitoring devices in {room_label}."
    count = len(rows)
    noun = "device" if count == 1 else "devices"
    lines = [f"{room_label} has {count} monitoring {noun}:", ""]
    for object_id, object_type, device_status, status, _room in rows:
        lines.append(
            f"- {object_id} — {_device_label(object_type)} "
            f"({_device_status_text(status, device_status)})"
        )
    return "\n".join(lines)


def _format_devices_list(rows: list) -> str:
    if not rows:
        return "There are no monitoring devices on record in this community."
    count = len(rows)
    lines = [
        f"There {'is' if count == 1 else 'are'} {count} monitoring "
        f"{'device' if count == 1 else 'devices'} across this community "
        "(one KuboCare radar per room):",
        "",
    ]
    current_room = object()  # sentinel
    for object_id, object_type, device_status, status, room_name, resident in rows:
        if room_name != current_room:
            current_room = room_name
            who = f" — {resident}" if resident else ""
            lines.append(f"{room_name or 'Unassigned room'}{who}:")
        lines.append(
            f"  - {object_id} — {_device_label(object_type)} "
            f"({_device_status_text(status, device_status)})"
        )
    return "\n".join(lines)


def _step_devices(query: str, community_id: int) -> dict | None:
    if not _detect_device_plan(query):
        return None

    q = query.lower()
    status_mode = bool(_DEVICE_STATUS_RE.search(q))

    # 1) Device(s) in a named resident's room.
    resident_id, resident_name = _resolve_device_resident(query, community_id)
    if resident_id is not None or resident_name:
        conditions = ["r.community_id = %s"]
        params: list = [community_id]
        if resident_id is not None:
            conditions.append("rp.id = %s")
            params.append(resident_id)
        else:
            conditions.append("rp.name ILIKE %s")
            params.append(f"%{_resident_filter_value(resident_name)}%")
        sql = (
            "SELECT o.object_id, o.object_type::text, o.device_status, o.status::text, r.room_name "
            "FROM objects o "
            "JOIN rooms r ON r.id = o.room_id AND COALESCE(r.is_deleted, false) = false "
            "JOIN room_resident_mapping rrm ON rrm.room_id = r.id AND COALESCE(rrm.is_deleted, false) = false "
            "JOIN resident_profile rp ON rp.id = rrm.resident_id AND COALESCE(rp.is_deleted, false) = false "
            f"WHERE {' AND '.join(conditions)} "
            f"AND o.object_type::text IN {_DEVICE_TYPES_SQL} "
            "AND COALESCE(o.is_deleted, false) = false "
            "ORDER BY o.object_id"
        )
        _validate_read_only_sql(sql)
        rows = run_query(sql, params)
        label = resident_name or f"resident {resident_id}"
        logger.info(f"Deterministic devices plan: resident={label}")
        answer = (
            _format_devices_status(rows, f"{label}'s room") if status_mode
            else _format_devices_for_resident(label, rows)
        )
        return {
            "query": query,
            "plan": {"_macro": "devices", "scope": "resident", "resident_name": resident_name},
            "sql": sql,
            "result": rows,
            "answer": answer,
        }

    # 2) Device(s) in a named room ("devices in room 3").
    room_match = _ROOM_NAME_RE.search(q)
    if room_match:
        room_token = room_match.group(1)
        sql = (
            "SELECT o.object_id, o.object_type::text, o.device_status, o.status::text, r.room_name "
            "FROM objects o "
            "JOIN rooms r ON r.id = o.room_id AND COALESCE(r.is_deleted, false) = false "
            "WHERE r.community_id = %s AND r.room_name ILIKE %s "
            f"AND o.object_type::text IN {_DEVICE_TYPES_SQL} "
            "AND COALESCE(o.is_deleted, false) = false "
            "ORDER BY o.object_id"
        )
        _validate_read_only_sql(sql)
        rows = run_query(sql, (community_id, f"%{room_token}%"))
        room_label = rows[0][4] if rows else f"room {room_token}"
        logger.info(f"Deterministic devices plan: room={room_token}")
        answer = (
            _format_devices_status(rows, room_label) if status_mode
            else _format_devices_for_room(room_label, rows)
        )
        return {
            "query": query,
            "plan": {"_macro": "devices", "scope": "room", "room": room_token},
            "sql": sql,
            "result": rows,
            "answer": answer,
        }

    # 3) Community-wide list or count.
    sql = (
        "SELECT o.object_id, o.object_type::text, o.device_status, o.status::text, "
        "r.room_name, rp.name "
        "FROM objects o "
        "JOIN rooms r ON r.id = o.room_id AND COALESCE(r.is_deleted, false) = false "
        "LEFT JOIN room_resident_mapping rrm ON rrm.room_id = r.id AND COALESCE(rrm.is_deleted, false) = false "
        "LEFT JOIN resident_profile rp ON rp.id = rrm.resident_id AND COALESCE(rp.is_deleted, false) = false "
        f"WHERE r.community_id = %s AND o.object_type::text IN {_DEVICE_TYPES_SQL} "
        "AND COALESCE(o.is_deleted, false) = false "
        "ORDER BY r.room_name, o.object_id"
    )
    _validate_read_only_sql(sql)
    rows = run_query(sql, (community_id,))
    logger.info("Deterministic devices plan: community-wide list")

    if status_mode:
        answer = _format_devices_status(rows, "this community")
    elif _DEVICE_COUNT_RE.search(q):
        count = len(rows)
        answer = (
            f"There {'is' if count == 1 else 'are'} {count} monitoring "
            f"{'device' if count == 1 else 'devices'} in this community."
        )
    else:
        answer = _format_devices_list(rows)
    return {
        "query": query,
        "plan": {"_macro": "devices", "scope": "community"},
        "sql": sql,
        "result": rows,
        "answer": answer,
    }


# ===========================================================================
# Vitals — heart rate, respiration rate, pulse
# ===========================================================================


def _build_vitals_sql(
    community_id: int,
    resident_id: int | None,
    resident_name: str | None,
) -> tuple[str, list]:
    """Latest vitals sample for a resident (or empty if none)."""
    select_cols = "rp.name, v.hr, v.rr, v.ingestion_time"
    from_clause = "FROM vitals v " + _BOARD_TO_RESIDENT_JOIN.format(sensor="v")

    conditions = ["r.community_id = %s"]
    params: list = [community_id]

    if resident_id is not None:
        conditions.append("rp.id = %s")
        params.append(resident_id)
    elif resident_name:
        conditions.append("rp.name ILIKE %s")
        params.append(f"%{_resident_filter_value(resident_name)}%")

    sql = (
        f"SELECT {select_cols} {from_clause} "
        f"WHERE {' AND '.join(conditions)} "
        "ORDER BY v.ingestion_time DESC LIMIT 1"
    )
    _validate_read_only_sql(sql)
    return sql, params


def _format_vitals_answer(rows: list, resident_name: str | None) -> str:
    if not rows:
        target = resident_name or "that resident"
        return f"No vitals readings on record for {target}."
    name, hr, rr, ts = rows[0]
    when = _human_clock(ts)
    hr_reading = classify_hr(hr)
    rr_reading = classify_rr(rr)

    lead = (
        f"{name}'s most recent vitals were logged {when}. "
        f"Heart rate came in at {hr} bpm and respiration at {rr} breaths per minute."
    )

    # Build a screening line by combining the worst of the two notes — keeps
    # the answer to ~2 sentences when both are normal, and surfaces a clear
    # callout when one isn't.
    screening_bits: list[str] = []
    if hr_reading and hr_reading.band != "normal":
        screening_bits.append(f"Heart rate: {hr_reading.note}")
    if rr_reading and rr_reading.band != "normal":
        screening_bits.append(f"Respiration: {rr_reading.note}")

    if screening_bits:
        return lead + " " + " ".join(screening_bits)
    return lead + " Both readings are within typical resting ranges."


def _detect_vitals_plan(query: str, community_id: int) -> dict | None:
    q_lower = query.lower()
    if not _VITALS_TERM_RE.search(q_lower):
        return None
    # Sleep + vitals overlap when someone says "vitals during sleep" — fall
    # through to the sleep handler, which already deals with the night.
    if _SLEEP_SESSION_RE.search(q_lower):
        return None
    if not _has_resident_target(query, community_id):
        # Community-wide vitals would have to roll up across 40 residents;
        # not a question shape covered here yet. Let the LLM planner try.
        return None
    return {"_macro": "vitals"}


def _step_vitals(query: str, community_id: int) -> dict | None:
    if _detect_vitals_plan(query, community_id) is None:
        return None
    resident_id, resident_name = _resolve_resident_target(query, community_id)
    sql, params = _build_vitals_sql(community_id, resident_id, resident_name)
    rows = run_query(sql, params)
    logger.info(f"Deterministic vitals plan: resident={resident_name or resident_id}")
    return {
        "query": query,
        "plan": {"_macro": "vitals", "resident_name": resident_name, "resident_id": resident_id},
        "sql": sql,
        "result": rows,
        "answer": _format_vitals_answer(rows, resident_name),
    }


# ===========================================================================
# Sleep session breakdown
# ===========================================================================


def _build_sleep_sql(
    community_id: int,
    resident_id: int | None,
    resident_name: str | None,
    target_date=None,
) -> tuple[str, list]:
    """Sleep_session segments for one night for a resident.

    Without ``target_date`` this returns the most recent night: the four
    segments whose start_duration is the latest. The seed inserts 4 stages
    per night so LIMIT 4 after ORDER BY start_duration DESC is one full
    night. With ``target_date`` set, it pins that one night.

    Note: a night's stages straddle two calendar dates (the evening it
    begins plus the early-morning hours of the next day), so a date filter
    must be a noon-to-noon window around the evening, not ``= some_date``.
    """
    select_cols = (
        "rp.name, ss.sleep_stage, ss.start_duration, ss.end_duration"
    )
    from_clause = "FROM sleep_sessions ss " + _BOARD_TO_RESIDENT_JOIN.format(sensor="ss")

    conditions = ["r.community_id = %s"]
    params: list = [community_id]

    if resident_id is not None:
        conditions.append("rp.id = %s")
        params.append(resident_id)
    elif resident_name:
        conditions.append("rp.name ILIKE %s")
        params.append(f"%{_resident_filter_value(resident_name)}%")

    if target_date is not None:
        from datetime import datetime, time, timedelta

        night_lo = datetime.combine(target_date, time(12, 0))
        night_hi = night_lo + timedelta(days=1)
        conditions.append("ss.start_duration >= %s AND ss.start_duration < %s")
        params.extend([night_lo, night_hi])

    sql = (
        f"SELECT {select_cols} {from_clause} "
        f"WHERE {' AND '.join(conditions)} "
        "ORDER BY ss.start_duration DESC LIMIT 4"
    )
    _validate_read_only_sql(sql)
    return sql, params


def _build_sleep_history_sql(
    community_id: int,
    resident_id: int | None,
    resident_name: str | None,
    nights: int = 15,
) -> tuple[str, list]:
    """Every sleep segment for a resident across the last ``nights`` nights.

    Defaults to the full 15-night seed window so trend/"sleep less" answers
    compare across all retained history, not just the most recent week.
    Pulls a slightly wider window than asked (``nights + 1`` days) so a night
    that began late in the window isn't clipped, then the formatter groups
    into nights and keeps the most recent ``nights``. LIMIT scales with the
    requested window (≈4 stages/night) — one resident only.
    """
    select_cols = "rp.name, ss.sleep_stage, ss.start_duration, ss.end_duration"
    from_clause = "FROM sleep_sessions ss " + _BOARD_TO_RESIDENT_JOIN.format(sensor="ss")

    conditions = [
        "r.community_id = %s",
        f"ss.start_duration > now() - INTERVAL '{nights + 1} days'",
    ]
    params: list = [community_id]

    if resident_id is not None:
        conditions.append("rp.id = %s")
        params.append(resident_id)
    elif resident_name:
        conditions.append("rp.name ILIKE %s")
        params.append(f"%{_resident_filter_value(resident_name)}%")

    sql = (
        f"SELECT {select_cols} {from_clause} "
        f"WHERE {' AND '.join(conditions)} "
        f"ORDER BY ss.start_duration DESC LIMIT {nights * 4 + 8}"
    )
    _validate_read_only_sql(sql)
    return sql, params


# --- Shared sleep formatting helpers ---------------------------------------


def _fmt_hm(minutes: int) -> str:
    """`90 → "1h 30m"`, `120 → "2h"`, `45 → "45m"`."""
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


def _breakdown_phrase(stages: list[tuple[str, int]]) -> str:
    """"2h of light sleep, 3h of deep sleep, 2h of REM, and 1h awake"."""
    nice_parts = []
    for stage, minutes in stages:
        duration = _fmt_hm(minutes)
        if stage == "awake":
            nice_parts.append(f"{duration} awake")
        elif stage == "rem":
            nice_parts.append(f"{duration} of REM")
        elif stage == "nonrem":
            nice_parts.append(f"{duration} of non-REM")
        else:
            nice_parts.append(f"{duration} of {stage} sleep")
    if len(nice_parts) > 1:
        return ", ".join(nice_parts[:-1]) + f", and {nice_parts[-1]}"
    return nice_parts[0] if nice_parts else "no recorded stages"


def _sleep_screening(total_minutes: int) -> str:
    reading = classify_sleep_duration(total_minutes)
    if reading and reading.band == "normal":
        return " That's within a healthy sleep range for an older adult."
    if reading:
        return f" {reading.note}"
    return ""


def _group_sleep_nights(rows: list) -> list[dict]:
    """Group flat stage rows into per-night summaries, newest night first.

    A sleep night runs from the evening into the next morning, so its four
    stages straddle two calendar dates. Keying on ``start - 12h`` collapses
    every segment of one night onto the evening it began — that evening's
    date is the night's label. Returns dicts with ``date`` (the label date),
    ``total_minutes`` (asleep, i.e. excluding 'awake'), and ``stages``.
    """
    from collections import defaultdict
    from datetime import timedelta

    by_night: dict = defaultdict(list)
    for _name, stage, start, end in rows:
        if start is None:
            continue
        key = (start - timedelta(hours=12)).date()
        by_night[key].append((stage, start, end))

    nights = []
    for night_date in sorted(by_night, reverse=True):
        segs = sorted(by_night[night_date], key=lambda s: s[1])
        total = 0
        stages: list[tuple[str, int]] = []
        for stage, start, end in segs:
            minutes = int((end - start).total_seconds() // 60) if start and end else 0
            if stage != "awake":
                total += minutes
            stages.append((stage, minutes))
        nights.append({"date": night_date, "total_minutes": total, "stages": stages})
    return nights


def _format_sleep_answer(rows: list, resident_name: str | None, target_date=None) -> str:
    if not rows:
        target = resident_name or "that resident"
        if target_date is not None:
            return f"No sleep record on file for {target} for the night of {_human_date(target_date)}."
        return f"No sleep records on file for {target}."

    name = rows[0][0]
    night = _group_sleep_nights(rows)[0]
    when = _human_date(night["date"])
    breakdown = _breakdown_phrase(night["stages"])
    screening = _sleep_screening(night["total_minutes"])
    return (
        f"{name} slept about {_fmt_hm(night['total_minutes'])} on the night of {when}. "
        f"The night broke down into {breakdown}.{screening}"
    )


def _format_sleep_history(rows: list, resident_name: str | None, max_nights: int = 15) -> str:
    """List each night's total asleep, newest first, with a low/high callout
    so a caregiver can compare across the window at a glance."""
    if not rows:
        target = resident_name or "that resident"
        return f"No sleep records on file for {target}."

    name = rows[0][0]
    nights = _group_sleep_nights(rows)[:max_nights]
    lines = [
        f"{name}'s sleep over the last {len(nights)} "
        f"{'night' if len(nights) == 1 else 'nights'} (most recent first):",
        "",
    ]
    for night in nights:
        lines.append(
            f"- {_human_date(night['date'])}: about {_fmt_hm(night['total_minutes'])} asleep"
        )

    lowest = min(nights, key=lambda n: n["total_minutes"])
    highest = max(nights, key=lambda n: n["total_minutes"])
    if lowest["date"] != highest["date"]:
        lines.append("")
        lines.append(
            f"Lowest was {_human_date(lowest['date'])} (~{_fmt_hm(lowest['total_minutes'])}); "
            f"highest was {_human_date(highest['date'])} (~{_fmt_hm(highest['total_minutes'])})."
        )
    return "\n".join(lines)


def _format_sleep_extreme(rows: list, resident_name: str | None, which: str) -> str:
    """`which` = 'least' or 'most' — the night with min/max time asleep,
    with comparative context across the window."""
    if not rows:
        target = resident_name or "that resident"
        return f"No sleep records on file for {target}."

    name = rows[0][0]
    nights = _group_sleep_nights(rows)
    if which == "least":
        pick, verb = min(nights, key=lambda n: n["total_minutes"]), "the least"
    else:
        pick, verb = max(nights, key=lambda n: n["total_minutes"]), "the most"

    when = _human_date(pick["date"])
    breakdown = _breakdown_phrase(pick["stages"])
    screening = _sleep_screening(pick["total_minutes"])

    span = ""
    if len(nights) > 1:
        lo = min(n["total_minutes"] for n in nights)
        hi = max(n["total_minutes"] for n in nights)
        span = (
            f" Across the last {len(nights)} nights, nightly sleep ranged from "
            f"{_fmt_hm(lo)} to {_fmt_hm(hi)}."
        )
    return (
        f"{name} slept {verb} on the night of {when} — about {_fmt_hm(pick['total_minutes'])}. "
        f"That night broke down into {breakdown}.{screening}{span}"
    )


def _detect_sleep_plan(query: str, community_id: int) -> dict | None:
    q_lower = query.lower()
    if not _SLEEP_TERM_RE.search(q_lower):
        return None
    # "X's sleep score" is a wellness-metric question, not a session
    # breakdown. Defer to the wellness handler.
    if "score" in q_lower or _WELLNESS_TERM_RE.search(q_lower):
        return None
    if not _has_resident_target(query, community_id):
        return None
    return {"_macro": "sleep"}


# A single-week request → cap the history list at 7 nights so the answer
# matches the word "week": "this/last/past/the/one/1/a week", "weekly", or
# "7 days". Anything broader (trend, compare, "all nights", "two weeks",
# "fortnight", "14/15 days") and the least/most comparison span the full window.
_WEEK_SCOPED_RE = re.compile(
    r"\b(?:(?:this|last|past|the|one|1|a)\s+week|weekly|7\s+days)\b",
    re.IGNORECASE,
)


def _sleep_mode(query: str, target_date) -> str:
    """Pick the sleep view: a specific 'date', the 'least'/'most' night across
    the window, the full 'history' list, or the single 'latest' night."""
    if target_date is not None:
        return "date"
    q = query.lower()
    if _SLEEP_LEAST_RE.search(q):
        return "least"
    if _SLEEP_MOST_RE.search(q):
        return "most"
    if _SLEEP_HISTORY_RE.search(q):
        return "history"
    return "latest"


def _sleep_history_nights(query: str, mode: str) -> int:
    """How many nights back to pull. least/most always use the full 15-night
    window for the most accurate extreme; a 'this/last week' history list is
    capped at 7, everything else gets the full 15."""
    if mode == "history" and _WEEK_SCOPED_RE.search(query):
        return 7
    return 15


def _step_sleep(query: str, community_id: int) -> dict | None:
    if _detect_sleep_plan(query, community_id) is None:
        return None
    resident_id, resident_name = _resolve_resident_target(query, community_id)
    target_date = _extract_target_date(query)
    mode = _sleep_mode(query, target_date)

    if mode in ("least", "most", "history"):
        nights = _sleep_history_nights(query, mode)
        sql, params = _build_sleep_history_sql(
            community_id, resident_id, resident_name, nights
        )
        rows = run_query(sql, params)
        if mode == "history":
            answer = _format_sleep_history(rows, resident_name, max_nights=nights)
        else:
            answer = _format_sleep_extreme(rows, resident_name, mode)
    else:
        sql, params = _build_sleep_sql(community_id, resident_id, resident_name, target_date)
        rows = run_query(sql, params)
        answer = _format_sleep_answer(rows, resident_name, target_date)

    logger.info(
        f"Deterministic sleep plan: resident={resident_name or resident_id} "
        f"mode={mode} night={target_date or 'n/a'}"
    )
    return {
        "query": query,
        "plan": {
            "_macro": "sleep", "resident_name": resident_name,
            "resident_id": resident_id, "mode": mode,
            "target_date": str(target_date) if target_date else None,
        },
        "sql": sql,
        "result": rows,
        "answer": answer,
    }


# ===========================================================================
# Wellness — wellness_metrics aggregate score
# ===========================================================================


def _build_wellness_sql(
    community_id: int,
    resident_id: int | None,
    resident_name: str | None,
) -> tuple[str, list]:
    """Latest day's wellness scores for a resident across all four types
    (sleep, activity, vitals, environment)."""
    select_cols = "rp.name, wm.type, wm.score, wm.date"
    from_clause = "FROM wellness_metrics wm " + _BOARD_TO_RESIDENT_JOIN.format(sensor="wm")

    conditions = [
        "r.community_id = %s",
        # Anchor on the most recent date the resident has data for. Doing
        # this as a subquery on the same table keeps the result tight even
        # if there are seven days of history per board.
        "wm.date = ("
        "  SELECT MAX(wm2.date) FROM wellness_metrics wm2 "
        "  WHERE wm2.board = wm.board"
        ")",
    ]
    params: list = [community_id]

    if resident_id is not None:
        conditions.append("rp.id = %s")
        params.append(resident_id)
    elif resident_name:
        conditions.append("rp.name ILIKE %s")
        params.append(f"%{_resident_filter_value(resident_name)}%")

    sql = (
        f"SELECT {select_cols} {from_clause} "
        f"WHERE {' AND '.join(conditions)} "
        "ORDER BY wm.type LIMIT 4"
    )
    _validate_read_only_sql(sql)
    return sql, params


def _format_wellness_answer(rows: list, resident_name: str | None) -> str:
    if not rows:
        target = resident_name or "that resident"
        return f"No wellness scores on record for {target}."
    name = rows[0][0]
    date = rows[0][3]
    when = _human_date(date)

    # Rank by score so the strongest area shows first — feels like a
    # quick "you're doing well in X, watch Y" rundown without diagnosing.
    by_score = sorted(
        ((str(wtype), round(float(score), 1)) for _, wtype, score, _ in rows),
        key=lambda item: item[1],
        reverse=True,
    )
    parts = ", ".join(f"{wtype} {score}" for wtype, score in by_score)
    strongest = by_score[0]
    weakest = by_score[-1]

    # Screening callout on the weakest score — surfaces "borderline" or
    # "concerning" only when the data warrants it. Everything-normal answers
    # stay one sentence.
    weakest_reading = classify_wellness_score(weakest[1])
    if weakest_reading and weakest_reading.band == "concerning":
        screening = f" {weakest[0].title()} score is low — review with the care plan."
    elif weakest_reading and weakest_reading.band == "elevated":
        screening = f" {weakest[0].title()} score is borderline."
    else:
        screening = ""

    return f"{name}'s wellness scores for {when}: {parts}.{screening}"


def _detect_wellness_plan(query: str, community_id: int) -> dict | None:
    q_lower = query.lower()
    is_wellness = bool(_WELLNESS_TERM_RE.search(q_lower))
    # "sleep score" / "activity score" / "vitals score" / "environment score"
    # are the type names of wellness_metrics. Catch them too.
    is_typed_score = bool(re.search(
        r"\b(?:sleep|activity|vitals?|environment)\s+score\b",
        q_lower,
    ))
    if not (is_wellness or is_typed_score):
        return None
    if not _has_resident_target(query, community_id):
        return None
    return {"_macro": "wellness"}


def _step_wellness(query: str, community_id: int) -> dict | None:
    if _detect_wellness_plan(query, community_id) is None:
        return None
    resident_id, resident_name = _resolve_resident_target(query, community_id)
    sql, params = _build_wellness_sql(community_id, resident_id, resident_name)
    rows = run_query(sql, params)
    logger.info(f"Deterministic wellness plan: resident={resident_name or resident_id}")
    return {
        "query": query,
        "plan": {"_macro": "wellness", "resident_name": resident_name, "resident_id": resident_id},
        "sql": sql,
        "result": rows,
        "answer": _format_wellness_answer(rows, resident_name),
    }


# ===========================================================================
# Holistic resident status — "How is X doing?" / "Is X stable?"
# ===========================================================================


# Question shapes that trigger the holistic summary. Kept tight on purpose
# so it doesn't swallow more specific intents (a question that hits sleep
# or vitals specifically should still land on its dedicated handler).
_HOLISTIC_RE = re.compile(
    r"\b(?:how\s+is|how['’]s|how\s+are)\s+[a-z]+(?:\s+[a-z]+){0,2}\s+doing\b"
    r"|\b(?:is|how['’]s)\s+[a-z]+(?:\s+[a-z]+){0,2}\s+"
    r"(?:doing\s+)?(?:ok|okay|fine|stable|alright|well|good)\b"
    r"|\bhow\s+is\s+[a-z]+(?:\s+[a-z]+){0,2}\?",
    re.IGNORECASE,
)


# Single-resident care / risk / priority questions. These ask "should I worry
# about THIS resident?" — answered by the same multi-signal summary as the
# holistic status, just phrased around care rather than "how are they doing".
# (The community-wide "who needs the most care?" is handled earlier by
# care._step_care_priority; this only fires when a specific resident is named.)
_CARE_STATUS_RE = re.compile(
    r"\bdoes\s+[a-z]+(?:\s+[a-z]+){0,2}\s+(?:need|require)\s+"
    r"(?:more\s+|extra\s+|additional\s+|any\s+)?(?:care|attention|monitoring|support|help|watching)\b"
    r"|\b(?:is|how['’]s)\s+[a-z]+(?:\s+[a-z]+){0,2}\s+"
    r"(?:a\s+)?(?:high|higher|low|lower)?\s*(?:care\s+)?(?:priority|at[\s-]?risk|concerning)\b"
    r"|\bwhat\s+care\s+does\s+[a-z]+(?:\s+[a-z]+){0,2}\s+need\b"
    r"|\bshould\s+(?:i|we)\s+(?:be\s+)?(?:worried|worry|concerned)\s+about\s+[a-z]+(?:\s+[a-z]+){0,2}\b"
    r"|\bdoes\s+[a-z]+(?:\s+[a-z]+){0,2}\s+need\s+(?:to\s+be\s+)?(?:watched|checked|reviewed|monitored)\b",
    re.IGNORECASE,
)


def _detect_holistic_plan(query: str) -> dict | None:
    q_lower = query.lower()
    # Defer to the specific handlers if the user named a sub-metric. The
    # holistic summary is for questions that don't already commit to one.
    if (
        _VITALS_TERM_RE.search(q_lower)
        or _SLEEP_TERM_RE.search(q_lower)
        or _WELLNESS_TERM_RE.search(q_lower)
        or _FALL_TERM_RE.search(q_lower)
        or _INCIDENT_TERM_RE.search(q_lower)
    ):
        return None
    if not (_HOLISTIC_RE.search(q_lower) or _CARE_STATUS_RE.search(q_lower)):
        return None
    return {"_macro": "holistic"}


def _step_holistic_status(query: str, community_id: int) -> dict | None:
    if _detect_holistic_plan(query) is None:
        return None
    resident_id, resident_name = _resolve_resident_target(query, community_id)
    if resident_id is None and not resident_name:
        return None  # Holistic summary needs a named resident.

    # Pull the inputs in parallel-ish (one round-trip per metric — could be
    # one query with UNIONs later, but four small queries are simple and
    # individually testable, and the existing connection pool absorbs them).
    vitals_sql, vitals_params = _build_vitals_sql(community_id, resident_id, resident_name)
    vitals_rows = run_query(vitals_sql, vitals_params)

    sleep_sql, sleep_params = _build_sleep_sql(community_id, resident_id, resident_name)
    sleep_rows = run_query(sleep_sql, sleep_params)

    wellness_sql, wellness_params = _build_wellness_sql(community_id, resident_id, resident_name)
    wellness_rows = run_query(wellness_sql, wellness_params)

    # Recent incidents for context (last 7 days, any category).
    incidents_query = "any incidents in the last 7 days"
    incidents_sql, incidents_params, incidents_meta = _build_incidents_sql(
        incidents_query, community_id, resident_id, resident_name,
    )
    incidents_rows = run_query(incidents_sql, incidents_params)

    # Classify everything.
    name = (
        vitals_rows[0][0] if vitals_rows else
        sleep_rows[0][0] if sleep_rows else
        wellness_rows[0][0] if wellness_rows else
        resident_name or "this resident"
    )

    hr_reading = classify_hr(vitals_rows[0][1]) if vitals_rows else None
    rr_reading = classify_rr(vitals_rows[0][2]) if vitals_rows else None

    sleep_minutes = 0
    if sleep_rows:
        for _n, stage, start, end in sleep_rows:
            if stage != "awake" and start and end:
                sleep_minutes += int((end - start).total_seconds() // 60)
    sleep_reading = classify_sleep_duration(sleep_minutes) if sleep_rows else None

    # Weakest wellness type drives the screening signal for the rollup.
    wellness_reading = None
    weakest_wellness_type: str | None = None
    if wellness_rows:
        ranked = sorted(
            ((str(t), float(s)) for _n, t, s, _d in wellness_rows),
            key=lambda i: i[1],
        )
        weakest_wellness_type, weakest_wellness_score = ranked[0]
        wellness_reading = classify_wellness_score(weakest_wellness_score)

    fall_total = sum(
        1 for r in incidents_rows
        if str(r[0]) in ("fall_alert", "confirmed_fall", "suspected_alert")
    )
    confirmed = sum(1 for r in incidents_rows if str(r[0]) == "confirmed_fall")
    incident_reading = classify_fall_pattern(fall_total, confirmed)

    # Build the answer.
    overall = worst_band(hr_reading, rr_reading, sleep_reading, wellness_reading, incident_reading)
    overall_phrase = {
        "concerning": "shows signals worth reviewing today",
        "high":       "shows elevated readings worth review",
        "low":        "shows readings on the low side",
        "elevated":   "is mostly steady, with items worth watching",
        "normal":     "looks stable across the board",
    }.get(overall or "normal", "has limited recent data")

    lines = [f"{name} {overall_phrase}."]

    if vitals_rows:
        _n, hr, rr, ts = vitals_rows[0]
        when = _human_clock(ts)
        line = f"Vitals ({when}): HR {hr} bpm, RR {rr} breaths/min."
        if hr_reading and hr_reading.band != "normal":
            line += f" {hr_reading.note}"
        if rr_reading and rr_reading.band != "normal":
            line += f" {rr_reading.note}"
        lines.append(line)
    else:
        lines.append("Vitals: no recent readings on file.")

    if sleep_rows and sleep_minutes:
        def _hm(m: int) -> str:
            h, m = divmod(m, 60)
            if h and m: return f"{h}h {m}m"
            if h: return f"{h}h"
            return f"{m}m"
        line = f"Sleep (latest night): about {_hm(sleep_minutes)} asleep."
        if sleep_reading and sleep_reading.band != "normal":
            line += f" {sleep_reading.note}"
        lines.append(line)
    else:
        lines.append("Sleep: no recent session on file.")

    if wellness_rows:
        line = f"Wellness rollup (most recent): " + ", ".join(
            f"{t} {round(float(s), 1)}" for _n, t, s, _d in wellness_rows
        ) + "."
        if wellness_reading and wellness_reading.band != "normal" and weakest_wellness_type:
            line += f" {weakest_wellness_type.title()} score is the weakest of the group."
        lines.append(line)

    if incidents_rows:
        line = f"Recent incidents (last 7 days): {len(incidents_rows)} on record."
        if incident_reading and incident_reading.band != "normal":
            line += f" {incident_reading.note}"
        lines.append(line)
    else:
        lines.append("Recent incidents: none in the last 7 days.")

    answer = "\n".join(lines)
    logger.info(f"Deterministic holistic plan: resident={name} overall={overall}")
    return {
        "query": query,
        "plan": {
            "_macro": "holistic_status",
            "resident_name": name,
            "overall_band": overall,
        },
        "result": {
            "vitals": vitals_rows, "sleep": sleep_rows,
            "wellness": wellness_rows, "incidents": incidents_rows,
        },
        "answer": answer,
    }


# ===========================================================================
# LLM-intent dispatch — flexible phrasing for health-data questions
#
# The regex handlers above understand the phrasings someone enumerated. This
# step adds robustness: a cheap keyword GATE decides "is this about a health
# metric at all" (stable vocabulary), then the LLM extracts the actual intent
# (resident, metric, time window, comparison, specific date) and we run the
# SAME deterministic builders below. If the LLM is unavailable or the question
# isn't health-data, it returns None and the regex handlers take over — so this
# can only add understanding, never remove it.
# ===========================================================================

# Broad "does this concern a monitored health metric" gate. Deliberately about
# DOMAIN vocabulary (stable) — not phrasing/intent (variable, left to the LLM).
_HEALTH_DOMAIN_GATE_RE = re.compile(
    r"\b(?:sleep|slept|sleeping|nap|napped|"
    r"heart\s*rate|hr|pulse|respiration|breathing|vitals?|vital\s+signs?|"
    r"wellness|well[-\s]?being|wellbeing|"
    r"fall|falls|fell|fallen|incident|incidents|alert|alerts|"
    r"notification|notifications|out\s+of\s+bed|out\s+of\s+room|"
    r"how\s+(?:is|are|'s|s)\b|doing\b|stable\b|okay\b)",
    re.IGNORECASE,
)


def _resolve_named_resident(name: str, community_id: int) -> str | None:
    """Map an LLM-extracted resident name to a canonical roster name in this
    community, or None. Going through the roster keeps the answer grounded —
    a name the model invented simply won't resolve."""
    if not name:
        return None
    from app.retrievers.sql_retriever import _find_resident_names_in_query

    matches = _find_resident_names_in_query(name, community_id)
    return matches[0] if matches else None


def _health_response(query, domain, sql, rows, answer, **plan_extra):
    plan = {"_macro": domain, "_via": "llm_intent"}
    plan.update(plan_extra)
    return {"query": query, "plan": plan, "sql": sql, "result": rows, "answer": answer}


def _dispatch_sleep_spec(query, community_id, resident_name, spec):
    target_date = spec.get("date")
    comparison = spec.get("comparison")
    window = spec.get("window_days")

    if target_date is not None:
        sql, params = _build_sleep_sql(community_id, None, resident_name, target_date)
        rows = run_query(sql, params)
        return _health_response(
            query, "sleep", sql, rows,
            _format_sleep_answer(rows, resident_name, target_date), mode="date",
        )
    if comparison in ("least", "most"):
        # Respect an explicit window ("worst sleep THIS WEEK" → over 7 nights,
        # not all 15); default to the full window when none was given.
        nights = max(1, min(window or 15, 15))
        sql, params = _build_sleep_history_sql(community_id, None, resident_name, nights)
        rows = run_query(sql, params)
        return _health_response(
            query, "sleep", sql, rows,
            _format_sleep_extreme(rows, resident_name, comparison), mode=comparison,
        )
    if comparison == "trend" or window:
        nights = max(1, min(window or 15, 15))  # only 15 nights of data exist
        sql, params = _build_sleep_history_sql(community_id, None, resident_name, nights)
        rows = run_query(sql, params)
        return _health_response(
            query, "sleep", sql, rows,
            _format_sleep_history(rows, resident_name, max_nights=nights), mode="history",
        )
    # No comparator / window / date → the single most-recent night.
    sql, params = _build_sleep_sql(community_id, None, resident_name, None)
    rows = run_query(sql, params)
    return _health_response(
        query, "sleep", sql, rows,
        _format_sleep_answer(rows, resident_name, None), mode="latest",
    )


def _dispatch_incidents_spec(query, community_id, resident_name, spec):
    window = spec.get("window_days")
    interval = None
    if window:
        interval = "1 day" if window == 1 else f"{int(window)} days"
    sql, params, meta = _build_incidents_sql(
        query, community_id, None, resident_name, None,
        interval=interval,
        is_fall_query=bool(spec.get("falls_only")),
        is_active_only=bool(spec.get("active_only")),
    )
    rows = run_query(sql, params)
    return _health_response(
        query, "incidents", sql, rows, _format_incidents_answer(rows, meta),
        resident_name=resident_name,
    )


def _step_health_intent(query: str, community_id: int) -> dict | None:
    """LLM-understood health-data questions → deterministic builders.

    Runs before the regex sensor handlers. Returns None (so they take over)
    whenever the gate misses, the LLM is unavailable, the question isn't a
    health-data domain, or a resident-scoped question names no resolvable
    resident.
    """
    if not _HEALTH_DOMAIN_GATE_RE.search(query):
        return None

    from app.agents.health_intent import extract_health_intent

    spec = extract_health_intent(query)
    if not spec:
        return None
    domain = spec["domain"]

    # Unsupported metric (BP/sugar/SpO2/weight/meds): hand to the existing
    # honest "not tracked" handler. It has its own keyword guard and returns
    # None unless that guard ALSO confirms the topic — so a mislabelled
    # supported question (e.g. heart rate) can't be hijacked into a refusal;
    # it just falls through to the real handlers below.
    if domain == "unsupported":
        from app.retrievers._sql.unsupported import _step_unsupported_metric

        return _step_unsupported_metric(query, community_id)

    # Holistic re-resolves the resident from the query itself; just delegate.
    if domain == "holistic":
        return _step_holistic_status(query, community_id)

    resident_name = _resolve_named_resident(spec.get("resident"), community_id)

    if domain in ("sleep", "vitals", "wellness") and not resident_name:
        # These are single-resident views; without a resolvable resident, let
        # the regex handlers try (they may refuse honestly or widen scope).
        return None

    logger.info(f"LLM-intent health plan: domain={domain} resident={resident_name}")

    if domain == "sleep":
        return _dispatch_sleep_spec(query, community_id, resident_name, spec)
    if domain == "vitals":
        sql, params = _build_vitals_sql(community_id, None, resident_name)
        rows = run_query(sql, params)
        return _health_response(
            query, "vitals", sql, rows, _format_vitals_answer(rows, resident_name),
        )
    if domain == "wellness":
        sql, params = _build_wellness_sql(community_id, None, resident_name)
        rows = run_query(sql, params)
        return _health_response(
            query, "wellness", sql, rows, _format_wellness_answer(rows, resident_name),
        )
    if domain == "incidents":
        return _dispatch_incidents_spec(query, community_id, resident_name, spec)
    return None


# Ordered list of (step_name, callable) so sql_retriever can plug all five
# into its dispatch chain with one import. holistic_status is last because
# its detection is the broadest — let the precise handlers win first.
SENSOR_STEPS = [
    ("incidents", _step_incidents),
    ("vitals", _step_vitals),
    ("sleep", _step_sleep),
    ("wellness", _step_wellness),
    ("holistic_status", _step_holistic_status),
]
