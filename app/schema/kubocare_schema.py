# ===========================================================================
# This file is the master map of the database — every table and column the app
# knows about. Other parts use it to check that a query only touches real,
# approved tables, to tell the AI what data exists, and to know which columns
# hold private information. Update it here whenever the real database changes.
# ===========================================================================
"""Kubocare production schema — single source of truth.

Mirrors `data/schema.sql` (~40 tables, 13 enums). Used by:
  - SQL safety validator (allowlist)
  - LLM SQL planner prompt (schema-for-LLM rendering, with pruning)
  - Rule router (column lookups, join paths)
  - Output guardrail (PHI column registry)

Pure data + pure helpers. No I/O, no DB connections. Update this file when
the real schema changes (Alembic migrations land).
"""

from __future__ import annotations

from typing import Iterable, Mapping


# ---------------------------------------------------------------------------
# Enums (from CREATE TYPE statements in schema.sql)
# ---------------------------------------------------------------------------

ENUMS: Mapping[str, tuple[str, ...]] = {
    "eventcategoryenum": (
        "alert", "new_resident", "fall_alert", "suspected_alert",
        "confirmed_fall", "false_alert", "forwarded", "test", "resolved",
        "movement", "zenzo_call", "unresolved_alert", "escalated",
        "dim_movement", "out_of_bed", "out_of_room",
    ),
    "genderenum": ("male", "female", "other"),
    "insightpriorityenum": ("low", "high", "mid"),
    "insighttypeenum": ("sleep", "activity", "vitals", "environment"),
    "objectstatusenum": ("good", "no_response"),
    "objecttypeenum": ("furniture", "sensor", "sensor_fds", "sensor_vitals"),
    "roompos": ("D", "L", "R", "U"),
    "severitytypeenum": ("LOW", "MEDIUM", "HIGH", "CRITICAL"),
    "sleepstageenum": ("light", "deep", "rem", "awake", "nonrem", "normal"),
    "sleeptypeenum": ("night", "day"),
    "statusenum": ("active", "inactive", "sleeping", "walking"),
    "statustypeenum": ("OPEN", "CLOSED", "INVESTIGATING"),
    "summarytypeenum": ("sleep", "activity", "vitals", "environment", "fall"),
    "temperature_unit_enum": ("C", "F", "K"),
    "timeintervalenum": ("hourly", "daily"),
}


# ---------------------------------------------------------------------------
# SCHEMA — { table: { "columns": {col: type}, "purpose": str } }
#
# Shape kept compatible with the legacy app/schema/schema.py contract:
# - SCHEMA[table]["columns"] is consumed by safety.py for the allowlist
# - schema_to_text(SCHEMA) is consumed by app/llm/client.py
#
# "purpose" is a 1-line plain-English description rendered into the LLM
# prompt so the planner understands what the table is for.
# ---------------------------------------------------------------------------

