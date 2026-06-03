# ===========================================================================
# This is a second, stricter safety inspector for database requests — used
# especially for requests the AI writes itself. It carefully reads the
# structure of a request to guarantee it only reads data, uses only approved
# tables, never peeks at system internals, and stays limited to the right
# community. If anything looks off, the request is blocked.
# ===========================================================================
"""Strict SQL validator for the Kubocare schema.

This is the new validator that the rewritten retriever (Phase B.6+) and
LLM SQL planner (Phase D.9) will pass every emitted query through, no
matter who wrote it (rule layer, LLM, future hand-written code).

Independent of the legacy `safety.py` so this can be tested in isolation
and the cutover is a one-line import change later.

Checks enforced (each maps to a specific failure mode we have to prevent):

  1. Single statement only — block `SELECT ...; DROP TABLE ...`
  2. Top-level node must be SELECT — no INSERT/UPDATE/DELETE etc. at root
  3. No mutation nodes ANYWHERE in the AST — block `WITH x AS (...) DELETE FROM ...`
  4. No SQL comments — block `SELECT 1 -- ; DROP TABLE x` style smuggling
  5. Every referenced table must be in the allowlist (SCHEMA + vw_resident_sensor)
  6. No reads from `information_schema`, `pg_catalog`, or other system schemas
  7. If any community-scoped table is touched, the SQL must reference community_id
     in a WHERE/ON predicate (caller can override for genuinely cross-community
     admin queries)
  8. If the caller asserts resident scope, the SQL must reference
     resident_id in a predicate

The validator does NOT execute the SQL or contact a DB. Pure parsing + AST walk.
"""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.core.logger import get_logger
from app.schema.kubocare_schema import (
    SCHEMA,
    COMMUNITY_SCOPE_PATH,
)

logger = get_logger("sql_validator")


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

class UnsafeSQLError(ValueError):
    """Raised when a SQL statement fails any safety check.

    Message is intentionally short and safe to surface in logs. Callers turn
    this into a generic user-facing apology; the technical detail stays in
    server logs.
    """


@dataclass(frozen=True)
class ValidationResult:
    """The post-validation summary the caller may consult."""

    sql: str
    tables: tuple[str, ...]               # tables touched (FROM/JOIN), deduped
    has_community_predicate: bool
    has_resident_predicate: bool


# ---------------------------------------------------------------------------
# Allowlists (derived from the schema brain)
# ---------------------------------------------------------------------------

# Virtual table created by data/migrations/0001_resident_sensor_view.sql.
_VIRTUAL_TABLES: frozenset[str] = frozenset({"vw_resident_sensor"})

_ALLOWED_TABLES: frozenset[str] = frozenset(SCHEMA.keys()) | _VIRTUAL_TABLES

# Postgres system schemas chatbot SQL must never read from.
_BLOCKED_SCHEMAS: frozenset[str] = frozenset({
    "information_schema", "pg_catalog", "pg_temp", "pg_toast",
})

# Any AST node type whose presence anywhere in the tree means "this is not a
# pure SELECT". Catches DML smuggled into CTEs or sub-expressions.
_MUTATION_NODES: tuple[type, ...] = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge,
    exp.Drop, exp.Create, exp.Alter, exp.TruncateTable,
    exp.Grant, exp.Revoke, exp.Copy, exp.Refresh,
    exp.Command,  # exp.Command catches statements sqlglot doesn't model (TRUNCATE, VACUUM, etc.)
)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate_sql(
    sql: str,
    *,
    enforce_community_scope: bool = True,
    enforce_resident_scope: bool = False,
) -> ValidationResult:
    """Validate `sql` against every safety rule. Raise UnsafeSQLError on any failure.

    Parameters
    ----------
    enforce_community_scope:
        If True (default), require a community_id predicate when any table
        touched needs community scoping (per COMMUNITY_SCOPE_PATH). Set False
        only for legitimately cross-community admin queries.
    enforce_resident_scope:
        If True, require a resident_id predicate. Used where the runtime must
        guarantee single-resident scope.
    """
    if not isinstance(sql, str) or not sql.strip():
        _reject("empty SQL")

    # 1. No SQL comments. Block both line and block comments before we parse,
    #    so a smuggled `-- ; DROP ...` can't sneak past via comment stripping.
    if "--" in sql or "/*" in sql or "*/" in sql:
        _reject("SQL comments are not allowed")

    # 2. Single statement only. sqlglot.parse() returns one item per statement
    #    (separated by semicolons); we require exactly one.
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except ParseError as exc:
        _reject(f"could not parse SQL: {exc}")
    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        _reject(f"exactly one SQL statement required (got {len(statements)})")
    root = statements[0]

    # 3. Top-level must be SELECT. WITH ... SELECT also parses as Select at the
    #    root in sqlglot.
    if not isinstance(root, exp.Select):
        _reject(f"only SELECT statements are allowed (got {type(root).__name__})")

    # 4. No mutation nodes anywhere in the AST. Catches DML inside CTEs,
    #    sub-queries, or anywhere the parser modelled an INSERT/UPDATE/etc.
    for node in root.walk():
        if isinstance(node, _MUTATION_NODES):
            _reject(f"mutation operation detected: {type(node).__name__}")

    # 5. Every table reference must be in the allowlist and not in a system schema.
    touched: set[str] = set()
    for table in root.find_all(exp.Table):
        # qualifier checks
        db = (table.db or "").lower()
        if db in _BLOCKED_SCHEMAS:
            _reject(f"system schema access denied: {db}.{table.name}")
        name = table.name
        # Allow CTE names (they are exp.Table refs but resolved against the
        # WITH clause, not the schema). sqlglot's `find_all(exp.CTE)` gives
        # those names.
        cte_names = {cte.alias_or_name for cte in root.find_all(exp.CTE)}
        if name in cte_names:
            continue
        if name not in _ALLOWED_TABLES:
            _reject(f"unknown or disallowed table: {name!r}")
        touched.add(name)

    # 6. Scope predicate checks. Walk every column reference in WHERE/JOIN-ON.
    referenced_in_predicates = _columns_in_predicates(root)
    has_community = "community_id" in referenced_in_predicates
    has_resident = "resident_id" in referenced_in_predicates

    if enforce_community_scope:
        scope_needed = any(
            COMMUNITY_SCOPE_PATH.get(t) for t in touched
            if t not in _VIRTUAL_TABLES  # view already enforces scope via its filter
        ) or any(t in _VIRTUAL_TABLES for t in touched)
        # The view contains community_id but that's a column, not a filter.
        # We still require the caller to add a WHERE predicate on it.
        if scope_needed and not has_community:
            _reject(
                "query is missing a community_id predicate; "
                "tenant scoping is mandatory"
            )

    if enforce_resident_scope and not has_resident:
        _reject(
            "query is missing a resident_id predicate; "
            "resident scoping is mandatory for this caller"
        )

    return ValidationResult(
        sql=sql,
        tables=tuple(sorted(touched)),
        has_community_predicate=has_community,
        has_resident_predicate=has_resident,
    )


