# Resident Care Workflow And Handoff

## Daily Wellness Review

Daily wellness review is the care team's routine check of resident data, recent alerts, and operational notes. It can include sleep quality, sleep duration, activity steps, blood pressure, sugar level, device status, and unresolved escalation items.

The assistant should summarize only the data available in the system. If a metric is missing, stale, or unavailable, it should say so clearly instead of filling the gap with assumptions.

## Shift Handoff Summary

Shift handoff summary helps one care team pass relevant resident and device context to the next team. A useful handoff should separate resident health observations from device or data-quality issues.

A handoff summary should include resident name, relevant recorded metrics, unresolved alerts, device connectivity concerns, and any documented escalation status. It should not include unrelated residents or unrelated community data.

## Medication Intake Documentation

Medication intake documentation describes prescribed intake information stored for care coordination. The assistant may retrieve and summarize prescribed intake from the structured database, but it must not change the prescription, recommend dosage changes, or tell the resident to start or stop medication.

If a medication question asks for a resident's prescribed intake, use SQL. If the question asks how medication information should be handled or escalated, use documentation.

## Fall Risk Review

Fall risk review is an operational review for residents who may need closer attention because of reduced mobility, low activity, poor sleep, recent clinical concerns, or care team notes. The assistant should not declare that a resident will fall or diagnose a fall-related condition.

If a user asks which resident may need more fall-risk review, the assistant should rely on structured resident data and explain that the result is a care prioritization signal, not a diagnosis.

## Reduced Mobility Follow-Up

Reduced mobility follow-up is used when a resident shows low activity, fewer steps, or a care note related to mobility. Low step count alone is not enough to determine the cause. It may reflect limited movement, device non-wear, missed synchronization, or a temporary operational issue.

The assistant should suggest checking recent activity history, device status, and relevant care notes before escalating.

## Hydration And Nutrition Notes

Hydration and nutrition notes are care-context entries that may be used during wellness review. The assistant should only discuss hydration or nutrition when the information is present in approved documentation or structured notes.

The assistant must not invent diet plans, fluid targets, or clinical instructions. If the user asks for resident-specific hydration or nutrition details and the database does not contain them, the assistant should say that the information is not available.

## Family Or Care Coordinator Update

Family or care coordinator updates should be concise, factual, and based on available records. They should avoid raw technical details unless the device issue affects monitoring reliability.

A safe update includes what was observed, whether the data came from recorded metrics or device status, and whether the care team has reviewed or escalated the item.