SCHEMA: Mapping[str, Mapping[str, object]] = {
    # ------------------------------------------------------------- Tenancy
    "tenants": {
        "columns": {
            "id": "uuid", "name": "text", "status": "text",
            "expires_at": "timestamptz", "config_version": "integer",
            "integration_config": "jsonb", "is_deleted": "boolean",
            "created_at": "timestamptz", "updated_at": "timestamptz",
        },
        "purpose": "Top-level tenant (customer company) row. UUID id.",
    },
    "tenant_credentials": {
        "columns": {
            "id": "integer", "api_key": "text", "api_secret_hash": "text",
            "is_active": "boolean", "expires_at": "timestamptz",
            "last_used_at": "timestamptz", "created_at": "timestamptz",
            "updated_at": "timestamptz", "tenant_id": "uuid",
        },
        "purpose": "API credentials per tenant. tenant_id FK to tenants.id.",
    },
    "organisation": {
        "columns": {
            "id": "integer", "name": "text", "city": "text",
            "headquarters_address": "text", "deleted_by": "integer",
            "is_deleted": "boolean", "created_at": "timestamptz",
            "updated_at": "timestamptz",
        },
        "purpose": "Customer organisation. Parent of communities.",
    },
    "community": {
        "columns": {
            "id": "integer", "name": "text", "address": "text",
            "capacity": "integer", "total_resident": "integer", "city": "text",
            "timezone_info": "text", "temperature_unit": "temperature_unit_enum",
            "deleted_by": "integer", "is_deleted": "boolean",
            "created_at": "timestamptz", "updated_at": "timestamptz",
            "home_type": "text", "organisation_id": "integer",
        },
        "purpose": "A physical facility/building. organisation_id FK to organisation.id. Primary tenant-scope key for the chatbot.",
    },
    "community_user_mapping": {
        "columns": {
            "id": "bigint", "community_id": "integer", "user_id": "integer",
            "deleted_by": "integer", "is_deleted": "boolean",
            "created_at": "timestamptz", "updated_at": "timestamptz",
        },
        "purpose": "Which staff users belong to which community. Used to scope the caller.",
    },

    # ------------------------------------------------------- Identity / RBAC
    "users": {
        "columns": {
            "id": "integer", "mobile": "text", "country_code": "text",
            "name": "text", "organization": "text", "email": "text",
            "pin": "text", "deleted_by": "integer", "is_deleted": "boolean",
            "last_login": "timestamptz", "created_at": "timestamptz",
            "updated_at": "timestamptz", "role_id": "integer", "city": "text",
            "address": "text", "attribute": "jsonb",
            "add_permissions": "jsonb", "remove_permissions": "jsonb",
            "timezone_info": "text", "first_login": "boolean",
            "rate_limit_config": "jsonb",
        },
        "purpose": "Staff/login users only (admin, center_owner, caregiver). Residents are NOT in this table — they live in resident_profile and are reached via room_resident_mapping.",
    },
    "roles": {
        "columns": {
            "id": "integer", "name": "text", "deleted_by": "integer",
            "is_deleted": "boolean", "created_at": "timestamptz",
            "updated_at": "timestamptz", "permissions": "jsonb",
        },
        "purpose": "Role definitions; users.role_id FK to here. permissions is JSONB.",
    },
    "user_hierarchy_mapping": {
        "columns": {
            "id": "integer", "parent_id": "integer", "child_id": "integer",
            "is_deleted": "boolean", "created_at": "timestamptz",
            "updated_at": "timestamptz",
        },
        "purpose": "Staff org chart. parent_id/child_id FK to users.id.",
    },
    "push_endpoints": {
        "columns": {
            "id": "bigint", "user_id": "integer", "provider": "text",
            "endpoint": "text", "p256dh": "text", "auth": "text",
            "device_type": "text", "device_id": "text", "user_agent": "text",
            "created_at": "timestamptz", "last_seen": "timestamptz",
            "is_valid": "boolean",
        },
        "purpose": "Registered phones/devices for push notifications. user_id FK to users.id.",
    },

    # ----------------------------------------------------------- Residents
    "resident_profile": {
        "columns": {
            "id": "integer", "name": "text", "image": "text",
            "flat_number": "text", "dob": "text", "gender": "text",
            "no_of_falls": "integer", "is_deleted": "boolean",
            "deleted_by": "integer", "created_at": "timestamptz",
            "updated_at": "timestamptz", "fall_alert": "boolean",
            "fall_suspected": "boolean", "movement_alert": "boolean",
            "dim_light_alert": "boolean", "outroom_alert": "boolean",
            "outbed_alert": "boolean", "distance_threshold": "float",
            "call_from_mobile": "text", "buzzer_config": "jsonb",
            "emergency_contacts": "jsonb[]", "trigger_settings": "jsonb",
            "medical_history": "text",
        },
        "purpose": "Canonical residents table. name, DOB, gender, flat_number, medical_history, fall flags. PHI-heavy.",
    },
    "room_resident_mapping": {
        "columns": {
            "id": "integer", "resident_id": "integer", "room_id": "integer",
            "deleted_by": "integer", "is_deleted": "boolean",
            "created_at": "timestamptz", "updated_at": "timestamptz",
        },
        "purpose": "Which resident lives in which room. room_id is UNIQUE (one resident per room). resident_id FK to resident_profile.id.",
    },

    # ------------------------------------------------------------ Facility
    "rooms": {
        "columns": {
            "id": "integer", "room_name": "text", "community_id": "integer",
            "width": "float", "length": "float", "room_pos": "roompos",
            "deleted_by": "integer", "is_deleted": "boolean",
            "created_at": "timestamptz", "updated_at": "timestamptz",
        },
        "purpose": "Physical rooms in a community. community_id FK to community.id.",
    },
    "objects": {
        "columns": {
            "id": "integer", "object_id": "text", "location": "text",
            "room_id": "integer", "image": "text", "start_x": "float",
            "start_z": "float", "end_x": "float", "end_z": "float",
            "rotation": "float", "object_type": "objecttypeenum",
            "status": "objectstatusenum", "sos_id": "text",
            "is_active": "boolean", "device_status": "text",
            "deleted_by": "integer", "is_deleted": "boolean",
            "created_at": "timestamptz", "updated_at": "timestamptz",
        },
        "purpose": "Furniture and sensors inside rooms. objects.object_id (text) matches sensor tables' board column. room_id FK to rooms.id.",
    },

    # ------------------------------------------------- Incidents & alerts
    "incidents": {
        "columns": {
            "id": "integer", "room_id": "integer",
            "event_category": "eventcategoryenum", "event_outcome": "text",
            "event_time": "timestamptz", "event_end_time": "timestamptz",
            "status": "boolean", "object_id": "text", "object_type": "text",
            "json_payload": "jsonb", "deleted_by": "integer",
            "is_deleted": "boolean", "resolve_type": "eventcategoryenum",
            "action_status": "jsonb", "call_status": "jsonb",
            "escalation_level": "integer",
            "last_escalation_time": "timestamptz",
            "created_at": "timestamptz", "updated_at": "timestamptz",
        },
        "purpose": "Fall/movement/out-of-bed events. room_id FK to rooms.id; resolve resident via room_resident_mapping.",
    },
    "notifications": {
        "columns": {
            "id": "integer", "event_category": "eventcategoryenum",
            "event_time": "timestamptz", "resident_id": "integer",
            "room_id": "integer", "status": "boolean", "message": "text",
            "resolve_type": "eventcategoryenum", "deleted_by": "integer",
            "is_deleted": "boolean", "created_at": "timestamptz",
            "updated_at": "timestamptz",
        },
        "purpose": "Alerts pushed to staff. resident_id FK to resident_profile.id; room_id FK to rooms.id.",
    },
    "security_incidents": {
        "columns": {
            "id": "bigint", "date": "date", "description": "text",
            "severity": "severitytypeenum", "status": "statustypeenum",
            "closed_date": "date", "is_resolved": "boolean", "remark": "text",
            "closed_by": "integer", "is_deleted": "boolean",
            "deleted_by": "integer", "created_at": "timestamptz",
            "updated_at": "timestamptz",
        },
        "purpose": "Severity-graded security/incident log (LOW/MEDIUM/HIGH/CRITICAL).",
    },
    "service_alert": {
        "columns": {
            "id": "bigint", "ingestion_time": "timestamptz",
            "service_name": "text", "slug": "text", "status": "boolean",
        },
        "purpose": "Platform-level health/service alerts.",
    },

    # --------------------------------------------- Sensor time-series
    # NOTE: These tables hold board (text) with NO FK to objects. Resolve
    # via objects.object_id = sensor.board (or .board_sn for fds).
    "vitals": {
        "columns": {
            "id": "bigint", "ingestion_time": "timestamptz",
            "hr": "float", "rr": "float", "board": "text",
        },
        "purpose": "Per-sample heart rate (hr) and respiration rate (rr). Identified by board (text).",
    },
    "motion": {
        "columns": {
            "id": "bigint", "ingestion_time": "timestamptz",
            "bodysigns": "float", "distance": "float", "x": "float",
            "y": "float", "z": "float", "board": "text",
        },
        "purpose": "Per-sample motion intensity and x/y/z. Identified by board.",
    },
    "ambience": {
        "columns": {
            "id": "bigint", "ingestion_time": "timestamptz", "temp": "float",
            "humidity": "float", "board": "text", "aqi_indoor": "float",
            "aqi_outdoor": "float", "ambient_noise": "float", "time": "text",
            "light": "float", "aqi": "float", "tvoc": "float", "eco2": "float",
            "location": "text",
        },
        "purpose": "Per-sample room environment (temp, humidity, AQI, light, noise, TVOC, eCO2).",
    },
    "on_bed": {
        "columns": {
            "id": "bigint", "ingestion_time": "timestamptz", "time": "text",
            "board": "text", "location": "text", "on_bed": "boolean",
        },
        "purpose": "Bed occupancy boolean stream.",
    },
    "fds": {
        "columns": {
            "id": "bigint", "ingestion_time": "timestamptz", "type": "text",
            "platform": "text", "report": "text", "board_sn": "text",
            "location": "text", "live": "integer", "fn": "bigint",
            "software_version": "text", "time": "text", "activity": "integer",
            "position": "text", "result": "text",
        },
        "purpose": "Fall-detection sensor (FDS) raw events. Uses board_sn (not board) — naming exception.",
    },
    "sos": {
        "columns": {
            "id": "bigint", "ingestion_time": "timestamptz", "time": "text",
            "board": "text", "button_action": "text", "sos_id": "text",
        },
        "purpose": "SOS button presses.",
    },
    "sleep_sessions": {
        "columns": {
            "id": "integer", "board": "text",
            "sleep_stage": "sleepstageenum",
            "start_duration": "timestamptz", "end_duration": "timestamptz",
            "sleep_type": "sleeptypeenum", "created_at": "timestamptz",
            "updated_at": "timestamptz",
        },
        "purpose": "Sleep session segments with stage (light/deep/rem/awake/...) and type (night/day).",
    },
    "toss": {
        "columns": {
            "id": "bigint", "ingestion_time": "timestamptz", "time": "text",
            "board": "text", "location": "text",
        },
        "purpose": "Bed tossing/restlessness events.",
    },
    "movement_mapping": {
        "columns": {
            "id": "bigint", "ingestion_time": "timestamptz", "time": "text",
            "board": "text", "location": "text",
            "movement_location": "text", "object_name": "text",
            "payload": "jsonb",
        },
        "purpose": "Per-event movement annotations with location and object_name.",
    },
    "movement_time": {
        "columns": {
            "id": "bigint", "ingestion_time": "timestamptz",
            "payload": "jsonb",
        },
        "purpose": "Raw movement timing payload (JSONB).",
    },
    "state_machine_binary": {
        "columns": {
            "id": "bigint", "ingestion_time": "timestamptz", "time": "text",
            "board": "text", "location": "text", "payload": "jsonb",
            "multiple_people": "text",
        },
        "purpose": "State-machine emission for occupancy/presence transitions.",
    },
    "obj": {
        "columns": {
            "id": "bigint", "ingestion_time": "timestamptz", "time": "text",
            "fn": "bigint", "board": "text", "location": "text",
            "obj": "jsonb",
        },
        "purpose": "Raw object-detection JSON ingest stage.",
    },

    # ------------------------------------------------ Wellness aggregates
    "wellness_metrics": {
        "columns": {
            "id": "bigint", "board": "text", "type": "summarytypeenum",
            "time_interval": "timeintervalenum", "attribute": "jsonb",
            "location": "text", "score": "float", "date": "date",
            "start_time": "timestamptz", "end_time": "timestamptz",
        },
        "purpose": "Hourly/daily aggregated scores per board, per type (sleep/activity/vitals/environment/fall).",
    },
    "insights": {
        "columns": {
            "id": "bigint", "resident_id": "integer", "board": "text",
            "type": "insighttypeenum", "priority": "insightpriorityenum",
            "meta_data": "jsonb", "location": "text", "date": "date",
            "created_at": "timestamptz", "updated_at": "timestamptz",
            "insight": "text",
        },
        "purpose": "Generated insights per resident-day with priority. resident_id FK to resident_profile.id (direct resident link, not via board).",
    },

    # ----------------------------------------------------------- Audit
    "activity_log": {
        "columns": {
            "id": "integer", "object_id": "text", "location": "text",
            "resident_id": "integer", "status": "statusenum",
            "start_time": "timestamptz", "end_time": "timestamptz",
            "created_at": "timestamptz", "updated_at": "timestamptz",
        },
        "purpose": "Resident activity log with status (active/inactive/sleeping/walking). resident_id FK to resident_profile.id (direct).",
    },

    # ---------------------------------------------------- Integrations
    "webhook_outbox": {
        "columns": {
            "id": "integer", "event_id": "text", "alert_type": "text",
            "device_id": "text", "payload": "jsonb", "status": "text",
            "attempts": "integer", "next_attempt_at": "timestamptz",
            "last_error": "text", "created_at": "timestamptz",
            "updated_at": "timestamptz", "delivered_at": "timestamptz",
            "tenant_id": "uuid",
        },
        "purpose": "Outbound webhook delivery queue per tenant. UNIQUE on (tenant_id, event_id).",
    },
    "analytics": {
        "columns": {
            "id": "integer", "display_name": "text", "dashboard_url": "text",
            "is_active": "boolean", "deleted_by": "integer",
            "is_deleted": "boolean", "created_at": "timestamptz",
            "updated_at": "timestamptz",
        },
        "purpose": "Registered analytics dashboards.",
    },
    "users_analytics_mapping": {
        "columns": {
            "id": "integer", "user_id": "integer", "analytics_id": "integer",
            "deleted_by": "integer", "is_deleted": "boolean",
            "created_at": "timestamptz", "updated_at": "timestamptz",
        },
        "purpose": "Which user can see which analytics dashboard.",
    },
    "feedbacks": {
        "columns": {
            "id": "bigint", "submitted_by": "integer", "body": "text",
            "created_at": "timestamptz", "updated_at": "timestamptz",
        },
        "purpose": "User-submitted feedback. submitted_by FK to users.id.",
    },

    # ---------------------------------------------------------- Plumbing
    "alembic_version": {
        "columns": {"version_num": "text"},
        "purpose": "Alembic migration tracking — do not query from chatbot.",
    },
}


