LOCAL_DEMO_COMMUNITIES = {
    1: "Green Valley Care",
    2: "Sunrise Senior Living",
    3: "Lotus Wellness Home",
}


def get_memory_session_id(session_id: str, community_id: int) -> str:
    """Keep chat history isolated per community."""
    return f"community:{community_id}:session:{session_id}"


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
    return (
        "Invalid community_id. Use 1 for Green Valley Care, "
        "2 for Sunrise Senior Living, or 3 for Lotus Wellness Home."
    )
