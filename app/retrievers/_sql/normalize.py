"""Query pre-processor: typo correction and ordinal extraction.

Why this exists
---------------
The deterministic SQL handlers are pattern-matched against a fixed
vocabulary ("oldest", "residents", "hypertension", etc.). A one-character
typo turns "oldest" into a word the regex doesn't know, so the entire
question silently falls through to a less reliable path. Caregivers type
fast on phones; treating "holdest" or "residant" as unknown is a UX bug.

This module sits in front of the dispatch chain and:

  1. Normalizes domain-vocabulary typos against a small allowlist
     (`_DOMAIN_VOCAB`). Tight `cutoff=0.85` plus a 4-char minimum keeps it
     from rewriting proper nouns (resident names) accidentally.
  2. Extracts an ordinal rank ("2nd", "second", "third oldest") so the
     ranking handler can OFFSET correctly instead of always returning the
     #1 row.

Both helpers are pure: no DB, no LLM, no state. Tests can call them
directly.
"""
from __future__ import annotations

import difflib
import re

from app.retrievers._sql.constants import _ORDINAL_WORDS


# Vocabulary the chatbot's deterministic handlers care about. Kept small
# on purpose — every entry is a load-bearing word in one of the regex
# tables (ranking terms, profile-rule patterns, text-search rule labels).
_DOMAIN_VOCAB: frozenset[str] = frozenset({
    # Core entities
    "resident", "residents", "patient", "patients",
    # Age / ranking
    "oldest", "youngest", "eldest", "younger", "older", "senior",
    "elder", "elderly", "ages", "age",
    # Profile fields
    "room", "rooms", "flat", "flats", "details", "detail", "profile",
    "profiles", "information", "history", "histories", "medical",
    "medication", "medications",
    # Conditions matched by _RESIDENT_TEXT_SEARCH_RULES
    "hypertension", "diabetes", "prediabetes", "arthritis", "asthma",
    "osteoporosis", "thyroid", "cardiac", "cardiovascular", "surgery",
    "mobility", "chronic",
    # Sensor / metric vocabulary
    "vitals", "heart", "rate", "respiration", "respiratory", "pulse",
    "sleep", "slept", "wellness", "score", "scores", "activity",
    # Incidents / alerts
    "fall", "falls", "fallen", "fell", "incident", "incidents",
    "alert", "alerts", "emergency", "emergencies",
    # Holistic
    "doing", "stable", "okay", "alright", "fine", "well",
    # Common action verbs that anchor handlers
    "list", "show", "display", "find", "tell", "give",
})


def correct_domain_typos(query: str) -> str:
    """Return ``query`` with any close-but-not-exact match of a
    `_DOMAIN_VOCAB` word replaced by its canonical form.

    Rules:
    - Words shorter than 4 chars are left alone (every short word is "close"
      to too many vocabulary entries).
    - Exact matches are left alone (no work to do).
    - Otherwise `difflib.get_close_matches(cutoff=0.85)` proposes one
      replacement; we apply only when there's a single high-confidence
      match.
    - We preserve original case by lowercasing only for the lookup and
      re-emitting the canonical (always-lowercase) form when we substitute.
      That's fine because the downstream handlers all lowercase before
      regex matching anyway.

    The query splitter keeps whitespace and punctuation as separate tokens
    via ``re.split(r"(\\W+)", ...)`` so `re.compile`-style boundaries
    survive the round-trip.
    """
    out: list[str] = []
    for token in re.split(r"(\W+)", query):
        if not token or not token.isalpha() or len(token) < 4:
            out.append(token)
            continue
        low = token.lower()
        if low in _DOMAIN_VOCAB:
            out.append(token)
            continue
        matches = difflib.get_close_matches(low, _DOMAIN_VOCAB, n=1, cutoff=0.85)
        if matches:
            # Substitution is always lowercase — handlers lowercase anyway.
            out.append(matches[0])
        else:
            out.append(token)
    return "".join(out)


# ---------------------------------------------------------------------------
# Ordinal position extraction
# ---------------------------------------------------------------------------

# Numeric ordinal — "2nd", "3rd", "21st", etc. Group(1) captures the int.
_NUMERIC_ORDINAL_RE = re.compile(r"\b(\d+)(?:st|nd|rd|th)\b", re.IGNORECASE)


def extract_ordinal_position(query: str) -> int | None:
    """Return the 1-based ordinal position requested in ``query``, or None.

    Examples:
      "who is the 2nd oldest"     -> 2
      "second youngest resident"  -> 2
      "third oldest"              -> 3
      "21st oldest"               -> 21
      "who is the oldest"         -> None  (no ordinal beyond "the")
    """
    q_lower = query.lower()
    m = _NUMERIC_ORDINAL_RE.search(q_lower)
    if m:
        try:
            n = int(m.group(1))
            return n if n >= 1 else None
        except ValueError:
            return None
    for word, n in _ORDINAL_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", q_lower):
            return n
    return None


# ---------------------------------------------------------------------------
# Position display labels — turn 1/2/3/... into "1st"/"2nd"/"3rd"/...
# ---------------------------------------------------------------------------

def ordinal_label(n: int) -> str:
    """`ordinal_label(2) -> "2nd"`, `ordinal_label(3) -> "3rd"`, etc.

    Handles the 11/12/13 exception correctly (these all take "th", not
    "st"/"nd"/"rd"). Used by formatters to phrase ranking answers.
    """
    if n <= 0:
        return str(n)
    last_two = n % 100
    if 10 <= last_two <= 20:
        suffix = "th"
    else:
        last = n % 10
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(last, "th")
    return f"{n}{suffix}"