# ---------------------------------------------------------------------------
# Foreign keys (only declared FKs from schema.sql — sensor.board is NOT one)
# ---------------------------------------------------------------------------

FOREIGN_KEYS: tuple[tuple[str, str, str, str], ...] = (
    # NOTE: resident_id FKs were migrated from users(id) -> resident_profile(id)
    # by data/kubo_dummy.sql's schema-migration prelude. resident_profile lost
    # its own resident_id column in the same migration.
    ("activity_log", "resident_id", "resident_profile", "id"),
    ("analytics", "deleted_by", "users", "id"),
    ("community", "deleted_by", "users", "id"),
    ("community", "organisation_id", "organisation", "id"),
    ("community_user_mapping", "community_id", "community", "id"),
    ("community_user_mapping", "deleted_by", "users", "id"),
    ("community_user_mapping", "user_id", "users", "id"),
    ("feedbacks", "submitted_by", "users", "id"),
    ("incidents", "room_id", "rooms", "id"),
    ("insights", "resident_id", "resident_profile", "id"),
    ("notifications", "deleted_by", "users", "id"),
    ("notifications", "resident_id", "resident_profile", "id"),
    ("notifications", "room_id", "rooms", "id"),
    ("objects", "deleted_by", "users", "id"),
    ("objects", "room_id", "rooms", "id"),
    ("organisation", "deleted_by", "users", "id"),
    ("push_endpoints", "user_id", "users", "id"),
    ("resident_profile", "deleted_by", "users", "id"),
    ("room_resident_mapping", "deleted_by", "users", "id"),
    ("room_resident_mapping", "resident_id", "resident_profile", "id"),
    ("room_resident_mapping", "room_id", "rooms", "id"),
    ("rooms", "community_id", "community", "id"),
    ("rooms", "deleted_by", "users", "id"),
    ("security_incidents", "closed_by", "users", "id"),
    ("security_incidents", "deleted_by", "users", "id"),
    ("tenant_credentials", "tenant_id", "tenants", "id"),
    ("user_hierarchy_mapping", "child_id", "users", "id"),
    ("user_hierarchy_mapping", "parent_id", "users", "id"),
    ("users", "deleted_by", "users", "id"),
    ("users", "role_id", "roles", "id"),
    ("users_analytics_mapping", "analytics_id", "analytics", "id"),
    ("users_analytics_mapping", "deleted_by", "users", "id"),
    ("users_analytics_mapping", "user_id", "users", "id"),
    ("webhook_outbox", "tenant_id", "tenants", "id"),
)


