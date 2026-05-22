"""
Database connection layer.
Provides a psycopg2 connection pool and a safe run_query() helper.

The pool is created lazily so a missing or unreachable database does not crash
import. Failed queries roll back and recycle the connection so a single bad
query cannot poison the pool. Callers are responsible for turning the raised
DatabaseUnavailableError into a safe, user-facing message.
"""
import psycopg2
from psycopg2 import pool

from app.core.config import DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_POOL_MIN, DB_POOL_MAX
from app.core.logger import get_logger

logger = get_logger("db")


class DatabaseUnavailableError(RuntimeError):
    """Raised when the pool cannot be created or a query fails.

    The message is intentionally generic; technical detail is logged instead of
    being surfaced to callers.
    """


_REQUIRED_DB_SETTINGS = {
    "DB_NAME": DB_NAME,
    "DB_USER": DB_USER,
    "DB_PASS": DB_PASS,
    "DB_HOST": DB_HOST,
    "DB_PORT": DB_PORT,
}

# Lazily initialized SimpleConnectionPool. None until the first successful query.
db_pool = None


def _missing_db_settings() -> list[str]:
    return [name for name, value in _REQUIRED_DB_SETTINGS.items() if value in (None, "")]


def _get_pool():
    """Return the connection pool, creating it on first use."""
    global db_pool
    if db_pool is not None:
        return db_pool

    missing = _missing_db_settings()
    if missing:
        logger.error(f"Database configuration incomplete; missing: {', '.join(missing)}")
        raise DatabaseUnavailableError("Database configuration is incomplete.")

    try:
        db_pool = psycopg2.pool.SimpleConnectionPool(
            DB_POOL_MIN, DB_POOL_MAX,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT,
        )
    except psycopg2.Error as exc:
        logger.error(f"Failed to create database connection pool: {exc}")
        raise DatabaseUnavailableError("Database connection pool could not be created.") from exc

    return db_pool


def run_query(sql, params=None):
    """Execute a read query and return all rows.

    On failure the connection is rolled back and, if it cannot be recovered,
    discarded so the pool is not left holding an aborted transaction. Raises
    DatabaseUnavailableError; the full error is logged, not returned.
    """
    pool_ = _get_pool()
    conn = pool_.getconn()
    close_on_error = False
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            data = cur.fetchall()
        # End the implicit read transaction so the pooled connection is reusable.
        conn.rollback()
        return data
    except psycopg2.Error as exc:
        logger.error(f"Query failed: {exc}", extra={"query": sql})
        # Recover the connection; if rollback also fails, discard it on return.
        close_on_error = True
        try:
            conn.rollback()
            close_on_error = False
        except psycopg2.Error as rollback_exc:
            logger.error(f"Rollback after failed query failed: {rollback_exc}")
        raise DatabaseUnavailableError("Database query failed.") from exc
    finally:
        pool_.putconn(conn, close=close_on_error)
