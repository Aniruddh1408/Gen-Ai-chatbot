"""CLI to apply the Kubocare demo seed to the configured database.

Usage:
    python scripts/apply_seed.py             # refuses on ENVIRONMENT=production
    python scripts/apply_seed.py --force     # override guard for staging/QA

Reads DB credentials from .env (DB_NAME / DB_USER / DB_PASS / DB_HOST / DB_PORT).

The seed file `data/kubo_dummy.sql` is two sections concatenated:
  1. A pg_dump-style schema section (CREATE TYPE / CREATE TABLE / CREATE
     SEQUENCE / FK ALTERs). NOT idempotent — re-applying against a populated
     DB errors at the first "type already exists".
  2. A `BEGIN; ... COMMIT;` seed section. Idempotent (TRUNCATE … RESTART
     IDENTITY CASCADE followed by INSERTs).

This runner detects which case it's in:
  - If the marker table `public.community` already exists, it executes only
    section 2 (the seed re-runs cleanly).
  - Otherwise it executes the whole file (fresh install).

It also strips psql client meta-commands (lines starting with backslash,
e.g. `\\restrict` / `\\unrestrict`) since psycopg2 cannot parse them.
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

import psycopg2  # noqa: E402

from app.core.config import DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT  # noqa: E402
from app.core.logger import get_logger  # noqa: E402

logger = get_logger("seed")

SEED_FILE = Path(__file__).resolve().parents[1] / "data" / "kubo_dummy.sql"


def _require_db_config() -> None:
    missing = [
        name for name, value in (
            ("DB_NAME", DB_NAME), ("DB_USER", DB_USER), ("DB_PASS", DB_PASS),
            ("DB_HOST", DB_HOST), ("DB_PORT", DB_PORT),
        ) if not value
    ]
    if missing:
        raise SystemExit(
            f"Database configuration is incomplete; missing: {', '.join(missing)}"
        )


def _refuse_in_production(force: bool) -> None:
    """Block accidental destructive runs. ENVIRONMENT=production always refuses."""
    env = (os.getenv("ENVIRONMENT") or "").strip().lower()
    if env == "production":
        raise SystemExit(
            "Refusing to seed: ENVIRONMENT=production. This seed TRUNCATEs "
            "reference tables and CASCADEs into sensor data. There is no "
            "override for production."
        )
    if not force:
        raise SystemExit(
            "Refusing to seed without --force. The seed is destructive: "
            "it wipes organisation, community, users, rooms, objects, and "
            "every row that FKs into them (activity_log, incidents, "
            "insights, notifications, etc.). Re-run with --force when you "
            "are sure this is a demo/staging database."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply the Kubocare demo seed.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Acknowledge the destructive truncation and proceed.",
    )
    args = parser.parse_args()

    _refuse_in_production(args.force)
    _require_db_config()

    if not SEED_FILE.is_file():
        print(f"FAILED: seed file not found at {SEED_FILE}", file=sys.stderr)
        return 1

    raw_sql = SEED_FILE.read_text(encoding="utf-8")

    # Strip psql client meta-commands (lines starting with backslash) — pg_dump
    # emits these and psycopg2 errors on the first one.
    sql_lines = [line for line in raw_sql.splitlines() if not line.lstrip().startswith("\\")]
    sql_full = "\n".join(sql_lines)

    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASS,
        host=DB_HOST, port=DB_PORT,
    )
    try:
        # Schema-already-present probe. If `community` exists, treat this as
        # a re-seed and skip the schema section above the first BEGIN.
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.community')")
            schema_present = cur.fetchone()[0] is not None
        conn.rollback()  # close the probe txn cleanly before DDL/DML

        if schema_present:
            begin_idx = sql_full.find("BEGIN;")
            if begin_idx == -1:
                print(
                    "FAILED: schema is already loaded but seed file has no "
                    "BEGIN; block to re-apply.",
                    file=sys.stderr,
                )
                return 1
            sql_to_run = sql_full[begin_idx:]
            mode = "re-seed (schema already present; skipped CREATE TYPE/TABLE section)"
        else:
            sql_to_run = sql_full
            mode = "fresh install (schema + seed)"

        with conn.cursor() as cur:
            cur.execute(sql_to_run)
        conn.commit()
    except psycopg2.Error as exc:
        conn.rollback()
        logger.error(f"Seed {SEED_FILE.name} failed: {exc}")
        print(
            f"FAILED: {SEED_FILE.name} did not apply; see logs for details.",
            file=sys.stderr,
        )
        return 1
    finally:
        conn.close()

    logger.info(f"Applied seed: {SEED_FILE.name} [{mode}]")
    print(f"Applied seed: {SEED_FILE.name} [{mode}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