# ---------------------------------------------------------------------------
# Primary keys (composite where applicable)
# ---------------------------------------------------------------------------

PRIMARY_KEYS: Mapping[str, tuple[str, ...]] = {
    "activity_log": ("id",),
    "alembic_version": ("version_num",),
    "ambience": ("id", "ingestion_time"),
    "analytics": ("id",),
    "community": ("id",),
    "community_user_mapping": ("id",),
    "fds": ("id", "ingestion_time"),
    "feedbacks": ("id",),
    "incidents": ("id",),
    "insights": ("id",),
    "motion": ("id", "ingestion_time"),
    "movement_mapping": ("id", "ingestion_time"),
    "movement_time": ("id", "ingestion_time"),
    "notifications": ("id",),
    "obj": ("id", "ingestion_time"),
    "objects": ("id",),
    "on_bed": ("id", "ingestion_time"),
    "organisation": ("id",),
    "push_endpoints": ("id",),
    "resident_profile": ("id",),
    "roles": ("id",),
    "room_resident_mapping": ("id",),
    "rooms": ("id",),
    "security_incidents": ("id",),
    "service_alert": ("id",),
    "sleep_sessions": ("id",),
    "sos": ("id", "ingestion_time"),
    "state_machine_binary": ("id", "ingestion_time"),
    "tenant_credentials": ("id",),
    "tenants": ("id",),
    "toss": ("id", "ingestion_time"),
    "user_hierarchy_mapping": ("id",),
    "users": ("id",),
    "users_analytics_mapping": ("id",),
    "vitals": ("id", "ingestion_time"),
    "webhook_outbox": ("id",),
    "wellness_metrics": ("id",),
}


