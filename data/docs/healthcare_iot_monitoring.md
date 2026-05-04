# Healthcare IoT Monitoring Operations Guide

## Scope

KuboCare healthcare IoT monitoring combines resident wellness data, device telemetry, and operational alerts. The documentation in this guide is intended for support teams, nurses, care coordinators, and technical operators who need to understand how device signals should be interpreted in a care environment. Resident-specific facts such as a resident's age, flat number, sleep score, blood pressure, glucose reading, or medication list must be retrieved from the structured clinical database, not inferred from this documentation.

## Monitoring Categories

The platform separates information into three broad categories:

1. Resident clinical metrics such as blood pressure, sugar level, sleep quality score, sleep duration, and activity steps.
2. Device telemetry such as WiFi signal strength, gateway connectivity, battery state, firmware version, uptime, CPU load, and sensor calibration state.
3. Operational documentation such as troubleshooting instructions, escalation policies, maintenance procedures, and alert interpretation.

When a user asks for a specific resident's data, the SQL database is the source of truth. When a user asks what an alert, code, or device behavior means, the documentation index is the source of truth.

## Resident Metric Interpretation

Resident metrics should be interpreted conservatively. A single abnormal reading should not be treated as a diagnosis. The assistant may summarize the retrieved database value and mention that elevated or reduced values may require clinical review, but it must not prescribe medication, diagnose a condition, or recommend emergency treatment unless the approved documentation explicitly says to escalate.

Blood pressure readings are commonly represented as systolic over diastolic. A high systolic or diastolic value may indicate that the care team should review the resident's latest clinical context. The assistant should include the actual value and timestamp when available.

Sleep quality scores are ranking metrics used for wellness trend review. Higher sleep quality scores indicate better sleep quality. Lower sleep quality scores indicate poorer sleep quality. Ranking questions such as best, worst, second best, top three, or bottom two should be answered from the structured database.

Activity step counts are operational wellness indicators. Higher step counts may reflect more physical activity, while lower step counts may reflect limited movement, reduced mobility, or missing device data. The assistant should not assume clinical cause without database context.

## Device Telemetry Interpretation

Device telemetry describes whether the monitoring hardware is operating normally. Telemetry does not itself diagnose a resident. For example, a low WiFi signal means the device may have connectivity issues; it does not mean the resident has a medical issue.

Signal strength should be interpreted as a connectivity quality indicator. A weaker signal may cause delayed uploads, missed synchronization windows, or intermittent status changes. Gateway connectivity failures should be handled as infrastructure issues first.

CPU load and uptime describe device health. High CPU load may occur during firmware updates, batch uploads, local processing, or retry loops. Uptime should be used to determine whether the device restarted unexpectedly.

## Documentation Answering Rules

Documentation answers should be grounded only in retrieved documentation chunks. If the documentation does not contain the answer, the assistant should say that it could not find the answer in the documentation. It should not fill missing operational rules with general internet knowledge.

Documentation answers should be concise. For troubleshooting questions, use short points with the following structure when useful:

1. Meaning
2. What to do
3. What not to do
4. When to check or escalate

## Escalation Principles

Escalate to a technical operator when a device repeatedly fails to connect, reports persistent firmware update failure, enters repeated reboot cycles, or produces missing data for a monitored resident.

Escalate to a clinical operator when the structured database returns a resident metric that is outside the organization's clinical review range and the care protocol requires review. The documentation can describe escalation principles, but the actual resident value must come from the SQL database.

## Data Quality

Data quality issues should be handled before drawing conclusions. Missing readings, stale timestamps, duplicate readings, mismatched resident identifiers, or disconnected devices can produce misleading summaries. If the latest data is not available, the assistant should say that clearly.

When a device is offline or cannot sync, the latest database value may not represent the current resident state. In such cases, the assistant should distinguish between recorded data and real-time status.
