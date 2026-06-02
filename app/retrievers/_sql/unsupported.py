"""Deterministic guard for resident questions about data the schema doesn't hold.

Why this exists
---------------
KuboCare's sensors are radar-based and non-wearable: they capture heart rate,
respiration, sleep, activity, wellness rollups, and fall/incident events. They
do NOT measure blood pressure, blood sugar/glucose, cholesterol, weight, SpO2,
or body temperature, and the system stores no medication/prescription records
(conditions live as free text in resident_profile.medical_history, but doses do
not).

Without this guard, a question like "what is Anil's blood pressure?" routes to
SQL, matches no deterministic handler, falls through to the LLM planner (which
has no such column), and comes back as a confusing empty echo — or, worse, a
made-up number. This step intercepts those topics LAST in the dispatch chain
(after every real handler has had its chance) and returns one clear, honest
sentence about what is and isn't tracked.

Pure text detection; no DB/LLM. The message names what IS available so the
caregiver isn't left guessing.
"""
from __future__ import annotations

import re

# Conditions tracked as free text in medical_history (handled earlier by the
# text-search handler) — listed here only so we never mistake a condition
# question for an unsupported-measurement question.
_CONDITION_TERMS = (
    "hypertension", "diabetes", "pre-diabetes", "prediabetes", "arthritis",
    "asthma", "cardiac", "cardiovascular", "osteoporosis", "thyroid",
)

# Measured values the sensors can't produce. Substring match (lowercased).
_UNSUPPORTED_VITALS_TERMS = (
    "blood pressure", "systolic", "diastolic",
    "blood sugar", "sugar level", "sugar levels", "sugar reading",
    "sugar value", "glucose", "blood glucose", "hba1c", "a1c",
    "cholesterol", "ldl", "hdl", "triglyceride", "triglycerides",
    "body weight", "weight", "bmi",
    "oxygen", "spo2", "o2 sat", "oxygen saturation",
    "pulse oximetry", "pulse ox",
    "body temperature", "body temp",
)
# Short token that needs a word boundary so it doesn't match inside other words.
_UNSUPPORTED_BP_RE = re.compile(r"(?<!\w)bp(?!\w)", re.IGNORECASE)

# Medication / prescription records the system doesn't keep.
_UNSUPPORTED_MEDICATION_TERMS = (
    "medication", "medications", "medicine", "medicines",
    "prescription", "prescriptions", "prescribed", "prescribe",
    "dose", "doses", "dosage", "dosages",
    "drug", "drugs", "tablet", "tablets", "pill", "pills",
    "intake",
)

_TRACKED_SUMMARY = (
    "The available readings are heart rate, respiration, sleep, activity, "
    "wellness scores, and fall/incident events."
)

_VITALS_MESSAGE = (
    "That isn't tracked in KuboCare's records — the sensors are radar-based and "
    "don't measure blood pressure, blood sugar, cholesterol, weight, or oxygen "
    f"levels. {_TRACKED_SUMMARY}"
)
_MEDICATION_MESSAGE = (
    "Medication and prescription details aren't stored in the available records. "
    "KuboCare tracks sensor readings (heart rate, respiration, sleep, activity, "
    "and falls) plus the conditions noted in each resident's medical history, "
    "not drugs or doses."
)


def _detect_unsupported_topic(query: str) -> str | None:
    """Return "medication", "vitals", or None for an unsupported-data question."""
    q = (query or "").lower()

    # Medication first — "what medication is X on" is unambiguous.
    if any(term in q for term in _UNSUPPORTED_MEDICATION_TERMS):
        return "medication"

    # A condition question ("who has diabetes") is supported via text search and
    # is handled before this guard runs; never treat it as an unsupported value.
    if any(term in q for term in _CONDITION_TERMS):
        return None

    if _UNSUPPORTED_BP_RE.search(q) or any(term in q for term in _UNSUPPORTED_VITALS_TERMS):
        return "vitals"

    return None


def _step_unsupported_metric(query: str, community_id: int) -> dict | None:
    """Last-resort deterministic handler: answer unsupported-data questions
    honestly instead of letting them fall to the LLM planner.

    Deliberately omits ``result`` from the response so the router's
    ``_sql_found_nothing`` check does NOT treat this as an empty result and
    retry RAG — this clear message is the final answer.
    """
    topic = _detect_unsupported_topic(query)
    if topic is None:
        return None

    answer = _MEDICATION_MESSAGE if topic == "medication" else _VITALS_MESSAGE
    return {
        "query": query,
        "plan": {"_macro": "unsupported_data", "topic": topic},
        "answer": answer,
    }