# ---------------------------------------------------------------------------
# Tables that have is_deleted column — every SELECT must filter is_deleted=false
# (validated empirically against schema.sql; do not edit by guesswork)
# ---------------------------------------------------------------------------

SOFT_DELETE_TABLES: frozenset[str] = frozenset({
    "analytics", "community", "community_user_mapping", "incidents",
    "notifications", "objects", "organisation", "resident_profile", "roles",
    "room_resident_mapping", "rooms", "security_incidents", "tenants",
    "user_hierarchy_mapping", "users", "users_analytics_mapping",
})


# ---------------------------------------------------------------------------
# PHI / PII columns. Caregivers see these; output guardrail prevents leaking
# them across residents (caller asking about resident A must not get
# resident B's medical_history in the response).
# ---------------------------------------------------------------------------

PHI_COLUMNS: Mapping[str, frozenset[str]] = {
    "users": frozenset({
        "mobile", "email", "address", "pin", "country_code", "name",
    }),
    "resident_profile": frozenset({
        "medical_history", "emergency_contacts", "dob", "gender",
        "flat_number", "call_from_mobile", "image", "buzzer_config",
        "trigger_settings",
    }),
    "vitals": frozenset({"hr", "rr"}),
    "sleep_sessions": frozenset({
        "sleep_stage", "sleep_type", "start_duration", "end_duration",
    }),
    "on_bed": frozenset({"on_bed"}),
    "fds": frozenset({"report", "activity", "position", "result"}),
    "incidents": frozenset({
        "event_category", "event_outcome", "json_payload", "resolve_type",
    }),
    "notifications": frozenset({
        "event_category", "message", "resolve_type",
    }),
    "security_incidents": frozenset({
        "description", "remark", "severity",
    }),
    "insights": frozenset({"meta_data", "insight"}),
    "wellness_metrics": frozenset({"attribute", "score"}),
}


