"""Read-only SQL validation primitives for sql_retriever.

Pure logic (schema allowlist + statement checks); no DB/LLM. Moved out of
sql_retriever.py and re-exported there so build_sql and tests keep working.
"""
import re

from app.core.logger import get_logger
from app.schema.schema import SCHEMA

logger = get_logger("sql_retriever.safety")


class UnsafeSQLError(ValueError):
    """Raised when a generated SQL plan or statement is not a safe, read-only query."""


_ALLOWED_TABLES = set(SCHEMA.keys())
_ALLOWED_COLUMNS_BY_TABLE = {
    table_name: set(meta["columns"]) for table_name, meta in SCHEMA.items()
}
_ALL_COLUMN_NAMES = {
    column_name
    for columns in _ALLOWED_COLUMNS_BY_TABLE.values()
    for column_name in columns
}
_ALLOWED_FILTER_OPERATORS = {"=", "!=", "<>", "<", "<=", ">", ">=", "LIKE", "ILIKE"}
_FORBIDDEN_SQL_RE = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|CALL|"
    r"EXEC|EXECUTE|GRANT|REVOKE|ATTACH|DETACH|PRAGMA|COPY|VACUUM|INTO|"
    r"COMMIT|ROLLBACK|SAVEPOINT)\b",
    re.IGNORECASE,
)
_SELECT_ONLY_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)


def _ensure_filters_list(raw_filters) -> list:
    """Normalize a plan's filters into a list (a lone filter dict becomes [dict])."""
    if isinstance(raw_filters, dict):
        return [raw_filters]
    if isinstance(raw_filters, list):
        return raw_filters
    return []


def _reject_unsafe_sql(reason: str) -> None:
    """Log the technical reason for developers and raise a safe-to-bubble error."""
    logger.warning(f"Rejected unsafe SQL: {reason}")
    raise UnsafeSQLError(reason)


def _is_allowed_identifier(token: str) -> bool:
    """True only for a known schema column, optionally table-qualified."""
    token = token.strip()
    if not token:
        return False
    if "." in token:
        table_part, _, column_part = token.partition(".")
        table_part = table_part.strip()
        return (
            table_part in _ALLOWED_TABLES
            and column_part.strip() in _ALLOWED_COLUMNS_BY_TABLE.get(table_part, set())
        )
    return token in _ALL_COLUMN_NAMES


def _validate_plan_identifiers(plan: dict) -> None:
    """Reject any table/column/order_by/operator not in the schema allowlist.

    Values are always bound as query parameters, so only identifiers are checked
    here. This is the structural half of the read-only guarantee; the built SQL
    string is checked again by _validate_read_only_sql.
    """
    table_name = str(plan.get("table", "residents")).strip()
    if table_name not in _ALLOWED_TABLES:
        _reject_unsafe_sql(f"disallowed table in plan: {table_name!r}")

    for part in str(plan.get("column", "residents.name")).split(","):
        if not _is_allowed_identifier(part):
            _reject_unsafe_sql(f"disallowed column in plan: {part.strip()!r}")

    order_by = plan.get("order_by")
    if order_by and not _is_allowed_identifier(str(order_by)):
        _reject_unsafe_sql(f"disallowed order_by in plan: {order_by!r}")

    for item in _ensure_filters_list(plan.get("filters", [])):
        if not isinstance(item, dict):
            continue
        column = item.get("column")
        if column is not None and not _is_allowed_identifier(str(column)):
            _reject_unsafe_sql(f"disallowed filter column in plan: {column!r}")
        operator = str(item.get("operator", "=")).strip().upper()
        if operator not in _ALLOWED_FILTER_OPERATORS:
            _reject_unsafe_sql(f"disallowed filter operator in plan: {operator!r}")


def _validate_read_only_sql(sql: str) -> None:
    """Defense-in-depth: ensure the built statement is a single read-only SELECT."""
    statement = sql.strip().rstrip(";").strip()
    if ";" in statement:
        _reject_unsafe_sql("multiple SQL statements are not allowed")
    if "--" in statement or "/*" in statement:
        _reject_unsafe_sql("SQL comments are not allowed")
    if not _SELECT_ONLY_RE.match(statement):
        _reject_unsafe_sql("only SELECT statements are allowed")
    if _FORBIDDEN_SQL_RE.search(statement):
        _reject_unsafe_sql("disallowed SQL keyword detected")
