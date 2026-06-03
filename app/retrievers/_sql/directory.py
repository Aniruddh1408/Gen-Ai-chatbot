# ===========================================================================
# This file answers "list the communities" and "list the caregivers" — but only
# shows what the person asking is allowed to see. An admin sees everything; a
# community owner sees their own community's staff; a caregiver isn't allowed to
# see the staff directory at all. This is what keeps each community's people
# private from the others.
# ===========================================================================
"""Role-aware directory handlers: communities and staff (caregivers).

The rest of the SQL retriever answers *resident*-scoped questions inside one
community. Two questions don't fit that mould — "list the communities" and
"list the caregivers" — because their correct answer depends on WHO is asking:

  - admin         -> the whole organisation (every community; staff per
                     community, or all communities when asked org-wide)
  - center_owner  -> their own community's staff and community
  - caregiver     -> residents only (already handled elsewhere); the staff
                     directory is denied
  - resident / demo (no login) -> denied for staff; own/current community only
                     for the community list

This is the access-isolation the user asked for: an admin sees everything, a
center owner sees their community's people, a caregiver sees only residents.

Pure-ish: the only I/O is run_query and the role/scope lookups, all imported as
module-level names so tests can monkeypatch them without a database.
"""
import re

from app.core.community import (
    get_authorized_community_ids,
    get_community_name,
    get_user_role,
)
from app.core.logger import get_logger
from app.retrievers._sql.safety import _validate_read_only_sql

logger = get_logger("sql_retriever.directory")


def run_query(sql, params=None):
    """Lazy proxy to app.core.db.run_query.

    app.core.db is imported lazily (not at module top) so tests that stub
    app.core.db with a minimal module — missing run_query /
    DatabaseUnavailableError — can still import this module. Mirrors the same
    deferral in app/core/community.py. Tests monkeypatch this name directly.
    """
    from app.core.db import run_query as _run_query

    return _run_query(sql, params)

# A generic, non-leaky failure used whenever the directory lookup can't be
# completed (DB down, role unknown). Never echoes SQL or internals.
_TEMP_UNAVAILABLE = "That information is temporarily unavailable. Please try again shortly."

# Roles that are allowed to see the staff directory at all.
_STAFF_VIEW_ROLES = {"admin", "center_owner"}

# Intent verbs that mark a "list/enumerate/count" request.
_LIST_INTENT_RE = re.compile(
    r"\b(?:list|show|display|give|get|tell|name|names|enumerate|view|see|"
    r"all|how\s+many|number\s+of|count\s+of|what\s+are|which\s+are|who\s+are)\b",
    re.IGNORECASE,
)

# Staff vocabulary. Residents are intentionally excluded — they are not staff
# and are handled by the resident-list path.
_STAFF_TERM_RE = re.compile(
    r"\b(?:care\s*givers?|caregivers?|carers?|nurses?|"
    r"center\s+owners?|centre\s+owners?|"
    r"staff|care\s+team|caretakers?|care\s+takers?)\b",
    re.IGNORECASE,
)

# Terms that widen a staff query from "caregivers" to "all staff" (owners too).
_STAFF_INCLUDE_OWNERS_RE = re.compile(
    r"\b(?:owners?|managers?|staff|team|everyone|employees?|all\s+users?)\b",
    re.IGNORECASE,
)

# "across the org" phrasing that lets an admin span every community. Requires
# an explicit community/organisation context — a bare "all" (as in "all staff")
# is a quantifier on the people, not a request to span every community.
_ORG_WIDE_RE = re.compile(
    r"\borg[- ]?wide\b|\borganisation\b|\borganization\b"
    r"|\b(?:all|every|each|across|whole|entire)\s+(?:the\s+)?communit(?:y|ies)\b"
    r"|\bacross\s+(?:the\s+)?communit(?:y|ies)\b"
    r"|\b(?:whole|entire)\s+org\b",
    re.IGNORECASE,
)

_COMMUNITY_WORD_RE = re.compile(r"\bcommunit(?:y|ies)\b", re.IGNORECASE)
_RESIDENT_WORD_RE = re.compile(r"\b(?:residents?|patients?)\b", re.IGNORECASE)