# ---------------------------------------------------------------------------
# Sensor tables (no FK to objects; identified by board text). Each entry maps
# the table to its board-column name — note fds uses 'board_sn' instead of
# 'board' (real schema inconsistency).
# ---------------------------------------------------------------------------

BOARD_COLUMN_BY_TABLE: Mapping[str, str] = {
    "vitals": "board",
    "motion": "board",
    "ambience": "board",
    "on_bed": "board",
    "fds": "board_sn",
    "sos": "board",
    "sleep_sessions": "board",
    "toss": "board",
    "movement_mapping": "board",
    "state_machine_binary": "board",
    "obj": "board",
    "wellness_metrics": "board",
    "insights": "board",
}

SENSOR_TABLES: frozenset[str] = frozenset(BOARD_COLUMN_BY_TABLE.keys())


# Tables that DO have a direct resident_id FK to users.id (no board hop needed).
RESIDENT_LINKED_DIRECT: frozenset[str] = frozenset({
    "resident_profile", "room_resident_mapping", "insights", "activity_log",
    "notifications",
})


# ---------------------------------------------------------------------------
# Community-scope path. Maps each domain table to the JOIN chain needed to
# reach community.id so SQL builders can enforce the caller's community scope.
# Empty tuple = no scope needed (administrative/system tables).
# 'self' = the table itself has community_id.
# ---------------------------------------------------------------------------

