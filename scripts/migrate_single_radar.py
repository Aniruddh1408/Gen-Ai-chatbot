"""One-off migration: collapse each room's two sensor objects (sensor_fds +
sensor_vitals) into a SINGLE KuboCare radar device (object_type 'sensor').

The radar handles fall detection, bed algorithms, and vitals together, so the
demo's split fall/vitals sensors don't match reality. We keep the vitals sensor
(every vitals/sleep/wellness stream already joins to its object_id via `board`),
repoint incident events onto it, and drop the redundant fall-sensor rows.

Idempotent: re-running after migration is a no-op. Mirrors the seed change in
data/kubo_dummy.sql so a fresh re-seed produces the same single-radar layout.
"""
import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import DB_NAME, DB_USER, DB_PASS, DB_HOST, DB_PORT  # noqa: E402


def _count(cur, sql):
    cur.execute(sql)
    return cur.fetchone()[0]


def main() -> int:
    conn = psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT
    )
    try:
        with conn, conn.cursor() as cur:
            before_fds = _count(cur, "SELECT count(*) FROM objects WHERE object_type='sensor_fds'")
            before_vit = _count(cur, "SELECT count(*) FROM objects WHERE object_type='sensor_vitals'")
            print(f"Before: sensor_fds={before_fds}, sensor_vitals={before_vit}")
            if before_fds == 0 and before_vit == 0:
                print("Already migrated (no split sensors). Nothing to do.")
                return 0

            # 1. Repoint incident events from the fall sensor onto the room's
            #    vitals sensor (the device we keep). Done first, while the
            #    sensor_vitals type still exists.
            cur.execute(
                """
                UPDATE incidents i
                SET object_id = vit.object_id, object_type = 'sensor'
                FROM objects f
                JOIN objects vit
                  ON vit.room_id = f.room_id AND vit.object_type = 'sensor_vitals'
                WHERE f.object_type = 'sensor_fds' AND i.object_id = f.object_id
                """
            )
            print(f"  incidents repointed: {cur.rowcount}")

            # 2. Defensive: repoint any sensor stream that used a fall-sensor
            #    board id onto the room's vitals board id. (fds/board streams are
            #    empty in the seed, but stay correct if that ever changes.)
            for table, col in [
                ("vitals", "board"), ("motion", "board"), ("ambience", "board"),
                ("on_bed", "board"), ("sos", "board"), ("sleep_sessions", "board"),
                ("toss", "board"), ("movement_mapping", "board"),
                ("state_machine_binary", "board"), ("obj", "board"),
                ("wellness_metrics", "board"), ("insights", "board"),
                ("fds", "board_sn"),
            ]:
                cur.execute(
                    f"""
                    UPDATE {table} s
                    SET {col} = vit.object_id
                    FROM objects f
                    JOIN objects vit
                      ON vit.room_id = f.room_id AND vit.object_type = 'sensor_vitals'
                    WHERE f.object_type = 'sensor_fds' AND s.{col} = f.object_id
                    """
                )
                if cur.rowcount:
                    print(f"  {table}.{col} repointed: {cur.rowcount}")

            # 3. Convert the kept vitals sensor into the unified radar.
            cur.execute("UPDATE objects SET object_type='sensor' WHERE object_type='sensor_vitals'")
            print(f"  vitals sensors -> radar: {cur.rowcount}")

            # 4. Remove the now-redundant fall-sensor objects.
            cur.execute("DELETE FROM objects WHERE object_type='sensor_fds'")
            print(f"  fall sensors removed: {cur.rowcount}")

        with conn.cursor() as cur:
            radars = _count(cur, "SELECT count(*) FROM objects WHERE object_type='sensor'")
            rooms = _count(cur, "SELECT count(*) FROM rooms WHERE COALESCE(is_deleted,false)=false")
            leftover = _count(
                cur,
                "SELECT count(*) FROM objects WHERE object_type IN ('sensor_fds','sensor_vitals')",
            )
            print(f"After: radar devices={radars}, rooms={rooms}, split-sensors-left={leftover}")
            print("OK — one radar per room." if radars == rooms and leftover == 0
                  else "WARNING — counts do not line up; review.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
