"""Roster-grounded answer verification — the structural backstop.

Why this exists
---------------
Deterministic handlers and the coverage matrix protect the *known* question
space. They cannot protect the *unknown* space: a never-anticipated phrasing
escapes every handler, falls to the LLM SQL planner, and we synthesize prose
from whatever rows return — which is where a confident wrong-resident or
hallucinated answer is born.

This module validates the OUTPUT against ground truth instead of trying to
anticipate the input. It extracts the resident names an answer asserts and
checks each one against the caller's community roster. If an answer names
someone who isn't a resident in this community, we don't trust it — the caller
declines rather than return a possibly-fabricated fact.

This closes the PHI / cross-resident leak gap documented in
app/agents/guardrails.py, and it works for any question, any phrasing, any
route, because it only looks at what the answer claims.

Fail-open on infrastructure errors (no roster ⇒ no decision): a DB hiccup must
not start blocking every answer. The risk it guards (a fabricated name) only
exists when we *have* a roster to contradict it.
"""
from __future__ import annotations

import re

from app.core.community import LOCAL_DEMO_COMMUNITIES
from app.core.logger import get_logger
from app.retrievers._sql.names import _is_plausible_resident_name

logger = get_logger("grounding")


# A full person-name (2-3 capitalized words) in a NAME position only — i.e.
# immediately followed by a strong name signal: "(", ", age/room/ID", " is", or
# possessive "'s". Anchoring to name positions keeps capitalized medical terms
# ("Type 2 Diabetes", "Chronic Kidney Disease") from being mistaken for names.
_NAME_POSITION_RE = re.compile(
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})"
    r"(?=\s*\(|,\s*(?:age|room|ID|id)\b|\s+is\b|'s\b)"
)

_KNOWN_COMMUNITY_LOWER = {name.lower() for name in LOCAL_DEMO_COMMUNITIES.values()}


def _extract_asserted_names(text: str) -> set[str]:
    """Resident-looking full names the answer states in a name position."""
    names: set[str] = set()
    for match in _NAME_POSITION_RE.finditer(text or ""):
        candidate = match.group(1).strip()
        if candidate and _is_plausible_resident_name(candidate):
            names.add(candidate)
    return names


def foreign_resident_names(
    answer: str,
    community_id: int,
    *,
    roster: list[tuple[int, str]] | None = None,
) -> list[str]:
    """Return resident names the answer asserts that are NOT in this community.

    Empty list means "nothing contradicts the roster" (grounded, or no names at
    all). Fails open: any roster-fetch error returns [] so a DB problem can't
    start blocking answers.
    """
    candidates = _extract_asserted_names(answer)
    if not candidates:
        return []

    try:
        if roster is None:
            # Imported lazily so this module stays usable (and importable) even
            # where the DB layer isn't configured — the fetch itself is the only
            # part that needs a database.
            from app.retrievers._sql.identity import _fetch_community_roster
            roster = _fetch_community_roster(community_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Grounding roster fetch failed: {exc}")
        return []

    roster_lower = {name.lower() for _id, name in roster}
    if not roster_lower:
        # No roster to contradict the answer — don't guess. Fail open.
        return []

    foreign: list[str] = []
    for candidate in candidates:
        cl = candidate.lower()
        if cl in roster_lower or cl in _KNOWN_COMMUNITY_LOWER:
            continue
        # Tolerate a partial of a real roster name (e.g. answer omits/adds a
        # middle name) so we only flag genuinely unknown people.
        if any(cl in name or name in cl for name in roster_lower):
            continue
        foreign.append(candidate)
    return foreign


def is_grounded(answer: str, community_id: int, *, roster=None) -> bool:
    """True when the answer asserts no resident outside this community's roster."""
    return not foreign_resident_names(answer, community_id, roster=roster)