COMMUNITY_SCOPE_PATH: Mapping[str, tuple[str, ...]] = {
    # Direct
    "community": ("self",),
    "rooms": ("self",),  # rooms.community_id
    # One hop via rooms
    "objects": ("rooms",),
    "incidents": ("rooms",),
    # Via room_resident_mapping → rooms
    "notifications": ("room_resident_mapping", "rooms"),
    "resident_profile": ("room_resident_mapping", "rooms"),
    "activity_log": ("room_resident_mapping", "rooms"),
    "insights": ("room_resident_mapping", "rooms"),
    # Sensor tables → objects → rooms
    "vitals": ("objects", "rooms"),
    "motion": ("objects", "rooms"),
    "ambience": ("objects", "rooms"),
    "on_bed": ("objects", "rooms"),
    "fds": ("objects", "rooms"),
    "sos": ("objects", "rooms"),
    "sleep_sessions": ("objects", "rooms"),
    "toss": ("objects", "rooms"),
    "movement_mapping": ("objects", "rooms"),
    "state_machine_binary": ("objects", "rooms"),
    "obj": ("objects", "rooms"),
    "wellness_metrics": ("objects", "rooms"),
    # User-scope via community_user_mapping
    "users": ("community_user_mapping",),
    # No scope (tenant-level / system)
    "tenants": (),
    "tenant_credentials": (),
    "webhook_outbox": (),
    "organisation": (),
    "community_user_mapping": (),
    "roles": (),
    "user_hierarchy_mapping": (),
    "push_endpoints": (),
    "analytics": (),
    "users_analytics_mapping": (),
    "feedbacks": (),
    "security_incidents": (),
    "service_alert": (),
    "alembic_version": (),
    "room_resident_mapping": ("rooms",),
}


# ---------------------------------------------------------------------------
# Canonical JOIN snippets. The board→resident chain is the load-bearing one;
# encode it once so both the rule layer and the LLM fallback select through
# vw_resident_sensor (created by the Phase A.3 migration).
# ---------------------------------------------------------------------------

CANONICAL_JOINS: Mapping[str, str] = {
    # Resolve a sensor row to the resident who owns it.
    # Note: fds uses board_sn instead of board (handled in vw_resident_sensor).
    "resident_sensor_chain": (
        "FROM resident_profile rp "
        "JOIN room_resident_mapping rrm ON rrm.resident_id = rp.resident_id "
        "  AND COALESCE(rrm.is_deleted, false) = false "
        "JOIN rooms r ON r.id = rrm.room_id "
        "  AND COALESCE(r.is_deleted, false) = false "
        "JOIN objects o ON o.room_id = r.id "
        "  AND COALESCE(o.is_deleted, false) = false"
    ),
    "user_to_community": (
        "FROM community_user_mapping cum "
        "JOIN community c ON c.id = cum.community_id "
        "  AND COALESCE(c.is_deleted, false) = false "
        "WHERE cum.user_id = %(user_id)s "
        "  AND COALESCE(cum.is_deleted, false) = false"
    ),
}


# ---------------------------------------------------------------------------
# Tables that hold a wall-clock event-time column. Lets the rule layer apply
# time-window filters generically.
# ---------------------------------------------------------------------------

