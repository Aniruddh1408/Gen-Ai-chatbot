# ===========================================================================
# This file answers "who needs the most care?" and "who is most at risk?". It
# looks at each resident's recent falls, sleep, vitals, age, and health history,
# gives each person a simple score, and ranks them so staff can see who to check
# first. It can also answer "who has fallen the most?" and honor counts like
# "give me just one person".
# ===========================================================================
"""Care-priority handler — "who needs the most care?", "who is at risk?".

What it does

Given a community, pull every signal the new schema actually has data for
(latest vitals, last night's sleep, latest wellness rollup, recent fall
events, age, medical history) and score each resident with the screening
thresholds in `app/retrievers/_sql/screening.py`. The handler then ranks
residents by composite score and returns a short, reasoned summary.

"""
from __future__ import annotations

import re
from typing import Any

from app.core.db import run_query
from app.core.logger import get_logger
from app.retrievers._sql.names import _extract_excluded_resident_names
from app.retrievers._sql.screening import (
    classify_fall_pattern,
    classify_hr,
    classify_rr,
    classify_sleep_duration,
    classify_wellness_score,
)

logger = get_logger("sql_retriever.care")


# ---------------------------------------------------------------------------
# Detection — phrasings that should land on this handler.
# ---------------------------------------------------------------------------

_CARE_PRIORITY_PATTERNS = [
    r"\bwho\s+needs?\s+(?:the\s+)?(?:most|more|highest|extra)\s+(?:care|attention|monitoring|support)\b",
    # Bare "who needs care" and "who else needs care" (no superlative) should
    # also land here rather than dying in the LLM planner.
    r"\bwho\s+(?:else\s+)?needs?\s+(?:care|attention|monitoring|support|help|watching|checking)\b",
    r"\bwho\s+(?:should|do|i\s+should)\s+(?:i\s+)?(?:focus|prioritize|prioritise|watch|check)\b",
    r"\bwho\s+(?:is|are)\s+(?:the\s+)?(?:most\s+)?(?:at\s+risk|concerning|unwell|critical|priority)\b",
    r"\bwhich\s+resident(?:s)?\s+(?:needs?|should|are)\b.*\b(?:care|attention|priority|risk|watch|check)\b",
    r"\b(?:care|risk|priority)\s+(?:list|ranking|top)\b",
    r"\btop\s+\d+\s+(?:care|priority|risk|concerning)\b",
    r"\b(?:highest|most)\s+(?:care|priority|risk|concern)\b",
    r"\b(?:concerning|unstable|risky|critical)\s+residents?\b",
    r"\bneeds?\s+attention\b",
    r"\bwho\s+(?:is\s+)?(?:doing\s+)?(?:badly|poorly|worst|unwell)\b",
]
_CARE_PRIORITY_RE = re.compile("|".join(_CARE_PRIORITY_PATTERNS), re.IGNORECASE)

# Inverse intent — "who needs the LEAST care / is the most stable / doing best".
# Without this, "who needs the least care?" matched no deterministic handler and
# fell through to the LLM planner, which errored ("technical error").
_LEAST_CARE_PATTERNS = [
    r"\bwho\s+needs?\s+(?:the\s+)?(?:least|less|lowest|fewest|minimal)\s+(?:care|attention|monitoring|support)\b",
    r"\b(?:lowest|least|fewest)\s+(?:care|priority|risk|concern)\b",
    r"\bwho\s+(?:is|are)\s+(?:the\s+)?(?:most\s+)?stable\b",
    r"\bwho\s+(?:is\s+)?(?:doing\s+)?(?:the\s+)?(?:best|well|fine)\b",
    r"\bmost\s+stable\s+residents?\b",
    r"\b(?:least|lowest)\s+(?:care\s+)?priority\b",
]
_LEAST_CARE_RE = re.compile("|".join(_LEAST_CARE_PATTERNS), re.IGNORECASE)


def _care_priority_direction(query: str) -> str | None:
    """Return "least", "most", or None for a care-priority query.

    "least" is checked first because phrasings like "who needs the least care"
    also contain the word "care" that the most-care patterns key on.
    """
    q = query.lower()
    if _LEAST_CARE_RE.search(q):
        return "least"
    if _CARE_PRIORITY_RE.search(q):
        return "most"
    return None


