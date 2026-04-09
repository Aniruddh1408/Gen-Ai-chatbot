import logging
import json
from datetime import datetime

class StructuredJSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        
        # Inject custom telemetry if present
        if hasattr(record, "trace_id"):
            log_obj["trace_id"] = record.trace_id
        if hasattr(record, "latency_ms"):
            log_obj["latency_ms"] = round(record.latency_ms, 2)
        if hasattr(record, "query"):
            log_obj["query"] = record.query
            
        return json.dumps(log_obj)

def get_logger(module_name):
    """
    Returns a configured JSON logger for observability and tracing.
    In production, you'd pipe these logs to Datadog, Prometheus, or AWS CloudWatch.
    """
    logger = logging.getLogger(module_name)
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(StructuredJSONFormatter())
        logger.addHandler(console_handler)
        
    return logger
