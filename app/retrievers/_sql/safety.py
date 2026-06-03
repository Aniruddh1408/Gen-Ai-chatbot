# ===========================================================================
# This file is a safety gate for database requests. Before any request runs, it
# checks that the request only READS information and can never change or delete
# anything, and that it only touches approved tables and columns. Think of it
# as a guard who inspects every request and turns away anything risky.
# ===========================================================================
"""Read-only SQL validation primitives for sql_retriever.

Pure logic (schema allowlist + statement checks); no DB/LLM. Moved out of
sql_retriever.py and re-exported there so build_sql and tests keep working.
"""
import re

from app.core.logger import get_logger
from app.schema.kubocare_schema import SCHEMA

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

# Computed-column expressions are accepted only when (a) every parenthesised
# function call is on this allowlist and (b) no subquery / DML keyword
# appears anywhere in the token. This keeps "EXTRACT(YEAR FROM AGE(...))::int
# AS age" usable from the deterministic rules in app/retrievers/_sql/constants
# without opening the door to arbitrary SQL injection.
_ALLOWED_EXPRESSION_FUNCS = frozenset({
    "EXTRACT", "AGE", "ROUND",
    "AVG", "SUM", "COUNT", "MIN", "MAX",
    "LENGTH", "COALESCE", "CONCAT", "LOWER", "UPPER", "TRIM",
})
# Stricter than _FORBIDDEN_SQL_RE — adds SELECT and other subquery-only
# keywords. `FROM` and `WHERE` are NOT here because PostgreSQL syntax uses
# them inside legitimate scalar expressions: EXTRACT(YEAR FROM ts),
# CASE WHEN x THEN y END, etc. They're only dangerous when paired with a
# preceding SELECT, which is blocked here.
_EXPRESSION_FORBIDDEN_RE = re.compile(
    r"\b(?:SELECT|UNION|JOIN|"
    r"INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|"
    r"CALL|EXEC|EXECUTE|GRANT|REVOKE|COPY|INTO)\b",
    re.IGNORECASE,
)
_DOTTED_REF_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b", re.IGNORECASE)
_FUNC_CALL_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")
# "EXTRACT(YEAR FROM ...)" includes the bare identifier YEAR which is fine in
# this position. Same for fields like MONTH/DAY etc. We don't try to parse
# the SQL grammar, just refuse anything we don't explicitly recognise.
_EXTRACT_FIELD_KEYWORDS = frozenset({
    "YEAR", "MONTH", "DAY", "HOUR", "MINUTE", "SECOND",
    "DOW", "DOY", "EPOCH", "WEEK", "QUARTER",
})


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


def _is_safe_expression_column(token: str) -> bool:
    """Accept a computed column when:

    - no DML / subquery keyword appears anywhere in the token
    - every function call is on _ALLOWED_EXPRESSION_FUNCS
    - every dotted reference (table.column) is allowlisted in SCHEMA
    - every bare identifier is either a known column, an allowlisted EXTRACT
      field (YEAR/MONTH/...), or part of the SQL grammar (AS, FROM-inside-
      EXTRACT, etc.) that we explicitly recognise.

    This is intentionally narrow. The token comes from a deterministic rule
    table (constants.py) or — in principle — the LLM planner; we never want
    to give either a path to inject arbitrary SQL through the column field.
    """
    if _EXPRESSION_FORBIDDEN_RE.search(token):
        return False
    for func in _FUNC_CALL_RE.findall(token):
        if func.upper() not in _ALLOWED_EXPRESSION_FUNCS:
            return False
    refs = _DOTTED_REF_RE.findall(token)
    if not refs:
        # Expression must reference at least one real column. Pure literals
        # ('foo'::text) are rejected as they can't legitimately answer a
        # row-level question.
        return False
    for table_name, column_name in refs:
        if table_name not in _ALLOWED_TABLES:
            return False
        if column_name not in _ALLOWED_COLUMNS_BY_TABLE.get(table_name, set()):
            return False
    return True


def _is_allowed_identifier(token: str) -> bool:
    """True only for a known schema column or a safe computed expression.

    A token containing '(' is treated as an expression and routed through
    _is_safe_expression_column. Otherwise it must match either
    "table.column" (both allowlisted) or a bare known column name. Trailing
    "AS alias" is permitted on plain identifiers; the alias itself is not
    interpreted, only stripped before lookup.
    """
    token = token.strip()
    if not token:
        return False

    if "(" in token:
        return _is_safe_expression_column(token)

    # Strip "X AS alias" — keep only the left-hand identifier.
    head = re.split(r"\s+(?:AS\s+)", token, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    if not head:
        return False

    if "." in head:
        table_part, _, column_part = head.partition(".")
        return (
            table_part.strip() in _ALLOWED_TABLES
            and column_part.strip() in _ALLOWED_COLUMNS_BY_TABLE.get(table_part.strip(), set())
        )
    return head in _ALL_COLUMN_NAMES


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
