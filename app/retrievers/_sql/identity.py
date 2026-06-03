# ===========================================================================
# This file decides EXACTLY which resident you mean. If two residents share a
# first name, it asks "which one did you mean?" instead of guessing. If you
# made a small typo in the name, it finds the closest real match. If nobody
# matches, it says so honestly. This is the safeguard that stops the assistant
# from accidentally answering about the wrong person.
# ===========================================================================
"""Central resident identity resolver.

Single place that turns a free-text query into a *decision* about which
resident (if any) it refers to, inside one community. Every resident-specific
path (profile lookups, sensor/vitals, incidents, RAG) should resolve identity
here first instead of re-implementing partial/fuzzy name matching — that
duplication is exactly how wrong-resident and silent-ambiguity bugs creep in.

Contract
--------
resolve_resident_identity(query, community_id) -> dict with one of:

  {"status": "exact_id",      "resident_id": int, "name": str}
  {"status": "exact_name",    "resident_id": int, "name": str}
  {"status": "unique_partial","resident_id": int, "name": str, "matched_from": str}
  {"status": "unique_fuzzy",  "resident_id": int, "name": str, "matched_from": str, "score": float}
  {"status": "ambiguous",     "candidates": [{"resident_id": int, "name": str}, ...]}
  {"status": "not_found"}

Safety rules (mirrors the hardening spec):
  1. Exact resident-id match wins.
  2. Exact full-name match wins (case-insensitive).
  3. A first-name / partial match resolves ONLY when exactly one resident matches.
  4. Multiple matches -> ambiguous (ask the caller to clarify); never silently pick.
  5. Fuzzy matching only when no exact/partial match exists AND best score >= 0.90
     AND best beats the runner-up by >= 0.08 AND the candidate looks like a name.
  6. Common words ("resident", "room", "fall", "oldest", ...) never resolve as names.
  7. No safe match -> not_found.

Pure logic given an injected ``roster`` (list of (resident_id, name)); only the
default roster fetch touches the DB, so the matching rules are unit-testable
offline.
"""
from __future__ import annotations

import difflib

from app.core.db import run_query
from app.core.logger import get_logger
from app.retrievers._sql.constants import _RESIDENT_NAME_STOPWORDS
from app.retrievers._sql.names import (
    _extract_resident_id,
    _extract_resident_name,
    _extract_resident_name_fragment,
)

logger = get_logger("identity")

# Strict thresholds for the fuzzy tier (see rule 5).
_FUZZY_MIN_SCORE = 0.90
_FUZZY_MARGIN = 0.08


def _fetch_community_roster(community_id: int) -> list[tuple[int, str]]:
    """Return [(resident_id, name)] for non-deleted residents in this community.

    Community scope joins through rooms because resident_profile has no
    community_id of its own. Kept as a standalone function so tests can
    monkeypatch it without a DB.
    """
    rows = run_query(
        """
        SELECT resident_profile.id, resident_profile.name
        FROM resident_profile
        JOIN room_resident_mapping rrm
          ON rrm.resident_id = resident_profile.id
         AND COALESCE(rrm.is_deleted, false) = false
        JOIN rooms rm
          ON rm.id = rrm.room_id
         AND COALESCE(rm.is_deleted, false) = false
        WHERE rm.community_id = %s
          AND COALESCE(resident_profile.is_deleted, false) = false
        """,
        (community_id,),
    )
    roster: list[tuple[int, str]] = []
    for row in rows or []:
        if not row or row[1] in (None, ""):
            continue
        try:
            roster.append((int(row[0]), str(row[1]).strip()))
        except (TypeError, ValueError):
            continue
    return roster


def _candidate_name(query: str) -> str | None:
    """Best resident-name candidate string from the query (full or fragment)."""
    return _extract_resident_name(query) or _extract_resident_name_fragment(query)


