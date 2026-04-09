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
    }
}


def schema_to_text(schema):
    """Convert schema dict to a typed DDL-like string for LLM consumption."""
    text = ""
    for table, details in schema.items():
        cols = ", ".join([f"{col} {dtype.upper()}" for col, dtype in details["columns"].items()])
        text += f"Table: {table}({cols})\n"
    return text