def extract_tables(sql: str) -> tuple[str, ...]:
    """Lightweight helper for schema-pruning the LLM planner prompt.

    Returns the set of allowlisted tables a (possibly invalid) SQL string
    references. Does not raise; on parse error returns ().
    """
    try:
        root = sqlglot.parse_one(sql, read="postgres")
    except ParseError:
        return ()
    cte_names = {cte.alias_or_name for cte in root.find_all(exp.CTE)}
    seen: set[str] = set()
    for t in root.find_all(exp.Table):
        if t.name in cte_names:
            continue
        if t.name in _ALLOWED_TABLES:
            seen.add(t.name)
    return tuple(sorted(seen))


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _reject(reason: str) -> None:
    """Log the technical reason and raise the safe-to-surface error."""
    logger.warning(f"Rejected unsafe SQL: {reason}")
    raise UnsafeSQLError(reason)


def _columns_in_predicates(root: exp.Expression) -> set[str]:
    """Names of columns referenced inside WHERE or JOIN-ON predicates.

    Looking only at predicates (not the SELECT projection) prevents false
    positives like `SELECT community_id FROM ...` satisfying the scope check.
    """
    names: set[str] = set()
    for where in root.find_all(exp.Where):
        for col in where.find_all(exp.Column):
            names.add(col.name)
    for join in root.find_all(exp.Join):
        on = join.args.get("on")
        if on is not None:
            for col in on.find_all(exp.Column):
                names.add(col.name)
    return names


# ---------------------------------------------------------------------------
# Self-check (run as `python -m app.retrievers._sql.validator`)
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    cases_safe = [
        # plain community-scoped SELECT
        ("SELECT name FROM community WHERE id = 1 AND community_id = 1", True, False),
        # join + community predicate via WHERE
        (
            "SELECT v.hr FROM vw_resident_sensor vrs JOIN vitals v "
            "ON v.board = vrs.object_id WHERE vrs.community_id = 1 "
            "AND vrs.resident_id = 42",
            True, True,
        ),
        # admin cross-community query (explicit opt-out)
        ("SELECT severity, COUNT(*) FROM security_incidents GROUP BY severity", False, False),
        # WITH ... SELECT
        (
            "WITH r AS (SELECT id FROM rooms WHERE community_id = 1) "
            "SELECT id FROM r",
            True, False,
        ),
    ]

    cases_unsafe = [
        "SELECT 1; DROP TABLE users",
        "UPDATE users SET name = 'x'",
        "DELETE FROM users WHERE id = 1",
        "WITH x AS (SELECT 1) INSERT INTO users VALUES (1)",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM pg_catalog.pg_user",
        "SELECT * FROM users -- comment",
        "SELECT 1 /* block */",
        "SELECT * FROM unknown_table",
        # missing community predicate
        "SELECT * FROM vitals WHERE board = 'X'",
    ]

    passed = failed = 0
    for sql, enforce_c, enforce_r in cases_safe:
        try:
            r = validate_sql(sql, enforce_community_scope=enforce_c, enforce_resident_scope=enforce_r)
            print(f"  SAFE OK   tables={r.tables}  community={r.has_community_predicate}  resident={r.has_resident_predicate}  -- {sql[:60]}")
            passed += 1
        except UnsafeSQLError as e:
            print(f"  SAFE FAIL ({e}) -- {sql[:60]}")
            failed += 1

    for sql in cases_unsafe:
        try:
            validate_sql(sql)
            print(f"  UNSAFE FAIL (no error raised) -- {sql[:60]}")
            failed += 1
        except UnsafeSQLError as e:
            print(f"  UNSAFE OK ({e}) -- {sql[:60]}")
            passed += 1

    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(0 if failed == 0 else 1)