def _looks_like_person_name(candidate: str) -> bool:
    """Reject obvious non-name words so 'oldest'/'room'/'fall' never resolve."""
    tokens = [t.strip(" .,?!()'\"").lower() for t in candidate.split()]
    tokens = [t for t in tokens if t]
    if not tokens:
        return False
    return all(t not in _RESIDENT_NAME_STOPWORDS for t in tokens)


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _best_fuzzy(cand_lower: str, roster: list[tuple[int, str]], single_token: bool):
    """Return (best_score, best_resident, second_score) over the roster.

    Score per resident is the max of full-name similarity and (for a
    single-token candidate) first-name similarity.
    """
    scored: list[tuple[float, tuple[int, str]]] = []
    for rid, name in roster:
        name_lower = name.lower()
        score = _ratio(cand_lower, name_lower)
        if single_token:
            first = name_lower.split()[0] if name_lower.split() else name_lower
            score = max(score, _ratio(cand_lower, first))
        scored.append((score, (rid, name)))
    if not scored:
        return 0.0, None, 0.0
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_resident = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    return best_score, best_resident, second_score


def resolve_resident_identity(
    query: str,
    community_id: int,
    *,
    roster: list[tuple[int, str]] | None = None,
) -> dict:
    """Resolve which resident ``query`` refers to within ``community_id``."""
    if roster is None:
        roster = _fetch_community_roster(community_id)

    by_id = {rid: name for rid, name in roster}

    # 1. Exact resident-id.
    rid = _extract_resident_id(query)
    if rid is not None:
        if rid in by_id:
            return {"status": "exact_id", "resident_id": rid, "name": by_id[rid]}
        return {"status": "not_found"}

    if not roster:
        return {"status": "not_found"}

    candidate = _candidate_name(query)
    if not candidate or not _looks_like_person_name(candidate):
        return {"status": "not_found"}

    cand_lower = candidate.lower().strip()
    cand_tokens = cand_lower.split()
    single_token = len(cand_tokens) == 1

    # 2. Exact full-name (case-insensitive).
    exact = [(rid, name) for rid, name in roster if name.lower() == cand_lower]
    if len(exact) == 1:
        return {"status": "exact_name", "resident_id": exact[0][0], "name": exact[0][1]}
    if len(exact) > 1:
        return _ambiguous(exact)

    # 3. Unique partial — first-name match, only for a single-token candidate.
    if single_token:
        partial = [
            (rid, name)
            for rid, name in roster
            if name.lower().split() and name.lower().split()[0] == cand_lower
        ]
        if len(partial) == 1:
            return {
                "status": "unique_partial",
                "resident_id": partial[0][0],
                "name": partial[0][1],
                "matched_from": candidate,
            }
        if len(partial) > 1:
            return _ambiguous(partial)

    # 5. Fuzzy — strict score + margin + uniqueness.
    best_score, best_resident, second_score = _best_fuzzy(cand_lower, roster, single_token)
    if best_resident is not None and best_score >= _FUZZY_MIN_SCORE:
        if (best_score - second_score) >= _FUZZY_MARGIN:
            return {
                "status": "unique_fuzzy",
                "resident_id": best_resident[0],
                "name": best_resident[1],
                "matched_from": candidate,
                "score": round(best_score, 3),
            }
        # Two near-equally-close names — clarify instead of guessing.
        close = [
            (rid, name)
            for rid, name in roster
            if _best_fuzzy(cand_lower, [(rid, name)], single_token)[0] >= _FUZZY_MIN_SCORE
        ]
        if len(close) > 1:
            return _ambiguous(close)

    return {"status": "not_found"}


def _ambiguous(candidates: list[tuple[int, str]]) -> dict:
    # Stable, name-sorted candidate list for a deterministic clarification prompt.
    ordered = sorted({(rid, name) for rid, name in candidates}, key=lambda c: c[1].lower())
    return {
        "status": "ambiguous",
        "candidates": [{"resident_id": rid, "name": name} for rid, name in ordered],
    }


# ---------------------------------------------------------------------------
# Standard user-facing response strings (Phase 11 normalization).
# ---------------------------------------------------------------------------

def no_matching_resident() -> str:
    return "I couldn't find a matching resident in this community."


def unavailable() -> str:
    return "I couldn't find that information in the available records."


def clarify_resident(candidates: list[dict]) -> str:
    names = [c["name"] for c in candidates if c.get("name")]
    if not names:
        return no_matching_resident()
    if len(names) == 1:
        return f"Did you mean {names[0]}?"
    listed = ", ".join(names)
    return f"Which resident do you mean? I found: {listed}."
