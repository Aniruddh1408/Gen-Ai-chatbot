"""Resident name / id / community-reference extraction helpers.

Pure text logic (no DB/LLM). Re-exported from sql_retriever.py.
"""
import re

from app.core.community import LOCAL_DEMO_COMMUNITIES, get_community_name
from app.retrievers._sql.constants import (
    _KNOWN_COMMUNITY_NAMES,
    _NON_RESIDENT_NAME_CANDIDATES,
    _RESIDENT_NAME_STOPWORDS,
)


def _is_plausible_resident_name(candidate: str) -> bool:
    words = [word.strip(" .,?!():'\"").lower() for word in candidate.split()]
    words = [word for word in words if word]
    if len(words) < 2:
        return False
    if any(word in _RESIDENT_NAME_STOPWORDS for word in words):
        return False
    return True


def _is_plausible_resident_name_fragment(candidate: str) -> bool:
    words = [word.strip(" .,?!():'\"").lower() for word in candidate.split()]
    words = [word for word in words if word]
    if len(words) != 1:
        return False
    word = words[0]
    if len(word) < 2 or word in _RESIDENT_NAME_STOPWORDS:
        return False
    return True


def _detect_known_community_reference(query: str) -> tuple[int, str] | None:
    q_lower = query.lower()
    for community_id, community_name in LOCAL_DEMO_COMMUNITIES.items():
        pattern = rf"(?<!\w){re.escape(community_name.lower())}(?!\w)"
        if re.search(pattern, q_lower):
            return community_id, community_name
    return None


def _is_known_community_name(candidate: str) -> bool:
    candidate_lower = candidate.lower().strip(" .,?!")
    if candidate_lower in _KNOWN_COMMUNITY_NAMES:
        return True
    return any(
        community_name.startswith(candidate_lower)
        for community_name in _KNOWN_COMMUNITY_NAMES
    )


def _is_known_community_name_fragment(candidate: str, query: str) -> bool:
    candidate_lower = candidate.lower().strip(" .,?!")
    if not candidate_lower:
        return False
    reference = _detect_known_community_reference(query)
    if not reference:
        return False
    _community_id, community_name = reference
    return candidate_lower in community_name.lower().split()


def _community_scope_mismatch_response(query: str, community_id: int) -> dict | None:
    reference = _detect_known_community_reference(query)
    if not reference:
        return None

    requested_community_id, requested_community_name = reference
    if requested_community_id == community_id:
        return None

    return {
        "query": query,
        "plan": {
            "_macro": "community_scope_mismatch",
            "requested_community_id": requested_community_id,
            "requested_community_name": requested_community_name,
            "current_community_id": community_id,
            "current_community_name": get_community_name(community_id) or f"community ID {community_id}",
        },
        "answer": f"I couldn't find matching resident records for '{requested_community_name.lower()}'.",
    }


def _extract_resident_name(query: str) -> str | None:
    q = query.lower().replace("’", "'").strip()
    patterns = [
        r"\b(?:h?ow\s+old\s+is|(?:what\s+is\s+)?(?:the\s+)?age\s+of)\s+(?:resident\s+|patient\s+)?([a-z]+(?:\s+[a-z]+){1,2})\b",
        r"\bwho\s+is\s+(?:resident\s+|patient\s+)?([a-z]+(?:\s+[a-z]+){1,2})\b",
        r"\b(?:what|which)\s+(?:flat|room)(?:\s+(?:number|no))?\s+(?:is|does)\s+(?:resident\s+|patient\s+)?([a-z]+(?:\s+[a-z]+){1,2})(?:\s+(?:in|have|has))?\b",
        r"\b(?:where\s+(?:does|is))\s+(?:resident\s+|patient\s+)?([a-z]+(?:\s+[a-z]+){1,2})(?:\s+(?:stay|staying|live|living|assigned))?\b",
        r"\b(?:what|which)\s+(?:medications?|medicine|prescription|prescriptions|intake|treatment)\s+(?:is|are|does|do)\s+(?:resident\s+|patient\s+)?([a-z]+(?:\s+[a-z]+){1,2})(?:\s+(?:prescribed|take|takes|taking|on|have|has))?\b",
        r"\b(?:what\s+is|what's)\s+(?:resident\s+|patient\s+)?([a-z]+(?:\s+[a-z]+){1,2})(?:'s)?\s+(?:prescribed\s+)?(?:medications?|medicine|prescription|prescriptions|intake|treatment)\b",
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
            candidate = re.sub(
                r"^(?:(?:what|who|is|the|of|for|about|resident|patient|me|my|give|show|tell|get|display|find|list|see|check)\s+)+",
                "",
                candidate,
            ).strip()
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
            } and candidate not in _NON_RESIDENT_NAME_CANDIDATES and not _is_known_community_name(candidate) and _is_plausible_resident_name(candidate):
                return candidate.title()
    return None


def _extract_resident_name_fragment(query: str) -> str | None:
    q = query.lower().replace("’", "'").strip()
    profile_tail = (
        r"details?|profile|info|information|age|old|room|flat|"
        r"medical history|health history|history|medication|prescribed|intake|treatment"
    )
    metric_tail = (
        r"age|old|room|flat|medical history|health history|history|"
        r"medication|prescribed|intake|treatment"
    )
    patterns = [
        rf"\b(?:h?ow\s+old\s+is|(?:what\s+is\s+)?(?:the\s+)?age\s+of)\s+"
        rf"(?:resident\s+|patient\s+)?([a-z]+)\b",
        rf"\b(?:what|which)\s+(?:flat|room)(?:\s+(?:number|no))?\s+(?:is|does)\s+"
        rf"(?:resident\s+|patient\s+)?([a-z]+)(?:\s+(?:in|have|has))?\b",
        rf"\b(?:where\s+(?:does|is))\s+(?:resident\s+|patient\s+)?([a-z]+)"
        rf"(?:\s+(?:stay|staying|live|living|assigned))?\b",
        rf"\b(?:what|which)\s+(?:medications?|medicine|prescription|prescriptions|intake|treatment)\s+"
        rf"(?:is|are|does|do)\s+(?:resident\s+|patient\s+)?([a-z]+)"
        rf"(?:\s+(?:prescribed|take|takes|taking|on|have|has))?\b",
        rf"\b(?:what\s+is|what's)\s+(?:resident\s+|patient\s+)?([a-z]+)(?:'s)?\s+"
        rf"(?:prescribed\s+)?(?:medications?|medicine|prescription|prescriptions|intake|treatment)\b",
        rf"\b(?:give|show|display|get|tell)\b(?:\s+me)?(?:\s+the)?\s+(?:{profile_tail})\s+"
        rf"(?:of|for|about)\s+(?:resident\s+|patient\s+)?([a-z]+)\b",
        rf"\b(?:{profile_tail})\s+(?:of|for|about)\s+(?:resident\s+|patient\s+)?([a-z]+)\b",
        rf"\b(?:what\s+is|what's|where\s+(?:does|is))\s+(?:resident\s+|patient\s+)?"
        rf"([a-z]+)(?:'s)?\s+(?:{metric_tail})\b",
        rf"\b([a-z]+)\s+(?:{profile_tail})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            candidate = match.group(1).strip(" .,?!")
            if (
                candidate not in _NON_RESIDENT_NAME_CANDIDATES
                and not _is_known_community_name_fragment(candidate, query)
                and _is_plausible_resident_name_fragment(candidate)
            ):
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
