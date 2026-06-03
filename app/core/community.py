# ===========================================================================
# This file keeps each care community's data walled off from the others. It
# holds the list of valid communities, builds the per-community/per-user keys
# used to store chat history, and checks that whoever is asking is actually
# allowed to see the community they're asking about — before any data is read.
# ===========================================================================
"""Community registry, session scoping, and per-user community authorization.

Three responsibilities live here so the request entry point can stay thin:

1. `LOCAL_DEMO_COMMUNITIES` — the allowlist of community_ids the chatbot
   accepts. It mirrors the rows seeded by `data/seed/0001_demo_seed.sql`.
2. `get_memory_session_id` / `is_current_community_query` — chat-history
   helpers that prefix Redis keys with the community so sessions never bleed.
3. `get_authorized_community_ids` — DB lookup against `community_user_mapping`.
   This is what enforces "a caregiver of community A cannot read community B"
   at the API edge, before any retrieval runs. The schema-level SQL validator
   still enforces a `community_id` predicate; this check ensures the predicate
   value is one the caller is actually allowed to ask for.
"""

from app.core.logger import get_logger

logger = get_logger("community")

# app.core.db is imported lazily inside the helpers below. Eager import would
# break tests that stub app.core.db with a minimal module (no run_query /
# DatabaseUnavailableError) — those tests don't exercise the authorization
# path, so paying the cost there is wasteful and broken.


LOCAL_DEMO_COMMUNITIES = {
    1: "Green Valley Care",
    2: "Sunrise Senior Living",
    3: "Lotus Wellness Home",
    4: "Maple Heights Eldercare",
    5: "Coastal Haven Senior Home",
}


def get_memory_session_id(
    session_id: str,
    community_id: int,
    user_id: int | None = None,
) -> str:
    """Return the Redis key under which this conversation's history lives.

    Isolation contract:
      - When `user_id` is supplied, history is scoped per (user, community,
        session). Switching users in the UI does NOT expose the previous
        user's queries even if the same session_id were ever reused.
      - When `user_id` is None (the unauthenticated demo path), history is
        scoped per (community, session). Preserves the older key shape so
        existing demo traffic doesn't lose its history.

    Memory keys are not authoritative for access control — `authorize_community`
    is. This namespacing is defense-in-depth and an UX fix.
    """
    if user_id is None:
        return f"community:{community_id}:session:{session_id}"
    return f"user:{user_id}:community:{community_id}:session:{session_id}"


def get_community_name(community_id: int) -> str | None:
    return LOCAL_DEMO_COMMUNITIES.get(community_id)


def is_current_community_query(query: str) -> bool:
    q = query.lower().strip()
    return any(
        phrase in q
        for phrase in [
            "which community am i",
            "where am i from",
            "what community am i",
            "which community data",
            "what community data",
            "current community",
            "which community am i viewing",
            "community am i viewing",
            "community am i using",
            "which community am i from",
            "what community am i from",
            "which community is this",
            "what community is this"
        ]
    )


def invalid_community_error() -> str:
    """Render the allowlist for the user without leaking internals."""
    options = ", ".join(
        f"{cid} for {name}" for cid, name in sorted(LOCAL_DEMO_COMMUNITIES.items())
    )
    return f"Invalid community_id. Use {options}."


def get_authorized_community_ids(user_id: int) -> set[int]:
    """Return the set of community_ids this user is mapped to.

    Reads `community_user_mapping`, filtered on `is_deleted`. An empty set
    means "no access" — callers should refuse the request rather than fall
    back to "any community".

    Raises DatabaseUnavailableError on DB failure; the API layer turns that
    into a safe user-facing error.
    """
    from app.core.db import run_query  # lazy: see module docstring

    rows = run_query(
        "SELECT community_id FROM community_user_mapping "
        "WHERE user_id = %s AND COALESCE(is_deleted, false) = false",
        (user_id,),
    )
    return {row[0] for row in rows}


def get_user_role(user_id: int) -> str | None:
    """Return the role name for a staff user, or None when unknown/deleted.

    Reads `users.role_id -> roles.name`. The seeded roles are 'admin',
    'center_owner', and 'caregiver' (see data/kubo_dummy.sql). Used by the
    directory handlers to decide who may list communities and staff.

    Raises DatabaseUnavailableError on DB failure; callers turn that into a
    safe, fail-closed message.
    """
    from app.core.db import run_query  # lazy: see module docstring

    rows = run_query(
        "SELECT r.name "
        "FROM users u JOIN roles r ON r.id = u.role_id "
        "WHERE u.id = %s AND COALESCE(u.is_deleted, false) = false",
        (user_id,),
    )
    return rows[0][0] if rows else None


def access_denied_error() -> str:
    """User-facing message for an unauthorized community request.

    Intentionally vague — does not reveal which communities the user CAN see,
    and does not reveal whether the community_id exists at all. Both would
    be enumeration aids.
    """
    return "You do not have access to this community."


def authorize_community(user_id: int | None, community_id: int) -> str | None:
    """Validate community_id and (if user_id given) user-community mapping.

    Returns None if the request is allowed; otherwise a safe user-facing
    error string. Two-layer check:

      1. community_id must be in the allowlist (`get_community_name`).
      2. If `user_id` is provided, it must be mapped to that community.

    `user_id=None` preserves the demo / unauthenticated path: only the
    allowlist check runs. Once the front-end always supplies user_id this
    branch will go away; for now it keeps existing demo traffic working.

    On DB failure, returns a generic error rather than crashing or letting
    the request through.
    """
    if get_community_name(community_id) is None:
        return invalid_community_error()

    if user_id is None:
        return None

    from app.core.db import DatabaseUnavailableError  # lazy: see module docstring

    try:
        allowed = get_authorized_community_ids(user_id)
    except DatabaseUnavailableError:
        logger.error(
            "Community authorization check failed (DB unavailable)",
            extra={"user_id": user_id, "community_id": community_id},
        )
        return "Access check is temporarily unavailable. Please try again shortly."

    if community_id not in allowed:
        logger.warning(
            "Community access denied",
            extra={"user_id": user_id, "community_id": community_id},
        )
        return access_denied_error()

    return None