def _is_community_list_query(q: str) -> bool:
    """True for "list/how many communities", not "residents in the community"."""
    if not _COMMUNITY_WORD_RE.search(q):
        return False
    # If the query is really about residents/staff that happen to mention the
    # word "community", let the resident/staff handlers take it.
    if _RESIDENT_WORD_RE.search(q) or _STAFF_TERM_RE.search(q):
        return False
    return _LIST_INTENT_RE.search(q) is not None


def _is_staff_list_query(q: str) -> bool:
    """True for "list the caregivers/staff", not resident questions."""
    if not _STAFF_TERM_RE.search(q):
        return False
    # "which resident needs a caregiver" is about residents, not the directory.
    if _RESIDENT_WORD_RE.search(q):
        return False
    return _LIST_INTENT_RE.search(q) is not None


# ---------------------------------------------------------------------------
# Community directory
# ---------------------------------------------------------------------------

def _format_community_rows(rows: list[tuple]) -> str:
    count = len(rows)
    if count == 1:
        name, city = rows[0][1], rows[0][2]
        where = f" ({city})" if city else ""
        return f"You have access to one community: {name}{where}."

    lead = f"There are {count} communities:" if count != 1 else "There is 1 community:"
    lines = [lead, ""]
    for cid, name, city in rows:
        where = f" — {city}" if city else ""
        lines.append(f"{cid}. {name}{where}")
    return "\n".join(lines)


def _community_list_response(query: str, community_id: int, user_id: int | None) -> dict:
    role = get_user_role(user_id) if user_id is not None else None

    if role == "admin":
        rows = run_query(
            "SELECT id, name, city FROM community "
            "WHERE COALESCE(is_deleted, false) = false "
            "ORDER BY id"
        )
        scope = "admin_all"
    else:
        # Non-admin (and the unauthenticated demo path) only ever see the
        # communities they are mapped to. Demo has no identity, so it is
        # scoped to the community it is currently viewing.
        if user_id is None:
            allowed = [community_id]
        else:
            allowed = sorted(get_authorized_community_ids(user_id))
        if not allowed:
            return _denied_communities(query)
        rows = run_query(
            "SELECT id, name, city FROM community "
            "WHERE id = ANY(%s) AND COALESCE(is_deleted, false) = false "
            "ORDER BY id",
            (list(allowed),),
        )
        scope = "scoped"

    if not rows:
        return {
            "query": query,
            "plan": {"_macro": "community_list", "_scope": scope},
            "answer": "No communities are on file.",
        }

    return {
        "query": query,
        "plan": {"_macro": "community_list", "_scope": scope, "_count": len(rows)},
        "answer": _format_community_rows(rows),
    }


def _denied_communities(query: str) -> dict:
    return {
        "query": query,
        "plan": {"_macro": "community_list", "_scope": "denied"},
        "answer": "You do not have access to any community.",
    }


# ---------------------------------------------------------------------------
# Staff directory (caregivers / owners)
# ---------------------------------------------------------------------------

_STAFF_BASE_SQL = (
    "SELECT u.name, r.name "
    "FROM users u "
    "JOIN roles r ON r.id = u.role_id "
    "JOIN community_user_mapping cum "
    "  ON cum.user_id = u.id AND COALESCE(cum.is_deleted, false) = false "
    "WHERE cum.community_id = %s "
    "  AND r.name = ANY(%s) "
    "  AND COALESCE(u.is_deleted, false) = false "
    "ORDER BY r.name, u.name"
)

_STAFF_ALL_SQL = (
    "SELECT c.id, c.name, u.name, r.name "
    "FROM community_user_mapping cum "
    "JOIN users u ON u.id = cum.user_id AND COALESCE(u.is_deleted, false) = false "
    "JOIN roles r ON r.id = u.role_id "
    "JOIN community c ON c.id = cum.community_id AND COALESCE(c.is_deleted, false) = false "
    "WHERE r.name = ANY(%s) AND COALESCE(cum.is_deleted, false) = false "
    "ORDER BY c.id, r.name, u.name"
)

_ROLE_LABEL = {"caregiver": "caregiver", "center_owner": "center owner"}


def _roles_wanted(q: str) -> list[str]:
    if _STAFF_INCLUDE_OWNERS_RE.search(q):
        return ["caregiver", "center_owner"]
    return ["caregiver"]


def _noun_for(roles_wanted: list[str]) -> str:
    return "staff" if "center_owner" in roles_wanted else "caregivers"


