# Clinical Data Quality And Safety Guide

## Missing Health Readings

Missing health readings occur when an expected resident metric is not available in the structured database. This may happen because a device was offline, a resident was not wearing a device, a sensor failed, a gateway did not sync, or the data has not been entered yet.

The assistant should not treat missing data as normal or abnormal. It should state that the reading is unavailable and suggest checking device status, synchronization, and care notes.

## Stale Timestamp Handling

A stale timestamp means the latest recorded value may not represent the resident's current state. The assistant should include the timestamp when available and avoid presenting old data as live monitoring.

If the user asks for the current state and only old data is available, the answer should say that the system has a recorded value but not a confirmed current value.

## Duplicate Or Conflicting Readings

Duplicate or conflicting readings can occur when a device retries uploads, multiple devices report for the same resident, or manual and automated entries overlap. Conflicting readings should be reviewed before the assistant summarizes a trend.

When conflicting readings are present, the assistant should report the conflict and avoid choosing a clinical conclusion unless the database or approved protocol identifies the authoritative value.

## Device Offline During Resident Review

If a device is offline during resident review, the assistant should separate resident data from monitoring reliability. A resident's latest stored value may still be available, but the absence of live device status can reduce confidence in current monitoring.

Device offline issues should be routed to technical review when they affect resident monitoring, repeated synchronization, or recent metric availability.

## Manual Entry Versus Device Reading

Manual entries and device readings may have different reliability considerations. The assistant should use the source recorded in the database when available and should not assume that one source is always more accurate.

If a manual entry conflicts with a device reading, the care team should review the source, timestamp, and context before acting on the value.

## Audit And Traceability

Audit and traceability help explain where an answer came from. Production responses should include enough trace information for support teams to investigate errors without exposing sensitive internal details to end users.

The assistant should preserve trace IDs in responses and logs. Raw SQL, internal prompts, database credentials, and full retrieved context should not be shown to normal users.

## Safe Language For Health Summaries

Safe health summaries use cautious, evidence-based wording. The assistant should say "recorded value", "may require review", "available data shows", or "care team should verify" when discussing resident health data.

The assistant should avoid phrases that imply diagnosis, certainty, or direct treatment advice. Examples to avoid include "the resident has a disease", "change the medication", or "this is definitely an emergency" unless approved emergency protocol text explicitly requires escalation.
