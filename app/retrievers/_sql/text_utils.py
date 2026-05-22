"""Small pure formatting/number helpers for sql_retriever (no DB/LLM)."""
def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_sleep_duration(value, missing: str = "not recorded") -> str:
    minutes = _to_float(value)
    if minutes is None:
        return missing

    total_minutes = int(round(minutes))
    sign = "-" if total_minutes < 0 else ""
    hours, remaining_minutes = divmod(abs(total_minutes), 60)
    if remaining_minutes == 0:
        return f"{sign}{hours}h"
    return f"{sign}{hours}h {remaining_minutes}m"


def _metric_text(value, suffix: str = "") -> str:
    if value is None:
        return "not recorded"
    return f"{value}{suffix}"


def _metric_explanation(metric: str) -> str:
    if metric == "bp":
        return "Blood pressure is a latest recorded vital, not live monitoring. Elevated values should be reviewed with clinical context."
    if metric == "sugar":
        return "Sugar level is a latest recorded reading and should be compared with the resident's usual range and care plan."
    if metric == "steps":
        return "Step count is a movement signal. Low values can reflect reduced activity, device non-wear, or missed synchronization."
    if metric == "sleep_duration":
        return "Sleep duration shows recorded rest time. Short or repeated low duration can be a useful review signal."
    if metric == "sleep_quality":
        return "Sleep quality score is a care-review signal. Lower scores can point to poorer rest or a data-quality issue."
    if metric == "sleep":
        return "Sleep duration and sleep quality should be read together before deciding whether follow-up is needed."
    return "Use this value as recorded operational context and review it with related resident metrics."


def _metric_next_step(metric: str, name: str | None = None) -> str:
    subject = name if name else "the resident"
    if metric in {"sleep_quality", "sleep_duration", "sleep"}:
        return f"Next step: Check {subject}'s sleep duration, activity, and device sync status before deciding on follow-up. This is not a diagnosis."
    if metric == "steps":
        return f"Next step: Compare {subject}'s steps with recent sleep and health readings, and confirm the device was worn. This is not a diagnosis."
    if metric == "bp":
        return f"Next step: Review {subject}'s BP with recent sugar, sleep, symptoms, and the care protocol. This is not a diagnosis."
    if metric == "sugar":
        return f"Next step: Review {subject}'s sugar trend with meal timing, medication context, and care protocol. This is not a diagnosis."
    return f"Next step: Review related metrics for {subject} before making an operational care decision."