def _format_staff_rows(rows: list[tuple], community_name: str, roles_wanted: list[str]) -> str:
    noun = _noun_for(roles_wanted)
    if not rows:
        return f"There are no {noun} on file in {community_name}."

    show_role = len(roles_wanted) > 1
    count = len(rows)
    label = noun[:-1] if count == 1 and noun.endswith("s") else noun
    lines = [f"There {'is' if count == 1 else 'are'} {count} {label} in {community_name}:", ""]
    for index, row in enumerate(rows, start=1):
        name = row[0] or "Unnamed"
        if show_role:
            role_label = _ROLE_LABEL.get(row[1], row[1])
            lines.append(f"{index}. {name} ({role_label})")
        else:
            lines.append(f"{index}. {name}")
    return "\n".join(lines)


def _format_staff_all_rows(rows: list[tuple], roles_wanted: list[str]) -> str:
    noun = _noun_for(roles_wanted)
    if not rows:
        return f"There are no {noun} on file in any community."

    show_role = len(roles_wanted) > 1
    lines = [f"{noun.capitalize()} across all communities:", ""]
    current_community = None
    for _cid, community_name, name, role_name in rows:
        if community_name != current_community:
            current_community = community_name
            lines.append(f"{community_name}:")
        if show_role:
            role_label = _ROLE_LABEL.get(role_name, role_name)
            lines.append(f"- {name} ({role_label})")
        else:
            lines.append(f"- {name}")
    return "\n".join(lines)


def _staff_list_response(query: str, community_id: int, user_id: int | None) -> dict:
    role = get_user_role(user_id) if user_id is not None else None

    if role not in _STAFF_VIEW_ROLES:
        # caregiver / resident / unauthenticated demo: no staff directory.
        logger.info(
            "Staff directory request denied",
            extra={"user_id": user_id, "role": role, "community_id": community_id},
        )
        return {
            "query": query,
            "plan": {"_macro": "staff_list", "_scope": "denied"},
            "answer": (
                "You do not have permission to view the staff directory. "
                "Please contact a center owner or administrator."
            ),
        }

    roles_wanted = _roles_wanted(query.lower())

    # An admin can ask for the whole organisation; everyone else (and an admin
    # who didn't ask org-wide) is scoped to the community they are viewing.
    if role == "admin" and _ORG_WIDE_RE.search(query.lower()):
        _validate_read_only_sql(_STAFF_ALL_SQL)
        rows = run_query(_STAFF_ALL_SQL, (roles_wanted,))
        return {
            "query": query,
            "plan": {"_macro": "staff_list", "_scope": "admin_all", "_roles": roles_wanted},
            "answer": _format_staff_all_rows(rows, roles_wanted),
        }

    _validate_read_only_sql(_STAFF_BASE_SQL)
    rows = run_query(_STAFF_BASE_SQL, (community_id, roles_wanted))
    community_name = get_community_name(community_id) or f"community {community_id}"
    return {
        "query": query,
        "plan": {
            "_macro": "staff_list",
            "_scope": "community",
            "_community_id": community_id,
            "_roles": roles_wanted,
        },
        "answer": _format_staff_rows(rows, community_name, roles_wanted),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def handle_directory_query(query: str, community_id: int, user_id: int | None) -> dict | None:
    """Answer a community- or staff-directory question, role-scoped.

    Returns a response dict for a recognised directory question, or None so the
    caller falls through to normal resident routing. All DB failures degrade to
    a safe, non-leaky message (fail closed) rather than raising.
    """
    q = (query or "").lower().strip()
    if not q:
        return None

    is_community = _is_community_list_query(q)
    is_staff = _is_staff_list_query(q)
    if not (is_community or is_staff):
        return None

    # Lazy import (see run_query proxy): keeps this module importable when
    # app.core.db is stubbed in tests that never reach a directory query.
    from app.core.db import DatabaseUnavailableError

    try:
        if is_staff:
            return _staff_list_response(query, community_id, user_id)
        return _community_list_response(query, community_id, user_id)
    except DatabaseUnavailableError:
        logger.error(
            "Directory lookup failed (DB unavailable)",
            extra={"user_id": user_id, "community_id": community_id, "query": query},
        )
        return {
            "query": query,
            "plan": {"_macro": "directory_unavailable"},
            "answer": _TEMP_UNAVAILABLE,
        }