def _detect_care_priority(query: str) -> bool:
    return _care_priority_direction(query) is not None


# How many residents to show. Default 3; honor an explicit count in the query
# so "give one person who needs the most care" returns a single name and
# "top 2 / name three residents" returns exactly that many.
_DEFAULT_CARE_TOP_N = 3
_MAX_CARE_TOP_N = 10
_COUNT_WORDS = {
    "a": 1, "an": 1, "one": 1, "single": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_PERSON_NOUN = r"(?:person|persons|people|resident|residents|patient|patients|name|names|individual|individuals)"


def _requested_count(query: str) -> int | None:
    """Return an explicit resident count from the query, or None for the default.

    Recognises "top N", "N residents", word-numbers ("one person", "name two"),
    and bare singular cues ("just one", "the one", "name one")."""
    q = query.lower()

    m = re.search(r"\btop\s+(\d{1,2})\b", q)
    if m:
        return max(int(m.group(1)), 1)

    m = re.search(rf"\b(\d{{1,2}})\s+{_PERSON_NOUN}\b", q)
    if m:
        return max(int(m.group(1)), 1)

    m = re.search(rf"\b(a|an|one|single|two|three|four|five|six|seven|eight|nine|ten)\s+{_PERSON_NOUN}\b", q)
    if m:
        return _COUNT_WORDS[m.group(1)]

    if re.search(r"\b(?:just|only)\s+one\b|\bthe\s+one\b|\b(?:name|give|show|tell\s+me)\s+one\b|\bsingle\s+(?:most|person|resident)\b", q):
        return 1

    return None


def _care_top_n(query: str) -> int:
    requested = _requested_count(query)
    if requested is None:
        return _DEFAULT_CARE_TOP_N
    return min(max(requested, 1), _MAX_CARE_TOP_N)


# ---------------------------------------------------------------------------
# Data loaders — one query per signal, all community-scoped, returning
# `{resident_id: value}` so the scorer can merge them.
# ---------------------------------------------------------------------------


def _load_residents(community_id: int) -> list[dict[str, Any]]:
    """Base row per resident: id, name, age (derived), medical_history.

    Community scope joins through room_resident_mapping → rooms.community_id
    (resident_profile has no community_id of its own post-migration).
    """
    rows = run_query(
        """
        SELECT rp.id, rp.name, rp.medical_history,
               EXTRACT(YEAR FROM AGE(rp.dob::date))::int AS age
        FROM resident_profile rp
        JOIN room_resident_mapping rrm
          ON rrm.resident_id = rp.id
         AND COALESCE(rrm.is_deleted, false) = false
        JOIN rooms r
          ON r.id = rrm.room_id
         AND COALESCE(r.is_deleted, false) = false
        WHERE r.community_id = %s
          AND COALESCE(rp.is_deleted, false) = false
        ORDER BY rp.id
        """,
        (community_id,),
    )
    return [
        {
            "id": rid,
            "name": name,
            "history": history or "",
            "age": age,
            "hr": None,
            "rr": None,
            "sleep_minutes": None,
            "wellness_min_score": None,
            "wellness_min_type": None,
            "fall_count": 0,
            "confirmed_fall_count": 0,
        }
        for rid, name, history, age in rows
    ]


def _attach_latest_vitals(residents: list[dict[str, Any]], community_id: int) -> None:
    """Most recent (hr, rr) per resident, joined via the board → object →
    rooms chain. Uses a correlated-subquery max() rather than a window
    function so it stays compatible with the existing safety validator."""
    rows = run_query(
        """
        SELECT rp.id, v.hr, v.rr
        FROM vitals v
        JOIN objects o
          ON o.object_id = v.board
         AND COALESCE(o.is_deleted, false) = false
        JOIN rooms r
          ON r.id = o.room_id
         AND COALESCE(r.is_deleted, false) = false
        JOIN room_resident_mapping rrm
          ON rrm.room_id = r.id
         AND COALESCE(rrm.is_deleted, false) = false
        JOIN resident_profile rp
          ON rp.id = rrm.resident_id
         AND COALESCE(rp.is_deleted, false) = false
        WHERE r.community_id = %s
          AND v.ingestion_time = (
            SELECT MAX(v2.ingestion_time) FROM vitals v2 WHERE v2.board = v.board
          )
        """,
        (community_id,),
    )
    by_id = {r["id"]: r for r in residents}
    for rid, hr, rr in rows:
        if rid in by_id:
            by_id[rid]["hr"] = float(hr) if hr is not None else None
            by_id[rid]["rr"] = float(rr) if rr is not None else None


def _attach_last_night_sleep(residents: list[dict[str, Any]], community_id: int) -> None:
    """Total minutes asleep (sum of non-awake stages) on each resident's
    most recent sleep date."""
    rows = run_query(
        """
        SELECT rp.id,
               SUM(EXTRACT(EPOCH FROM (s.end_duration - s.start_duration)) / 60)::int AS asleep_min
        FROM sleep_sessions s
        JOIN objects o
          ON o.object_id = s.board
         AND COALESCE(o.is_deleted, false) = false
        JOIN rooms r
          ON r.id = o.room_id
         AND COALESCE(r.is_deleted, false) = false
        JOIN room_resident_mapping rrm
          ON rrm.room_id = r.id
         AND COALESCE(rrm.is_deleted, false) = false
        JOIN resident_profile rp
          ON rp.id = rrm.resident_id
         AND COALESCE(rp.is_deleted, false) = false
        WHERE r.community_id = %s
          AND s.sleep_stage::text != 'awake'
          AND s.start_duration::date = (
            SELECT MAX(s2.start_duration::date)
            FROM sleep_sessions s2 WHERE s2.board = s.board
          )
        GROUP BY rp.id
        """,
        (community_id,),
    )
    by_id = {r["id"]: r for r in residents}
    for rid, minutes in rows:
        if rid in by_id:
            by_id[rid]["sleep_minutes"] = int(minutes) if minutes is not None else None


def _attach_latest_wellness_weakest(residents: list[dict[str, Any]], community_id: int) -> None:
    """The weakest (lowest-score) wellness type on each resident's most
    recent wellness date. Captures both the score and which type it was so
    the rationale line can name it."""
    rows = run_query(
        """
        SELECT rp.id, wm.type::text, wm.score
        FROM wellness_metrics wm
        JOIN objects o
          ON o.object_id = wm.board
         AND COALESCE(o.is_deleted, false) = false
        JOIN rooms r
          ON r.id = o.room_id
         AND COALESCE(r.is_deleted, false) = false
        JOIN room_resident_mapping rrm
          ON rrm.room_id = r.id
         AND COALESCE(rrm.is_deleted, false) = false
        JOIN resident_profile rp
          ON rp.id = rrm.resident_id
         AND COALESCE(rp.is_deleted, false) = false
        WHERE r.community_id = %s
          AND wm.date = (
            SELECT MAX(wm2.date) FROM wellness_metrics wm2 WHERE wm2.board = wm.board
          )
        """,
        (community_id,),
    )
    by_id = {r["id"]: r for r in residents}
    for rid, wtype, score in rows:
        if rid not in by_id:
            continue
        r = by_id[rid]
        s = float(score) if score is not None else None
        if s is None:
            continue
        if r["wellness_min_score"] is None or s < r["wellness_min_score"]:
            r["wellness_min_score"] = s
            r["wellness_min_type"] = wtype


def _attach_fall_counts(residents: list[dict[str, Any]], community_id: int) -> None:
    """Fall and confirmed-fall counts per resident in the last 7 days."""
    rows = run_query(
        """
        SELECT rp.id,
               COUNT(*) FILTER (
                 WHERE i.event_category::text IN
                       ('fall_alert', 'confirmed_fall', 'suspected_alert')
               ) AS fall_count,
               COUNT(*) FILTER (
                 WHERE i.event_category::text = 'confirmed_fall'
               ) AS confirmed_count
        FROM incidents i
        JOIN rooms r
          ON r.id = i.room_id
         AND COALESCE(r.is_deleted, false) = false
        JOIN room_resident_mapping rrm
          ON rrm.room_id = r.id
         AND COALESCE(rrm.is_deleted, false) = false
        JOIN resident_profile rp
          ON rp.id = rrm.resident_id
         AND COALESCE(rp.is_deleted, false) = false
        WHERE r.community_id = %s
          AND i.event_time > now() - INTERVAL '7 days'
          AND COALESCE(i.is_deleted, false) = false
        GROUP BY rp.id
        """,
        (community_id,),
    )
    by_id = {r["id"]: r for r in residents}
    for rid, fc, cc in rows:
        if rid in by_id:
            by_id[rid]["fall_count"] = int(fc or 0)
            by_id[rid]["confirmed_fall_count"] = int(cc or 0)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

# Chronic conditions tracked by the screening rules. Kept aligned with
# _RESIDENT_TEXT_SEARCH_RULES so the same word that lets a caregiver query
# for a condition is the one that contributes here.
_CHRONIC_TERMS: tuple[str, ...] = (
    "diabetes", "hypertension", "cardiac", "cardiovascular",
    "post-surgery", "post surgery", "asthma", "osteoporosis", "thyroid",
)


def _score_resident(r: dict[str, Any]) -> tuple[int, list[str]]:
    """Return (composite_score, ordered_reasons) for one resident.

    Reasons are added in priority order (heaviest signal first) so the
    formatter can show the top 2-3 without losing the most important one.
    """
    score = 0
    reasons: list[str] = []

    # --- Falls (heaviest signal) ----------------------------------------------
    fall_reading = classify_fall_pattern(r["fall_count"], r["confirmed_fall_count"])
    if fall_reading and fall_reading.band == "concerning":
        score += 5
        n = r["confirmed_fall_count"]
        reasons.append(f"{n} confirmed fall{'s' if n != 1 else ''} this week")
    elif fall_reading and fall_reading.band == "elevated":
        if r["fall_count"] >= 2:
            score += 4
            reasons.append(f"{r['fall_count']} recent fall alerts")
        else:
            score += 3
            reasons.append("recent fall alert")

    # --- Vitals ----------------------------------------------------------------
    hr_reading = classify_hr(r["hr"])
    if hr_reading and hr_reading.band == "concerning":
        score += 3
        reasons.append(f"HR {r['hr']:.0f} bpm — concerning")
    elif hr_reading and hr_reading.band in ("low", "elevated", "high"):
        score += 1
        reasons.append(f"HR {r['hr']:.0f} bpm — {hr_reading.band}")

    rr_reading = classify_rr(r["rr"])
    if rr_reading and rr_reading.band == "concerning":
        score += 3
        reasons.append(f"RR {r['rr']:.0f}/min — concerning")
    elif rr_reading and rr_reading.band in ("low", "elevated", "high"):
        score += 1
        reasons.append(f"RR {r['rr']:.0f}/min — {rr_reading.band}")

    # --- Sleep -----------------------------------------------------------------
    sleep_reading = classify_sleep_duration(r["sleep_minutes"])
    if sleep_reading and sleep_reading.band == "concerning":
        score += 3
        reasons.append("very short sleep last night")
    elif sleep_reading and sleep_reading.band == "low":
        score += 1
        reasons.append("reduced sleep last night")

    # --- Wellness --------------------------------------------------------------
    wellness_reading = classify_wellness_score(r["wellness_min_score"])
    if wellness_reading and wellness_reading.band == "concerning":
        score += 3
        which = r["wellness_min_type"] or "wellness"
        reasons.append(f"{which} score low ({r['wellness_min_score']:.0f})")
    elif wellness_reading and wellness_reading.band == "elevated":
        score += 1
        which = r["wellness_min_type"] or "wellness"
        reasons.append(f"{which} score borderline ({r['wellness_min_score']:.0f})")

    # --- Age -------------------------------------------------------------------
    age = r["age"]
    if age is not None:
        if age >= 90:
            score += 2
            reasons.append(f"age {age}")
        elif age >= 85:
            score += 1

    # --- Chronic medical history ----------------------------------------------
    history = (r["history"] or "").lower()
    present = [term for term in _CHRONIC_TERMS if term in history]
    # De-duplicate "cardiac" / "cardiovascular" pair — they're the same signal.
    if "cardiac" in present and "cardiovascular" in present:
        present.remove("cardiovascular")
    if "post-surgery" in present and "post surgery" in present:
        present.remove("post surgery")
    score += len(present)
    if present:
        # Show the first two only; the score already reflects the rest.
        reasons.append("chronic: " + ", ".join(present[:2]))

    return score, reasons


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------


def _format_care_priority(
    scored: list[tuple[int, list[str], dict[str, Any]]],
    top_n: int = 3,
) -> str:
    """Render the top-N care-priority list with a leading verdict sentence.

    ``scored`` is sorted DESC by score already. Residents with score 0 are
    skipped — they have no signal worth surfacing.
    """
    flagged = [item for item in scored if item[0] > 0]
    if not flagged:
        return (
            "No residents are showing concerning signals right now — "
            "the community looks stable across vitals, sleep, wellness, and falls."
        )

    leader_score, leader_reasons, leader = flagged[0]
    if leader_score >= 8:
        verdict = f"{leader['name']} needs the most attention right now."
    elif leader_score >= 4:
        verdict = f"{leader['name']} is the top care priority today."
    else:
        verdict = (
            f"{leader['name']} carries the highest care signal, "
            "though everyone is mostly stable."
        )

    lines = [verdict, ""]
    shown = flagged[:top_n]
    for score, reasons, r in shown:
        reason_text = "; ".join(reasons[:3]) if reasons else "multiple mild signals"
        age_text = f", age {r['age']}" if r["age"] is not None else ""
        lines.append(f"- {r['name']}{age_text} — score {score}: {reason_text}")
    return "\n".join(lines)


def _format_care_priority_least(
    scored: list[tuple[int, list[str], dict[str, Any]]],
    top_n: int = 3,
) -> str:
    """Render the LOWEST-care residents (most stable). ``scored`` is sorted
    ASC by score already (lowest first)."""
    if not scored:
        return "No residents on file in this community."

    leader_score, _leader_reasons, leader = scored[0]
    if leader_score == 0:
        verdict = (
            f"{leader['name']} needs the least care right now — "
            "no concerning signals across vitals, sleep, wellness, or falls."
        )
    else:
        verdict = f"{leader['name']} needs the least care relative to others in the community."

    lines = [verdict, ""]
    for score, reasons, r in scored[:top_n]:
        age_text = f", age {r['age']}" if r["age"] is not None else ""
        if score == 0:
            detail = "stable across vitals, sleep, wellness, and falls"
        else:
            detail = "; ".join(reasons[:3]) if reasons else "mostly stable"
        lines.append(f"- {r['name']}{age_text} — score {score}: {detail}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dispatch entry point
# ---------------------------------------------------------------------------


def _step_care_priority(query: str, community_id: int) -> dict | None:
    """Detect care-priority intent, load every signal, rank, return."""
    direction = _care_priority_direction(query)
    if direction is None:
        return None

    residents = _load_residents(community_id)
    if not residents:
        return {
            "query": query,
            "plan": {"_macro": "care_priority"},
            "result": [],
            "answer": "No residents on file in this community.",
        }

    # "who else needs care / who needs care other than A, B, C" — drop every
    # resident already named so the ranking reflects everyone *else*.
    exclude_names = _extract_excluded_resident_names(query)
    if exclude_names:
        needles = [n.lower() for n in exclude_names]
        residents = [
            r for r in residents
            if not any(n in (r["name"] or "").lower() for n in needles)
        ]
        if not residents:
            return {
                "query": query,
                "plan": {"_macro": "care_priority", "exclude_name": exclude_names[0]},
                "result": [],
                "answer": "No other residents are on file in this community.",
            }

    _attach_latest_vitals(residents, community_id)
    _attach_last_night_sleep(residents, community_id)
    _attach_latest_wellness_weakest(residents, community_id)
    _attach_fall_counts(residents, community_id)

    scored = [
        (score, reasons, r)
        for r in residents
        for score, reasons in [_score_resident(r)]
    ]
    top_n = _care_top_n(query)
    if direction == "least":
        # Lowest score first (most stable). Tie-break by name for determinism.
        scored.sort(key=lambda item: (item[0], item[2]["name"]))
        answer = _format_care_priority_least(scored, top_n=top_n)
    else:
        scored.sort(key=lambda item: (-item[0], item[2]["name"]))
        answer = _format_care_priority(scored, top_n=top_n)

    logger.info(
        "Deterministic care-priority plan: direction=%s leader=%s score=%s",
        direction,
        scored[0][2]["name"] if scored else None,
        scored[0][0] if scored else None,
    )
    return {
        "query": query,
        "plan": {
            "_macro": "care_priority",
            "direction": direction,
            "exclude_name": exclude_names[0] if exclude_names else None,
            "leader_name": scored[0][2]["name"] if scored else None,
            "leader_score": scored[0][0] if scored else None,
        },
        "result": [
            {"name": r["name"], "score": s, "reasons": reasons}
            for s, reasons, r in scored
        ],
        "answer": answer,
    }


# ===========================================================================
# Resident comparison — "compare the sleep of X and Y", "who's doing better,
# X or Y?", "X vs Y". Reuses the same per-resident signal loaders and the
# _score_resident attention score, but scoped to the named residents and
# rendered side by side with a verdict on who's better / who needs attention.
# ===========================================================================

# A comparison needs either an explicit compare cue or a health-metric word,
# AND (checked in the handler) two or more named residents. The two-name
# requirement is the real signal — it's phrasing-robust because it keys on the
# roster names, not on how the question is worded.
_COMPARE_CUE_RE = re.compile(
    r"\b(?:compare|comparison|compared|comparing|versus|vs\.?|"
    r"side[-\s]by[-\s]side|stacks?\s+up|against\s+each\s+other|"
    r"who(?:'s| is| are)?\s+(?:doing\s+)?(?:better|worse|healthier|best|worst)|"
    r"better\s+or\s+worse)\b",
    re.IGNORECASE,
)
_COMPARE_METRIC_RE = re.compile(
    r"\b(?:sleep|slept|sleeping|vitals?|heart\s*rate|hr|pulse|respiration|"
    r"wellness|well[-\s]?being|wellbeing|fall|falls|fell|incident|incidents|"
    r"health|metrics?|doing|attention|condition|overall)\b",
    re.IGNORECASE,
)


def _attach_avg_sleep(residents: list[dict[str, Any]], community_id: int, nights: int = 7) -> None:
    """Average nightly minutes asleep (non-awake stages) over the last
    ``nights`` nights — a fairer comparison signal than a single night. Stored
    back into ``sleep_minutes`` so _score_resident reflects typical sleep."""
    rows = run_query(
        f"""
        SELECT rp.id,
               (SUM(EXTRACT(EPOCH FROM (s.end_duration - s.start_duration)) / 60)
                / NULLIF(COUNT(DISTINCT (s.start_duration - INTERVAL '12 hours')::date), 0)
               )::int AS avg_asleep_min
        FROM sleep_sessions s
        JOIN objects o
          ON o.object_id = s.board AND COALESCE(o.is_deleted, false) = false
        JOIN rooms r
          ON r.id = o.room_id AND COALESCE(r.is_deleted, false) = false
        JOIN room_resident_mapping rrm
          ON rrm.room_id = r.id AND COALESCE(rrm.is_deleted, false) = false
        JOIN resident_profile rp
          ON rp.id = rrm.resident_id AND COALESCE(rp.is_deleted, false) = false
        WHERE r.community_id = %s
          AND s.sleep_stage::text != 'awake'
          AND s.start_duration > now() - INTERVAL '{nights + 1} days'
        GROUP BY rp.id
        """,
        (community_id,),
    )
    by_id = {r["id"]: r for r in residents}
    for rid, minutes in rows:
        if rid in by_id:
            by_id[rid]["sleep_minutes"] = int(minutes) if minutes is not None else None


def _hm(minutes: int | None) -> str:
    if not minutes:
        return "—"
    h, m = divmod(int(minutes), 60)
    if h and m:
        return f"{h}h {m}m"
    return f"{h}h" if h else f"{m}m"


def _join_names(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _format_resident_comparison(scored: list[tuple[int, list[str], dict[str, Any]]]) -> str:
    """Side-by-side per-resident block plus a verdict. ``scored`` is in the
    order the residents were named; the verdict is derived from the attention
    score (lower = doing better)."""
    names = [r["name"] for _, _, r in scored]
    lines = [f"Comparing {_join_names(names)} (recent data, last 7 days):", ""]

    for score, _reasons, r in scored:
        sleep = f"{_hm(r['sleep_minutes'])}/night" if r["sleep_minutes"] else "no recent sleep data"
        hr = f"{r['hr']:.0f} bpm" if r["hr"] is not None else "—"
        rr = f"{r['rr']:.0f}/min" if r["rr"] is not None else "—"
        if r["wellness_min_score"] is not None:
            well = f"{r['wellness_min_type'] or 'wellness'} {r['wellness_min_score']:.0f} (weakest)"
        else:
            well = "—"
        falls = r["fall_count"]
        fall_txt = f"{falls} fall{'s' if falls != 1 else ''}" if falls else "no falls"
        lines.append(f"{r['name']} — concern score {score}")
        lines.append(
            f"  Sleep {sleep} · heart rate {hr} · respiration {rr} · "
            f"wellness {well} · {fall_txt} (7d)"
        )
        lines.append("")

    best = min(scored, key=lambda i: i[0])
    worst = max(scored, key=lambda i: i[0])
    if best[0] == worst[0]:
        # Tie on concern score — separate by typical sleep, then wellness.
        ranked = sorted(
            scored,
            key=lambda i: (-(i[2]["sleep_minutes"] or 0), -(i[2]["wellness_min_score"] or 0)),
        )
        if best[0] == 0:
            verdict = (
                "All look stable right now — no concerning signals across sleep, "
                f"vitals, wellness, or falls. {ranked[0][2]['name']} edges ahead on "
                f"sleep and wellness; {ranked[-1][2]['name']} is the one to keep a "
                "light eye on."
            )
        else:
            verdict = (
                f"{ranked[0][2]['name']} and {ranked[-1][2]['name']} carry similar "
                "concern levels — review both."
            )
    else:
        worst_reasons = "; ".join(worst[1][:2]) if worst[1] else "more signals worth watching"
        verdict = (
            f"{best[2]['name']} is doing better overall (lowest concern score). "
            f"{worst[2]['name']} needs more attention — {worst_reasons}."
        )
    lines.append(verdict)
    return "\n".join(lines)


def _step_compare_residents(query: str, community_id: int) -> dict | None:
    """Compare two or more named residents across all metrics, with a verdict."""
    q = query.lower()
    if not (_COMPARE_CUE_RE.search(q) or _COMPARE_METRIC_RE.search(q)):
        return None

    # Lazy import to avoid a cycle (sql_retriever imports this module).
    from app.retrievers.sql_retriever import _find_resident_names_in_query

    found = _find_resident_names_in_query(query, community_id)
    seen: set[str] = set()
    names = [n for n in found if not (n in seen or seen.add(n))]
    if len(names) < 2:
        return None  # not a multi-resident question — let other handlers run

    residents = _load_residents(community_id)
    targets = [r for r in residents if r["name"] in names]
    if len(targets) < 2:
        return None
    # Present residents in the order they were named in the question.
    order = {n: i for i, n in enumerate(names)}
    targets.sort(key=lambda r: order.get(r["name"], len(order)))

    _attach_latest_vitals(targets, community_id)
    _attach_avg_sleep(targets, community_id)
    _attach_latest_wellness_weakest(targets, community_id)
    _attach_fall_counts(targets, community_id)

    scored = [(s, reasons, r) for r in targets for s, reasons in [_score_resident(r)]]
    logger.info(
        "Deterministic resident-comparison plan: residents=%s",
        [r["name"] for r in targets],
    )
    return {
        "query": query,
        "plan": {"_macro": "compare_residents", "residents": [r["name"] for r in targets]},
        "result": [
            {"name": r["name"], "score": s, "reasons": reasons} for s, reasons, r in scored
        ],
        "answer": _format_resident_comparison(scored),
    }


# ---------------------------------------------------------------------------
# Fall ranking — "who has had the most falls", "who fell the most"
# ---------------------------------------------------------------------------

_FALL_RANKING_PATTERNS = [
    r"\bwho\s+(?:has\s+(?:had\s+)?|had\s+)?(?:the\s+)?(?:most|highest|fewest)\s+falls?\b",
    r"\bwho\s+(?:has\s+)?fell\s+(?:the\s+)?most\b",
    r"\b(?:most|highest)\s+falls?\s+(?:among|in)\b",
    r"\bfall\s+(?:count|ranking|rankings|leaderboard)\b",
    r"\bwho\s+falls?\s+(?:the\s+)?most\b",
]
_FALL_RANKING_RE = re.compile("|".join(_FALL_RANKING_PATTERNS), re.IGNORECASE)


def _detect_fall_ranking(query: str) -> bool:
    return bool(_FALL_RANKING_RE.search(query.lower()))


def _step_fall_ranking(query: str, community_id: int) -> dict | None:
    """Group fall-shaped incidents by resident and rank by count.

    Window is 30 days by default — wide enough that a single weekly fall
    doesn't dominate, narrow enough that ancient history doesn't either.
    """
    if not _detect_fall_ranking(query):
        return None

    # "who else fell the most / who fell the most other than A, B" — exclude the
    # resident(s) in focus from the leaderboard.
    exclude_names = _extract_excluded_resident_names(query)
    conditions = [
        "r.community_id = %s",
        "i.event_category::text IN ('fall_alert', 'confirmed_fall', 'suspected_alert')",
        "i.event_time > now() - INTERVAL '30 days'",
        "COALESCE(i.is_deleted, false) = false",
    ]
    params: list = [community_id]
    if exclude_names:
        conditions.append("rp.name IS NOT NULL")
        for name in exclude_names:
            conditions.append("rp.name NOT ILIKE %s")
            params.append(f"%{name}%")
    exclude_name = exclude_names[0] if exclude_names else None

    rows = run_query(
        f"""
        SELECT rp.name,
               COUNT(*) AS fall_count,
               COUNT(*) FILTER (
                 WHERE i.event_category::text = 'confirmed_fall'
               ) AS confirmed_count,
               MAX(i.event_time) AS most_recent
        FROM incidents i
        JOIN rooms r
          ON r.id = i.room_id
         AND COALESCE(r.is_deleted, false) = false
        JOIN room_resident_mapping rrm
          ON rrm.room_id = r.id
         AND COALESCE(rrm.is_deleted, false) = false
        JOIN resident_profile rp
          ON rp.id = rrm.resident_id
         AND COALESCE(rp.is_deleted, false) = false
        WHERE {' AND '.join(conditions)}
        GROUP BY rp.name
        ORDER BY fall_count DESC, confirmed_count DESC, rp.name ASC
        LIMIT 5
        """,
        params,
    )

    if not rows:
        empty = (
            f"No other residents have recorded a fall in the last 30 days."
            if exclude_name
            else "No fall events recorded in this community in the last 30 days."
        )
        return {
            "query": query,
            "plan": {"_macro": "fall_ranking", "exclude_name": exclude_name},
            "result": rows,
            "answer": empty,
        }

    # Honor an explicit count ("name one who fell the most"); default shows up
    # to the full top-5 leaderboard.
    top_n = _care_top_n(query)
    shown = rows[:top_n]

    top_name, top_count, top_confirmed, _top_time = rows[0]
    among = "among other residents" if exclude_name else "in this community"
    lead = (
        f"{top_name} has had the most falls {among} over the last 30 days "
        f"— {top_count} event{'s' if top_count != 1 else ''}"
    )
    lead += f" ({top_confirmed} confirmed)." if top_confirmed else "."

    lines = [lead]
    if len(shown) > 1:
        lines.append("")
        for name, count, confirmed, _time in shown:
            suffix = f" ({confirmed} confirmed)" if confirmed else ""
            lines.append(f"- {name}: {count} fall{'s' if count != 1 else ''}{suffix}")
    return {
        "query": query,
        "plan": {"_macro": "fall_ranking", "leader_name": top_name, "exclude_name": exclude_name},
        "result": rows,
        "answer": "\n".join(lines),
    }


# Ordered list for the sql_retriever dispatch chain. Care priority is the
# more specific intent and should win over the generic resident-aggregate
# path; fall ranking should similarly win over the incidents listing.
CARE_STEPS = [
    ("care_priority", _step_care_priority),
    ("fall_ranking", _step_fall_ranking),
]
