# ===========================================================================
# This file turns a raw health number into a short, plain note. For example, a
# heart rate of 95 becomes "within the normal resting range", while a very low
# one becomes "worth flagging for review". These are gentle review hints to
# help staff — NOT medical diagnoses, and every note says so.
# ===========================================================================
"""Screening thresholds for resident metrics.

Purpose
-------
Let the sensor handlers attach a one-line interpretation to every reading
so the chatbot can tell a caregiver "HR 95 bpm — slightly elevated; flag
for review if it stays this way" instead of just dumping the number.

These are **screening** thresholds, not diagnostic boundaries. They mirror
broadly-accepted ranges for older adults (65+):

  - Heart rate, resting:  60-100 bpm typical
  - Respiration rate:     12-20 breaths/min typical
  - Sleep duration:       7-8 hours target for adults 65+
  - Sleep quality score:  60+ acceptable, 80+ ideal (project scale)
  - Wellness score:       60+ acceptable, 80+ strong (project scale)

The "concerning" band intentionally means "review with the care team",
not "diagnose this resident". Every screening note ends with that frame.

Why these live here, not in router._METRIC_BASELINES
----------------------------------------------------
_METRIC_BASELINES answers "what is a normal BP?" — it educates the user
when they ask in the abstract. This module classifies a **specific
reading** the chatbot just pulled from the DB. Different audience, same
underlying medicine; kept separate so a threshold tweak doesn't churn the
guidance prose, and vice versa.
"""
from __future__ import annotations

from typing import Literal, NamedTuple


Band = Literal["low", "normal", "elevated", "high", "concerning"]


class Reading(NamedTuple):
    """A classified metric reading.

    `band` — which screening bucket the value fell into.
    `note` — one short sentence (≤ ~18 words) suitable for tacking onto
             the end of a chatbot answer. Always non-diagnostic.
    """
    band: Band
    note: str


# ---------------------------------------------------------------------------
# Heart rate (bpm) — adult resting baseline.
# ---------------------------------------------------------------------------

def classify_hr(value: float | None) -> Reading | None:
    """Classify a resting heart rate reading.

    Buckets (typical for older adults at rest):
      < 50  : low — review for bradycardia / medication side effects
      50-59 : on the low side — watch trend
      60-100: within typical resting range
      101-110: slightly elevated — check for recent activity / fever
      > 110 : high — flag for clinical review
    """
    if value is None:
        return None
    v = float(value)
    if v < 50:
        return Reading("concerning", "That's below the typical resting range — worth flagging for clinical review.")
    if v < 60:
        return Reading("low", "A bit on the low side of typical resting; watch the trend.")
    if v <= 100:
        return Reading("normal", "Within the typical resting heart-rate range.")
    if v <= 110:
        return Reading("elevated", "Slightly above the typical resting range — could reflect recent activity.")
    return Reading("concerning", "Notably elevated for a resting reading — recommend a clinical check.")


# ---------------------------------------------------------------------------
# Respiration rate (breaths/min) — adult baseline.
# ---------------------------------------------------------------------------

def classify_rr(value: float | None) -> Reading | None:
    """Classify a respiration rate reading.

    Buckets:
      < 10 : low — review for sedation / clinical concern
      10-11: on the low side
      12-20: typical resting range
      21-24: slightly elevated
      > 24 : high — flag for clinical review
    """
    if value is None:
        return None
    v = float(value)
    if v < 10:
        return Reading("concerning", "Below the typical resting range — recommend a clinical check.")
    if v < 12:
        return Reading("low", "On the low side of typical resting; watch the trend.")
    if v <= 20:
        return Reading("normal", "Within the typical resting respiration range.")
    if v <= 24:
        return Reading("elevated", "Slightly above typical — could reflect activity or mild exertion.")
    return Reading("concerning", "Notably elevated — worth a clinical review, especially if sustained.")


# ---------------------------------------------------------------------------
# Sleep duration (minutes asleep, total of non-awake stages).
# ---------------------------------------------------------------------------

def classify_sleep_duration(minutes: int | None) -> Reading | None:
    """Classify a night's total asleep time (older-adult target: 7-8 h).

    Buckets:
      < 4h  : very short — concerning
      4-5h  : short — flag for review
      5-6h  : reduced sleep
      6-9h  : within typical range
      > 9h  : long — review if persistent (oversleeping signal)
    """
    if minutes is None:
        return None
    hours = minutes / 60.0
    if hours < 4:
        return Reading("concerning", "That's well below a healthy night's sleep — flag for review.")
    if hours < 5:
        return Reading("low", "A short night — keep an eye on the next few days.")
    if hours < 6:
        return Reading("low", "Reduced sleep compared to the typical target.")
    if hours <= 9:
        return Reading("normal", "Within a healthy sleep range for an older adult.")
    return Reading("elevated", "Longer than typical — worth reviewing if it persists.")


# ---------------------------------------------------------------------------
# Sleep quality / wellness score (0-100 project scale).
# ---------------------------------------------------------------------------

def _classify_0_100_score(value: float | None, kind: str) -> Reading | None:
    """Shared 0-100 score classifier used for sleep-quality and wellness."""
    if value is None:
        return None
    v = float(value)
    if v >= 80:
        return Reading("normal", f"{kind.title()} score is strong.")
    if v >= 60:
        return Reading("normal", f"{kind.title()} score sits in the acceptable mid-range.")
    if v >= 50:
        return Reading("elevated", f"{kind.title()} score is borderline — worth watching the trend.")
    return Reading("concerning", f"{kind.title()} score is low — review with the resident's care plan.")


def classify_wellness_score(value: float | None) -> Reading | None:
    return _classify_0_100_score(value, "wellness")


def classify_sleep_score(value: float | None) -> Reading | None:
    return _classify_0_100_score(value, "sleep")


# ---------------------------------------------------------------------------
# Incident pattern (per resident, last 7 days).
# ---------------------------------------------------------------------------

def classify_fall_pattern(fall_count: int, confirmed_count: int) -> Reading | None:
    """Classify a resident's recent fall pattern.

    `fall_count` is the total of fall-shaped incidents in the window;
    `confirmed_count` is the subset with `event_category = 'confirmed_fall'`.
    Confirmed falls weigh more heavily than alerts that were resolved as
    false positives.
    """
    if fall_count == 0:
        return Reading("normal", "No recent fall events on record.")
    if confirmed_count >= 1:
        return Reading(
            "concerning",
            "There's a confirmed fall on record — recommend escalating to clinical review.",
        )
    if fall_count >= 2:
        return Reading(
            "elevated",
            "Multiple fall alerts in a short window — review for environmental or mobility factors.",
        )
    return Reading(
        "elevated",
        "One recent fall alert on record — watch the next few days.",
    )


# ---------------------------------------------------------------------------
# Public list of band severities (highest concern first) — handlers use this
# to pick the worst-ranked metric when summarizing a resident overall.
# ---------------------------------------------------------------------------

BAND_SEVERITY: dict[Band, int] = {
    "concerning": 4,
    "high": 3,
    "low": 2,
    "elevated": 2,
    "normal": 0,
}


def worst_band(*readings: Reading | None) -> Band | None:
    """Return the highest-severity band across the supplied readings, or
    None if every reading is missing. ``"normal"`` wins only if every
    non-None reading is normal."""
    bands = [r.band for r in readings if r is not None]
    if not bands:
        return None
    return max(bands, key=lambda b: BAND_SEVERITY.get(b, 0))
