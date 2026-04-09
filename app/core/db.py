"""
Database connection layer.
Provides a psycopg2 connection pool and a safe run_query() helper.
"""
import psycopg2
from psycopg2 import pool
from app.core.config import DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_POOL_MIN, DB_POOL_MAX

db_pool = psycopg2.pool.SimpleConnectionPool(
    DB_POOL_MIN, DB_POOL_MAX,
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASS,
    host=DB_HOST,
    port=DB_PORT,
)


def run_query(sql, params=None):
    """Execute a read query and return all rows."""
    conn = db_pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        data = cur.fetchall()
        cur.close()
        return data
    finally:
        db_pool.putconn(conn)