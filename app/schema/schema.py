SCHEMA = {
    "device_status": {
        "columns": {
            "board_id": "text",
            "location": "text",
            "signal": "numeric",
            "uptime": "numeric",
            "cpu": "numeric",
            "time": "timestamp"
        }
    },
    "residents": {
        "columns": {
            "id": "integer",
            "name": "text",
            "flat_no": "text",
            "age": "integer",
            "health_medical_history": "text",
            "medical_intake_prescribed": "text"
        }
    },
    "health_reports": {
        "columns": {
            "resident_id": "integer",
            "bp_systolic": "integer",
            "bp_diastolic": "integer",
            "sugar_level": "numeric",
            "recorded_at": "timestamp"
        }
    },
    "activity_metrics": {
        "columns": {
            "resident_id": "integer",
            "steps_count": "integer",
            "recorded_at": "timestamp"
        }
    },
    "sleep_analytics": {
        "columns": {
            "resident_id": "integer",
            "sleep_duration_minutes": "integer",
            "sleep_quality_score": "integer",
            "recorded_at": "timestamp"
        }
    }
}


def schema_to_text(schema):
    """Convert schema dict to a typed DDL-like string for LLM consumption."""
    text = ""
    for table, details in schema.items():
        cols = ", ".join([f"{col} {dtype.upper()}" for col, dtype in details["columns"].items()])
        text += f"Table: {table}({cols})\n"

    # Important for JOINs
    text += "\nRelationships:\n"
    text += "- residents.id = health_reports.resident_id\n"
    text += "- residents.id = activity_metrics.resident_id\n"
    text += "- residents.id = sleep_analytics.resident_id\n"
    return text