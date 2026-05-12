# Resident Vital Signs And Metric Review

## Blood Pressure Review

Blood pressure review is an operational care workflow for checking recorded systolic and diastolic values from the structured database. The assistant may explain what the values represent, but the latest resident-specific reading must come from SQL.

When discussing blood pressure, include the resident name, the recorded value, and the timestamp if the database returns it. Do not diagnose hypertension, change medication, or tell a resident to start or stop treatment. If the value is outside the organization's clinical review range, say that the recorded value may require clinical review.

## Sugar Level Review

Sugar level review is used to summarize recorded glucose or sugar values for care team awareness. The assistant should report the value retrieved from the database and avoid unsupported clinical interpretation.

If a sugar level appears outside the organization's review range, the assistant may recommend that the care team review the recorded value. It should not label the resident as diabetic, prescribe diet changes, or give medication instructions unless those instructions are already present in approved care documentation.

## Sleep Quality Review

Sleep quality review uses recorded sleep quality scores and sleep duration to support wellness monitoring. Higher sleep quality scores indicate better sleep quality in this dataset. Lower scores indicate poorer sleep quality or a possible need for care team review.

Sleep answers should distinguish between ranking questions and concept questions. Ranking questions such as best sleep score, worst sleep score, or longest sleep duration must use the structured database. Concept questions such as what sleep quality score means may use documentation.

## Activity And Step Count Review

Activity and step count review is used to understand resident movement patterns from recorded activity data. Higher step counts may reflect more movement, while lower step counts may reflect reduced mobility, device non-wear, missed synchronization, or a care concern.

The assistant should not assume the reason for low activity without supporting data. If activity is unusually low or missing, the assistant should mention that device status and data freshness should be checked before drawing conclusions.

## Combined Metric Review

Combined metric review considers several recorded signals together, such as blood pressure, sugar level, sleep quality, sleep duration, activity steps, age, and medical history. This can help care teams decide which residents may need attention.

The assistant may rank or summarize residents using recorded data, but it should avoid diagnosis. Phrases such as "may require review", "recorded values suggest follow-up", or "care team should review the data" are safer than definitive clinical statements.

## Data Freshness Before Clinical Review

Before presenting a health summary, check whether the data is current enough for the user's request. A stale timestamp, missing latest reading, disconnected device, or failed sync can make a health summary misleading.

If the latest reading is stale or missing, the assistant should say that the available value is recorded data and may not represent the resident's current state.

## What Not To Say

The assistant must not diagnose residents, prescribe medication, override clinician judgment, or claim certainty from a single metric. It must not use documentation as the source for resident-specific values.

Use cautious wording when the answer involves clinical meaning. The documentation can explain review workflows, but the structured database is the source of truth for resident values.
