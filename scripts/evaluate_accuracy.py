"""
Local regression evaluator for KuboCare retrieval and routing.

This is intentionally deterministic: it uses the seeded unit-test database
fixture instead of the live DB/LLM so regressions are easy to reproduce.
The score is not a live production accuracy score. It checks whether routing,
retrieved rows, and answer grounding match an independent seed-data oracle.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_memory_followups import load_memory_with_stubs
from tests.test_resident_superlatives import (
    SEED_ACTIVITY,
    SEED_DEVICES,
    SEED_HEALTH,
    SEED_RESIDENTS,
    SEED_SLEEP,
    SeedQueryRunner,
    load_sql_retriever,
)
from tests.test_router_general_chat import load_router_with_stubs


@dataclass
class ExpectedFacts:
    result_names_exact: list[str] | None = None
    result_names_prefix: list[str] | None = None
    answer_contains: list[str] = field(default_factory=list)
    answer_not_contains: list[str] = field(default_factory=list)
    result_contains: list[str] = field(default_factory=list)


@dataclass
class SQLCase:
    query: str
    community_id: int
    category: str
    oracle: Callable[[], ExpectedFacts]
    macro: str | None = None


@dataclass
class RouteCase:
    query: str
    expected_route: str
    category: str = "routing"


@dataclass
class MemoryCase:
    query: str
    expected_rewrite: str
    history: list[dict[str, str]]
    category: str = "memory"


@dataclass
class CheckResult:
    category: str
    case: str
    check: str
    passed: bool
    expected: str
    actual: str


def _residents(community_id: int) -> list[dict[str, Any]]:
    return [item for item in SEED_RESIDENTS if item["community_id"] == community_id]


def _resident_by_name(name: str, community_id: int | None = None) -> dict[str, Any]:
    name_lower = name.lower()
    for item in SEED_RESIDENTS:
        if community_id is not None and item["community_id"] != community_id:
            continue
        if item["name"].lower() == name_lower:
            return item
    raise ValueError(f"Unknown seed resident: {name}")


def _metric_value(item: dict[str, Any], metric: str) -> Any:
    resident_id = item["id"]
    systolic, diastolic, sugar = SEED_HEALTH[resident_id]
    sleep_duration, sleep_score = SEED_SLEEP[resident_id]
    if metric == "bp_systolic":
        return systolic
    if metric == "bp_diastolic":
        return diastolic
    if metric == "bp":
        return f"{systolic}/{diastolic}"
    if metric == "sugar":
        return sugar
    if metric == "steps":
        return SEED_ACTIVITY[resident_id]
    if metric == "sleep_duration":
        return sleep_duration
    if metric == "sleep_score":
        return sleep_score
    raise ValueError(f"Unknown metric: {metric}")


def _format_minutes(minutes: int | float) -> str:
    total_minutes = int(round(minutes))
    hours, remaining_minutes = divmod(total_minutes, 60)
    if remaining_minutes == 0:
        return f"{hours}h"
    return f"{hours}h {remaining_minutes}m"


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_text(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_flatten_text(v) for v in value)
    return str(value)


def _actual_result_names(result: Any) -> list[str]:
    names: list[str] = []
    if not isinstance(result, list):
        return names
    for row in result:
        if isinstance(row, dict):
            value = row.get("name") or row.get("board_id")
        elif isinstance(row, (tuple, list)) and row:
            value = row[0]
        else:
            value = None
        if isinstance(value, str):
            names.append(value)
    return names


def _profile_facts(name: str, community_id: int) -> ExpectedFacts:
    item = _resident_by_name(name, community_id)
    facts = [item["name"], item["flat_no"], str(item["age"]), item["history"], item["medication"]]
    return ExpectedFacts(
        result_names_exact=[item["name"]],
        answer_contains=facts,
        result_contains=facts,
    )


def _multi_profile_facts(names: list[str], community_id: int) -> ExpectedFacts:
    residents = sorted(
        [_resident_by_name(name, community_id) for name in names],
        key=lambda item: (item["flat_no"], item["name"]),
    )
    facts: list[str] = []
    for item in residents:
        facts.extend([item["name"], item["flat_no"], str(item["age"]), item["history"], item["medication"]])
    return ExpectedFacts(
        result_names_exact=[item["name"] for item in residents],
        answer_contains=facts,
        result_contains=facts,
    )


def _multi_profile_field_facts(names: list[str], community_id: int, field_name: str) -> ExpectedFacts:
    residents = sorted(
        [_resident_by_name(name, community_id) for name in names],
        key=lambda item: (item["flat_no"], item["name"]),
    )
    field_map = {
        "age": lambda item: str(item["age"]),
        "flat_no": lambda item: item["flat_no"],
        "history": lambda item: item["history"],
        "medication": lambda item: item["medication"],
    }
    value_for = field_map[field_name]
    facts: list[str] = []
    for item in residents:
        facts.extend([item["name"], value_for(item)])
    return ExpectedFacts(
        result_names_exact=[item["name"] for item in residents],
        answer_contains=facts,
        result_contains=facts,
    )


def _text_search_facts(community_id: int, terms: list[str], exclude_terms: list[str] | None = None) -> ExpectedFacts:
    exclude_terms = exclude_terms or []
    matches = []
    for item in _residents(community_id):
        haystack = f"{item['history']} {item['medication']}".lower()
        if any(term.lower() in haystack for term in terms) and not any(term.lower() in haystack for term in exclude_terms):
            matches.append(item)
    matches = sorted(matches, key=lambda row: (row["flat_no"], row["name"]))
    matched_names = [item["name"] for item in matches]
    non_matching_names = [item["name"] for item in _residents(community_id) if item["name"] not in matched_names]
    answer_facts = []
    for item in matches:
        answer_facts.extend([item["name"], item["flat_no"]])
    return ExpectedFacts(
        result_names_exact=matched_names,
        answer_contains=answer_facts,
        answer_not_contains=non_matching_names,
        result_contains=answer_facts,
    )


def _high_bp_facts(community_id: int) -> ExpectedFacts:
    matches = []
    for item in _residents(community_id):
        systolic, diastolic, _sugar = SEED_HEALTH[item["id"]]
        if systolic >= 140 or diastolic >= 90:
            matches.append(item)
    matched_names = [item["name"] for item in matches]
    answer_facts = []
    result_facts = []
    for item in matches:
        systolic, diastolic, _sugar = SEED_HEALTH[item["id"]]
        answer_facts.extend([item["name"], item["flat_no"], _metric_value(item, "bp")])
        result_facts.extend([item["name"], item["flat_no"], systolic, diastolic])
    non_matching_names = [item["name"] for item in _residents(community_id) if item["name"] not in matched_names]
    return ExpectedFacts(
        result_names_exact=matched_names,
        answer_contains=[str(fact) for fact in answer_facts],
        answer_not_contains=non_matching_names,
        result_contains=[str(fact) for fact in result_facts],
    )


def _named_metric_facts(name: str, community_id: int, metric: str) -> ExpectedFacts:
    item = _resident_by_name(name, community_id)
    value = _metric_value(item, metric)
    facts = [item["name"], str(value)]
    if metric == "bp":
        facts.append("mmHg")
    return ExpectedFacts(
        result_names_exact=[item["name"]],
        answer_contains=facts,
        result_contains=[item["name"], str(value)],
    )


def _multi_metric_facts(names: list[str], community_id: int, metric: str) -> ExpectedFacts:
    residents = sorted(
        [_resident_by_name(name, community_id) for name in names],
        key=lambda item: (item["flat_no"], item["name"]),
    )
    answer_facts: list[str] = []
    result_facts: list[str] = []
    for item in residents:
        answer_facts.extend([item["name"], item["flat_no"]])
        result_facts.extend([item["name"], item["flat_no"]])
        if metric == "bp":
            systolic, diastolic, _sugar = SEED_HEALTH[item["id"]]
            answer_facts.append(f"{systolic}/{diastolic}")
            result_facts.extend([str(systolic), str(diastolic)])
        elif metric == "sleep_score":
            value = _metric_value(item, "sleep_score")
            answer_facts.append(str(value))
            result_facts.append(str(value))
        elif metric == "steps":
            value = _metric_value(item, "steps")
            answer_facts.append(str(value))
            result_facts.append(str(value))
        elif metric == "all_metrics":
            systolic, diastolic, sugar = SEED_HEALTH[item["id"]]
            duration, score = SEED_SLEEP[item["id"]]
            steps = SEED_ACTIVITY[item["id"]]
            answer_facts.extend([f"{systolic}/{diastolic}", str(sugar), str(steps), _format_minutes(duration), str(score)])
            result_facts.extend([str(systolic), str(diastolic), str(sugar), str(steps), str(duration), str(score)])
        else:
            raise ValueError(f"Unknown multi metric: {metric}")
    return ExpectedFacts(
        result_names_exact=[item["name"] for item in residents],
        answer_contains=answer_facts,
        result_contains=result_facts,
    )


def _named_average_metric_facts(name: str, community_id: int, metric: str, interpretation: bool = False) -> ExpectedFacts:
    item = _resident_by_name(name, community_id)
    facts = [item["name"], "Window: over the last 20 recorded days"]
    if metric == "bp":
        systolic, diastolic, _sugar = SEED_HEALTH[item["id"]]
        facts.extend([f"{float(systolic):.1f}/{float(diastolic):.1f}", "mmHg"])
    elif metric == "sleep_score":
        _duration, score = SEED_SLEEP[item["id"]]
        facts.append(f"{float(score):.1f}")
        if interpretation:
            facts.append("not flagged as low")
    else:
        facts.append(str(_metric_value(item, metric)))
    return ExpectedFacts(
        result_names_exact=[item["name"]],
        answer_contains=facts,
        result_contains=[item["name"]],
    )


def _score_seed_care(item: dict[str, Any]) -> dict[str, Any]:
    systolic, diastolic, sugar = SEED_HEALTH[item["id"]]
    sleep_duration, sleep_score = SEED_SLEEP[item["id"]]
    steps = SEED_ACTIVITY[item["id"]]
    score = 0

    if item["age"] >= 85:
        score += 2
    elif item["age"] >= 75:
        score += 1

    if systolic >= 160 or diastolic >= 100:
        score += 3
    elif systolic >= 140 or diastolic >= 90:
        score += 2
    elif systolic >= 130 or diastolic >= 85:
        score += 1

    if sugar >= 180:
        score += 3
    elif sugar >= 140:
        score += 2
    elif sugar >= 125:
        score += 1

    if sleep_score < 50:
        score += 2
    elif sleep_score < 60:
        score += 1

    if sleep_duration < 300:
        score += 2
    elif sleep_duration < 360:
        score += 1

    if steps < 2500:
        score += 2
    elif steps < 3500:
        score += 1

    history_text = item["history"].lower()
    for keyword in ("diabetes", "hypertension", "cardiovascular", "cardiac", "post-surgery", "asthma", "osteoporosis"):
        if keyword in history_text:
            score += 1

    if score >= 9:
        priority = "High"
    elif score >= 5:
        priority = "Moderate"
    else:
        priority = "Routine"

    return {
        **item,
        "bp": f"{systolic}/{diastolic}",
        "sugar": sugar,
        "steps": steps,
        "sleep_duration": sleep_duration,
        "sleep_score": sleep_score,
        "care_score": score,
        "care_priority": priority,
    }


def _care_rows(community_id: int) -> list[dict[str, Any]]:
    return sorted(
        [_score_seed_care(item) for item in _residents(community_id)],
        key=lambda row: (-row["care_score"], row["name"]),
    )


def _care_facts(community_id: int, visible_count: int | None = None, named: str | None = None) -> ExpectedFacts:
    rows = _care_rows(community_id)
    if named:
        item = next(row for row in rows if row["name"].lower() == named.lower())
        facts = [
            item["name"],
            item["care_priority"],
            str(item["care_score"]),
            item["bp"],
            str(item["sugar"]),
            str(item["sleep_score"]),
            str(item["steps"]),
        ]
        return ExpectedFacts(result_names_exact=[item["name"]], answer_contains=facts, result_contains=facts)

    visible = rows[:visible_count] if visible_count else rows
    visible_names = [item["name"] for item in visible]
    hidden_names = [item["name"] for item in rows[len(visible):]]
    facts = []
    for item in visible:
        facts.extend([item["name"], item["care_priority"], str(item["care_score"])])
    return ExpectedFacts(
        result_names_exact=[item["name"] for item in rows],
        answer_contains=facts,
        answer_not_contains=hidden_names if visible_count else [],
    )


def _multi_care_facts(community_id: int, names: list[str]) -> ExpectedFacts:
    rows = _care_rows(community_id)
    name_set = {name.lower() for name in names}
    items = [
        row for row in _residents(community_id)
        if row["name"].lower() in name_set
    ]
    scored = [
        next(row for row in rows if row["name"] == item["name"])
        for item in items
    ]
    non_requested = [
        row["name"]
        for row in _residents(community_id)
        if row["name"].lower() not in name_set
    ]
    facts: list[str] = []
    result_facts: list[str] = []
    for item in scored:
        systolic, diastolic, _sugar = SEED_HEALTH[item["id"]]
        facts.extend([
            item["name"],
            item["care_priority"],
            str(item["care_score"]),
            item["bp"],
            str(item["sugar"]),
            str(item["sleep_score"]),
            str(item["steps"]),
        ])
        result_facts.extend([
            item["name"],
            item["care_priority"],
            str(item["care_score"]),
            str(systolic),
            str(diastolic),
            str(item["sugar"]),
            str(item["sleep_score"]),
            str(item["steps"]),
        ])
    return ExpectedFacts(
        result_names_exact=[item["name"] for item in scored],
        answer_contains=facts,
        answer_not_contains=non_requested,
        result_contains=result_facts,
    )


def _oldest_care_facts(community_id: int) -> ExpectedFacts:
    rows = _care_rows(community_id)
    oldest = max(_residents(community_id), key=lambda row: (row["age"], row["name"]))
    scored_oldest = next(row for row in rows if row["id"] == oldest["id"])
    return ExpectedFacts(
        result_names_exact=[item["name"] for item in rows],
        result_names_prefix=[oldest["name"]],
        answer_contains=[
            oldest["name"],
            str(oldest["age"]),
            scored_oldest["care_priority"],
            str(scored_oldest["care_score"]),
        ],
    )


def _average_metric_facts(community_id: int, metric: str) -> ExpectedFacts:
    residents = _residents(community_id)
    if metric == "bp":
        systolic = round(sum(SEED_HEALTH[item["id"]][0] for item in residents) / len(residents), 1)
        diastolic = round(sum(SEED_HEALTH[item["id"]][1] for item in residents) / len(residents), 1)
        facts = [f"{systolic:.1f}", f"{diastolic:.1f}"]
    else:
        raise ValueError(f"Unknown average metric: {metric}")
    return ExpectedFacts(answer_contains=facts, result_contains=facts)


def _ranking_facts(community_id: int, metric: str, descending: bool = False) -> ExpectedFacts:
    rows = sorted(
        _residents(community_id),
        key=lambda item: (_metric_value(item, metric), item["name"]),
        reverse=descending,
    )
    item = rows[0]
    value = _metric_value(item, metric)
    return ExpectedFacts(
        result_names_exact=[item["name"]],
        answer_contains=[item["name"], str(value)],
        result_contains=[item["name"], str(value)],
    )


def _device_details_facts(board_id: str) -> ExpectedFacts:
    row = next(device for device in SEED_DEVICES if device[0] == board_id)
    facts = [str(value) for value in row[:5]]
    return ExpectedFacts(result_names_exact=[board_id], answer_contains=facts, result_contains=facts)


def _device_ranking_facts(metric: str, descending: bool = False) -> ExpectedFacts:
    metric_indexes = {"signal": 2, "uptime": 3, "cpu": 4}
    idx = metric_indexes[metric]
    row = sorted(SEED_DEVICES, key=lambda item: (item[idx], item[0]), reverse=descending)[0]
    facts = [row[0], row[1], str(row[idx])]
    return ExpectedFacts(result_names_exact=[row[0]], answer_contains=facts, result_contains=facts)


ROUTE_CASES = [
    RouteCase("what is atorvastatin?", "CHAT", "medical_education"),
    RouteCase("what is bp and how is it measured?", "CHAT", "medical_education"),
    RouteCase("what is diabetes?", "CHAT", "medical_education"),
    RouteCase("what is the ideal sleep score?", "CHAT", "metric_guidance"),
    RouteCase("how many steps is good?", "CHAT", "metric_guidance"),
    RouteCase("what is a good bp?", "CHAT", "metric_guidance"),
    RouteCase("what is score 12 in high priority?", "CHAT", "care_guidance"),
    RouteCase("how is care score calculated?", "CHAT", "care_guidance"),
    RouteCase("what is care priority?", "CHAT", "care_guidance"),
    RouteCase("write a short thank you note", "CHAT", "general_chat"),
    RouteCase("who takes atorvastatin?", "SQL", "resident_lookup"),
    RouteCase("which residents have diabetes?", "SQL", "resident_lookup"),
    RouteCase("how old is Rishi?", "SQL", "resident_profile"),
    RouteCase("where does Rishi stay?", "SQL", "resident_profile"),
    RouteCase("what medication is Rishi prescribed?", "SQL", "resident_profile"),
    RouteCase("what is Meera Krishnan's blood pressure?", "SQL", "named_metric"),
    RouteCase("what is rishis current sugar?", "SQL", "named_metric"),
    RouteCase("what is rishis average sleep score?", "SQL", "named_metric"),
    RouteCase("what is DEV2 status?", "SQL", "device"),
    RouteCase("who has the lowest sleep quality score?", "SQL", "metric_ranking"),
    RouteCase("what is sleep quality score", "RAG", "documentation"),
]


SQL_CASES = [
    SQLCase(
        "give details of meera krishnan",
        2,
        "resident_profile",
        oracle=lambda: _profile_facts("Meera Krishnan", 2),
    ),
    SQLCase(
        "give details of priya saxena and leela varma",
        3,
        "resident_profile",
        oracle=lambda: _multi_profile_facts(["Priya Saxena", "Leela Varma"], 3),
        macro="multi_resident_profile",
    ),
    SQLCase(
        "how old is Rishi?",
        2,
        "resident_profile",
        oracle=lambda: ExpectedFacts(
            result_names_exact=["Rishi Nambiar"],
            answer_contains=["Rishi Nambiar", "71"],
            result_contains=["Rishi Nambiar", "71"],
        ),
    ),
    SQLCase(
        "where does Rishi stay?",
        2,
        "resident_profile",
        oracle=lambda: ExpectedFacts(
            result_names_exact=["Rishi Nambiar"],
            answer_contains=["Rishi Nambiar", "B-204"],
            result_contains=["Rishi Nambiar", "B-204"],
        ),
    ),
    SQLCase(
        "what medication is Rishi prescribed?",
        2,
        "resident_profile",
        oracle=lambda: ExpectedFacts(
            result_names_exact=["Rishi Nambiar"],
            answer_contains=["Rishi Nambiar", "Paracetamol as needed"],
            result_contains=["Rishi Nambiar", "Paracetamol as needed"],
        ),
    ),
    SQLCase(
        "what are priya and leela ages?",
        3,
        "resident_profile",
        oracle=lambda: _multi_profile_field_facts(["Priya Saxena", "Leela Varma"], 3, "age"),
        macro="multi_resident_profile",
    ),
    SQLCase(
        "who is older priya or leela?",
        3,
        "resident_profile",
        oracle=lambda: _multi_profile_field_facts(["Priya Saxena", "Leela Varma"], 3, "age"),
        macro="multi_resident_profile",
    ),
    SQLCase(
        "who is older among priya saxena, karan oberoi, and leela varma?",
        3,
        "resident_profile",
        oracle=lambda: _multi_profile_field_facts(["Priya Saxena", "Karan Oberoi", "Leela Varma"], 3, "age"),
        macro="multi_resident_profile",
    ),
    SQLCase(
        "what is bp of priya and leela?",
        3,
        "named_metric",
        oracle=lambda: _multi_metric_facts(["Priya Saxena", "Leela Varma"], 3, "bp"),
        macro="multi_resident_metric",
    ),
    SQLCase(
        "which of priya and leela has higher bp?",
        3,
        "named_metric",
        oracle=lambda: _multi_metric_facts(["Priya Saxena", "Leela Varma"], 3, "bp"),
        macro="multi_resident_metric",
    ),
    SQLCase(
        "which of priya saxena, karan oberoi, and leela varma has higher blood pressure?",
        3,
        "named_metric",
        oracle=lambda: _multi_metric_facts(["Priya Saxena", "Karan Oberoi", "Leela Varma"], 3, "bp"),
        macro="multi_resident_metric",
    ),
    SQLCase(
        "what are john and ravi sleep scores?",
        1,
        "named_metric",
        oracle=lambda: _multi_metric_facts(["John Mathew", "Ravi Kumar"], 1, "sleep_score"),
        macro="multi_resident_metric",
    ),
    SQLCase(
        "who has lower sleep score john or ravi?",
        1,
        "named_metric",
        oracle=lambda: _multi_metric_facts(["John Mathew", "Ravi Kumar"], 1, "sleep_score"),
        macro="multi_resident_metric",
    ),
    SQLCase(
        "compare priya and leela health metrics",
        3,
        "named_metric",
        oracle=lambda: _multi_metric_facts(["Priya Saxena", "Leela Varma"], 3, "all_metrics"),
        macro="multi_resident_metric",
    ),
    SQLCase(
        "which of priya and leela needs more care?",
        3,
        "care_priority",
        oracle=lambda: _multi_care_facts(3, ["Priya Saxena", "Leela Varma"]),
        macro="deterministic_care_assessment",
    ),
    SQLCase(
        "give me the list of residents with hypertension",
        2,
        "condition_lookup",
        oracle=lambda: _text_search_facts(2, ["hypertension"]),
        macro="resident_text_search",
    ),
    SQLCase(
        "who takes atorvastatin?",
        2,
        "medication_lookup",
        oracle=lambda: _text_search_facts(2, ["atorvastatin"]),
        macro="resident_text_search",
    ),
    SQLCase(
        "who has high blood pressure?",
        2,
        "threshold",
        oracle=lambda: _high_bp_facts(2),
        macro="metric_threshold",
    ),
    SQLCase(
        "what is Ravi's sleep quality score?",
        1,
        "named_metric",
        oracle=lambda: _named_metric_facts("Ravi Kumar", 1, "sleep_score"),
        macro="named_resident_metric",
    ),
    SQLCase(
        "what is rishis average bp?",
        2,
        "named_metric",
        oracle=lambda: _named_average_metric_facts("Rishi Nambiar", 2, "bp"),
        macro="named_resident_average_metric",
    ),
    SQLCase(
        "is rishis average sleep score good or bad?",
        2,
        "named_metric",
        oracle=lambda: _named_average_metric_facts("Rishi Nambiar", 2, "sleep_score", interpretation=True),
        macro="named_resident_average_metric",
    ),
    SQLCase(
        "which 1 person needs the most care?",
        1,
        "care_priority",
        oracle=lambda: _care_facts(1, visible_count=1),
        macro="deterministic_care_assessment",
    ),
    SQLCase(
        "does rishi require more care?",
        2,
        "care_priority",
        oracle=lambda: _care_facts(2, named="Rishi Nambiar"),
        macro="deterministic_care_assessment",
    ),
    SQLCase(
        "who is the oldest and needs most care?",
        2,
        "care_priority",
        oracle=lambda: _oldest_care_facts(2),
        macro="deterministic_care_assessment",
    ),
    SQLCase(
        "what is the average bp?",
        1,
        "aggregate",
        oracle=lambda: _average_metric_facts(1, "bp"),
        macro="resident_average_metric",
    ),
    SQLCase(
        "which resident has the lowest step count?",
        2,
        "metric_ranking",
        oracle=lambda: _ranking_facts(2, "steps"),
    ),
    SQLCase(
        "what is DEV2 status?",
        1,
        "device",
        oracle=lambda: _device_details_facts("DEV2"),
        macro="device_details",
    ),
    SQLCase(
        "give list of devices",
        1,
        "device",
        oracle=lambda: ExpectedFacts(
            result_names_exact=[row[0] for row in SEED_DEVICES],
            answer_contains=[row[0] for row in SEED_DEVICES],
        ),
        macro="device_list",
    ),
    SQLCase(
        "which device has the weakest signal?",
        1,
        "device",
        oracle=lambda: _device_ranking_facts("signal"),
        macro="device_ranking",
    ),
]


MEMORY_CASES = [
    MemoryCase(
        "what is bp and how is it measured?",
        "what is bp and how is it measured?",
        [
            {
                "user": "does rishi require more care?",
                "ai": (
                    "Rishi Nambiar is routine priority. Recorded values: BP 132/82, "
                    "sugar 113.2, sleep score 64, sleep duration 326 minutes, steps 2074."
                ),
            }
        ],
        "memory_general_question_bypass",
    ),
    MemoryCase(
        "what is his bp?",
        "What is Ravi Kumar's blood pressure?",
        [
            {
                "user": "give details of ravi kumar",
                "ai": "Name: Ravi Kumar\nAddress: A-103\nAge: 74",
            }
        ],
        "memory_named_followup",
    ),
    MemoryCase(
        "what are their ages?",
        "What are the ages of residents in this community?",
        [
            {
                "user": "give the list of residents",
                "ai": "Residents in this community:\n1. John Mathew (A-101)\n2. Ravi Kumar (A-103)",
            }
        ],
        "memory_collection_followup",
    ),
    MemoryCase(
        "among these who is the oldest?",
        "Who is older among Priya Saxena, Karan Oberoi, and Leela Varma?",
        [
            {
                "user": "give details of priya leela and karan",
                "ai": (
                    "Resident details:\n"
                    "- Priya Saxena (ID 12, C-302, 70 years)\n"
                    "- Karan Oberoi (ID 13, C-303, 73 years)\n"
                    "- Leela Varma (ID 14, C-304, 76 years)"
                ),
            }
        ],
        "memory_named_set_followup",
    ),
    MemoryCase(
        "what is his average sleep score?",
        "What is Rishi Nambiar's average sleep quality score?",
        [
            {
                "user": "what is rishis sleep score?",
                "ai": (
                    "Rishi Nambiar's latest sleep quality score is 64.\n\n"
                    "What this means: Sleep quality score is a care-review signal.\n\n"
                    "Next step: Check Rishi Nambiar's sleep duration, activity, and device sync status."
                ),
            }
        ],
        "memory_named_average_followup",
    ),
    MemoryCase(
        "is it good or bad?",
        "Is Rishi Nambiar's average sleep quality score good or bad?",
        [
            {
                "user": "what is his average sleep score?",
                "ai": "Rishi Nambiar's average sleep score is 64.0. Window: over the last 20 recorded days.",
            }
        ],
        "memory_average_interpretation_followup",
    ),
    MemoryCase(
        "what is his current bp?",
        "What is Rishi Nambiar's blood pressure?",
        [
            {
                "user": "what is rishis average bp?",
                "ai": "Rishi Nambiar's average blood pressure is 132.0/82.0 mmHg.",
            }
        ],
        "memory_current_metric_followup",
    ),
]


def _plan_macro(response: dict[str, Any]) -> str | None:
    plan = response.get("plan") or {}
    if not isinstance(plan, dict):
        return None
    return plan.get("_macro") or plan.get("macro")


def run_route_cases() -> list[CheckResult]:
    router = load_router_with_stubs()
    results: list[CheckResult] = []
    for case in ROUTE_CASES:
        actual = router.classify_intent(case.query)
        results.append(CheckResult(
            category=case.category,
            case=case.query,
            check="route",
            passed=actual == case.expected_route,
            expected=case.expected_route,
            actual=actual,
        ))
    return results


def run_sql_cases() -> list[CheckResult]:
    sql_retriever = load_sql_retriever()
    seed_db = SeedQueryRunner()
    sql_retriever.run_query = seed_db.run_query

    results: list[CheckResult] = []
    for case in SQL_CASES:
        response = sql_retriever.handle_sql(case.query, community_id=case.community_id)
        answer = str(response.get("answer", ""))
        result = response.get("result")
        result_text = _flatten_text(result)
        actual_result_names = _actual_result_names(result)
        expected = case.oracle()

        if case.macro:
            actual_macro = _plan_macro(response) or ""
            results.append(CheckResult(
                category=case.category,
                case=case.query,
                check="macro",
                passed=actual_macro == case.macro,
                expected=case.macro,
                actual=actual_macro,
            ))

        if expected.result_names_exact is not None:
            results.append(CheckResult(
                category=case.category,
                case=case.query,
                check="retrieved_names_exact",
                passed=actual_result_names == expected.result_names_exact,
                expected=json.dumps(expected.result_names_exact),
                actual=json.dumps(actual_result_names),
            ))

        if expected.result_names_prefix is not None:
            actual_prefix = actual_result_names[:len(expected.result_names_prefix)]
            results.append(CheckResult(
                category=case.category,
                case=case.query,
                check="retrieved_names_prefix",
                passed=actual_prefix == expected.result_names_prefix,
                expected=json.dumps(expected.result_names_prefix),
                actual=json.dumps(actual_prefix),
            ))

        for fact in expected.result_contains:
            fact_text = str(fact)
            results.append(CheckResult(
                category=case.category,
                case=case.query,
                check="retrieved_fact",
                passed=fact_text in result_text,
                expected=fact_text,
                actual=result_text,
            ))

        for fact in expected.answer_contains:
            fact_text = str(fact)
            results.append(CheckResult(
                category=case.category,
                case=case.query,
                check="answer_grounded_fact",
                passed=fact_text in answer,
                expected=fact_text,
                actual=answer,
            ))

        for forbidden in expected.answer_not_contains:
            results.append(CheckResult(
                category=case.category,
                case=case.query,
                check="answer_excludes_unretrieved_name",
                passed=forbidden not in answer,
                expected=f"not {forbidden}",
                actual=answer,
            ))
    return results


def run_memory_cases() -> list[CheckResult]:
    memory = load_memory_with_stubs()
    results: list[CheckResult] = []
    for index, case in enumerate(MEMORY_CASES, start=1):
        session_id = f"eval-{index}"
        memory._memory_fallback[session_id] = case.history
        actual = memory.rewrite_query_with_memory(session_id, case.query)
        results.append(CheckResult(
            category=case.category,
            case=case.query,
            check="rewrite",
            passed=actual == case.expected_rewrite,
            expected=case.expected_rewrite,
            actual=actual,
        ))
    return results


def summarize(results: list[CheckResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    by_category: dict[str, dict[str, Any]] = {}
    for result in results:
        bucket = by_category.setdefault(result.category, {"passed": 0, "total": 0, "accuracy": 0.0})
        bucket["total"] += 1
        if result.passed:
            bucket["passed"] += 1

    for bucket in by_category.values():
        bucket["accuracy"] = round(bucket["passed"] / bucket["total"], 4) if bucket["total"] else 0.0

    return {
        "passed": passed,
        "total": total,
        "accuracy": round(passed / total, 4) if total else 0.0,
        "by_category": dict(sorted(by_category.items())),
        "failures": [
            {
                "category": result.category,
                "case": result.case,
                "check": result.check,
                "expected": result.expected,
                "actual": result.actual,
            }
            for result in results
            if not result.passed
        ],
    }


def print_text_report(summary: dict[str, Any]) -> None:
    score = summary["accuracy"] * 100
    print("KuboCare Retrieval Regression Evaluation")
    print(f"Overall regression score: {score:.1f}% ({summary['passed']}/{summary['total']} checks passed)")
    print("Scope: fixed question set, seeded database oracle, route/retrieval/grounding checks. Not live production accuracy.")
    print("")
    print("By category:")
    for category, bucket in summary["by_category"].items():
        print(f"- {category}: {bucket['accuracy'] * 100:.1f}% ({bucket['passed']}/{bucket['total']})")

    if summary["failures"]:
        print("")
        print("Failures:")
        for failure in summary["failures"]:
            print(f"- [{failure['category']}] {failure['case']} ({failure['check']})")
            print(f"  expected: {failure['expected']}")
            print(f"  actual: {failure['actual']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate local KuboCare retrieval/routing accuracy.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--fail-under", type=float, default=None, help="Exit non-zero if accuracy is below this percent.")
    args = parser.parse_args()

    results = run_route_cases() + run_sql_cases() + run_memory_cases()
    summary = summarize(results)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print_text_report(summary)

    if args.fail_under is not None and summary["accuracy"] * 100 < args.fail_under:
        return 1
    return 0 if not summary["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