TIME_COLUMN_BY_TABLE: Mapping[str, str] = {
    # Sensor streams
    "vitals": "ingestion_time",
    "motion": "ingestion_time",
    "ambience": "ingestion_time",
    "on_bed": "ingestion_time",
    "fds": "ingestion_time",
    "sos": "ingestion_time",
    "toss": "ingestion_time",
    "movement_mapping": "ingestion_time",
    "movement_time": "ingestion_time",
    "obj": "ingestion_time",
    "state_machine_binary": "ingestion_time",
    "service_alert": "ingestion_time",
    # Sessions / events
    "sleep_sessions": "start_duration",
    "incidents": "event_time",
    "notifications": "event_time",
    "activity_log": "start_time",
    "wellness_metrics": "start_time",
    "insights": "date",
    "security_incidents": "date",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_columns(table: str) -> tuple[str, ...]:
    """Return the column names for a table, or empty tuple if unknown."""
    meta = SCHEMA.get(table)
    if not meta:
        return ()
    return tuple(meta["columns"].keys())  # type: ignore[arg-type]


def is_phi(table: str, column: str) -> bool:
    return column in PHI_COLUMNS.get(table, frozenset())


def is_soft_deleted(table: str) -> bool:
    return table in SOFT_DELETE_TABLES


def board_column_for(table: str) -> str | None:
    """Sensor tables use 'board' except fds which uses 'board_sn'."""
    return BOARD_COLUMN_BY_TABLE.get(table)


def time_column_for(table: str) -> str | None:
    return TIME_COLUMN_BY_TABLE.get(table)


def requires_community_scope(table: str) -> bool:
    """True if a SELECT on this table must be scoped to the caller's community."""
    path = COMMUNITY_SCOPE_PATH.get(table)
    return bool(path)


def enum_values(enum_name: str) -> tuple[str, ...]:
    return ENUMS.get(enum_name, ())


def schema_to_text(
    schema: Mapping[str, Mapping[str, object]] | None = None,
    *,
    only: Iterable[str] | None = None,
) -> str:
    """Render the schema as a compact prompt-ready string.

    `only`: if provided, restrict to these table names (schema pruning for the
    LLM planner — sending all 40 tables every call is noisy and expensive).
    """
    src = schema if schema is not None else SCHEMA
    selected = set(only) if only is not None else set(src.keys())

    lines: list[str] = []
    for table, meta in src.items():
        if table not in selected:
            continue
        cols = ", ".join(
            f"{c} {t.upper()}" for c, t in meta["columns"].items()  # type: ignore[union-attr]
        )
        purpose = meta.get("purpose", "")  # type: ignore[union-attr]
        lines.append(f"Table: {table}({cols})  -- {purpose}")

    # Critical relationships: declared FKs + the board→object resolution rule.
    lines.append("")
    lines.append("Key relationships:")
    lines.append("- resident_profile.resident_id = users.id (residents are users)")
    lines.append("- room_resident_mapping links residents to rooms (room_id UNIQUE)")
    lines.append("- rooms.community_id = community.id")
    lines.append("- objects.room_id = rooms.id")
    lines.append("- Sensor tables (vitals, motion, ambience, on_bed, sos, sleep_sessions, toss, wellness_metrics, insights, ...) join to objects via objects.object_id = sensor.board")
    lines.append("- EXCEPTION: fds uses board_sn instead of board (objects.object_id = fds.board_sn)")
    lines.append("- For resident-scoped sensor queries, prefer SELECT FROM vw_resident_sensor JOIN <sensor_table> USING(board, object_id) -- handles the join chain and tenant scope.")

    lines.append("")
    lines.append("Always-applied filters:")
    lines.append("- Tables with is_deleted column: filter COALESCE(is_deleted, false) = false")
    lines.append("- All queries must be scoped to the caller's community_id")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Self-check (run as `python -m app.schema.kubocare_schema`)
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    # Sanity: every PRIMARY_KEYS entry points at columns that actually exist.
    for tbl, pk_cols in PRIMARY_KEYS.items():
        cols = get_columns(tbl)
        missing = [c for c in pk_cols if c not in cols]
        assert not missing, f"PK mismatch on {tbl}: {missing}"

    # Sanity: every FOREIGN_KEYS source column exists on its table.
    for src_tbl, src_col, ref_tbl, ref_col in FOREIGN_KEYS:
        assert src_col in get_columns(src_tbl), f"{src_tbl}.{src_col} not in SCHEMA"
        assert ref_col in get_columns(ref_tbl), f"{ref_tbl}.{ref_col} not in SCHEMA"

    # Sanity: every SOFT_DELETE_TABLES entry actually has is_deleted.
    for tbl in SOFT_DELETE_TABLES:
        assert "is_deleted" in get_columns(tbl), f"{tbl} not in SCHEMA or has no is_deleted"

    # Sanity: every BOARD_COLUMN_BY_TABLE entry resolves.
    for tbl, board_col in BOARD_COLUMN_BY_TABLE.items():
        assert board_col in get_columns(tbl), f"{tbl} has no column {board_col}"

    # Sanity: every PHI column exists on its table.
    for tbl, phi_cols in PHI_COLUMNS.items():
        cols = set(get_columns(tbl))
        missing = phi_cols - cols
        assert not missing, f"PHI columns missing on {tbl}: {missing}"

    print(f"OK: {len(SCHEMA)} tables, {len(FOREIGN_KEYS)} FKs, "
          f"{len(SOFT_DELETE_TABLES)} soft-delete tables, "
          f"{len(SENSOR_TABLES)} sensor tables, "
          f"{sum(len(v) for v in PHI_COLUMNS.values())} PHI columns")
    print()
    print("--- schema_to_text(only=['vitals','resident_profile','rooms']) preview ---")
    print(schema_to_text(only=["vitals", "resident_profile", "rooms"]))
