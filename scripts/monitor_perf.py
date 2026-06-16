import argparse
import json
import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parents[1] / "ats.db"


def rows_as_dicts(rows):
    return [dict(row) for row in rows]


def main():
    parser = argparse.ArgumentParser(description="Summarize recent ATS performance logs.")
    parser.add_argument("--minutes", type=int, default=120)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='performance_logs'"
        ).fetchone()
        if not exists:
            print("performance_logs table does not exist yet.")
            return

        total = conn.execute("SELECT COUNT(*) AS n FROM performance_logs").fetchone()["n"]
        recent_count = conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM performance_logs
            WHERE datetime(created_at) >= datetime('now','localtime', ?)
            """,
            (f"-{args.minutes} minutes",),
        ).fetchone()["n"]
        print(f"DB={DB_PATH}")
        print(f"total_logs={total} recent_logs_{args.minutes}m={recent_count}")

        slow_by_path = conn.execute(
            """
            SELECT path,
                   COUNT(*) AS calls,
                   ROUND(AVG(elapsed_ms), 1) AS avg_ms,
                   ROUND(MAX(elapsed_ms), 1) AS max_ms,
                   SUM(CASE WHEN elapsed_ms >= 750 THEN 1 ELSE 0 END) AS slow_750ms
            FROM performance_logs
            WHERE datetime(created_at) >= datetime('now','localtime', ?)
            GROUP BY path
            ORDER BY avg_ms DESC
            LIMIT ?
            """,
            (f"-{args.minutes} minutes", args.limit),
        ).fetchall()
        print("\nslow_by_path")
        print(json.dumps(rows_as_dicts(slow_by_path), indent=2))

        slow_by_user = conn.execute(
            """
            SELECT COALESCE(NULLIF(username,''), recruiter_name, recruiter_email, '-') AS user,
                   COUNT(*) AS calls,
                   ROUND(AVG(elapsed_ms), 1) AS avg_ms,
                   ROUND(MAX(elapsed_ms), 1) AS max_ms
            FROM performance_logs
            WHERE datetime(created_at) >= datetime('now','localtime', ?)
            GROUP BY user
            ORDER BY avg_ms DESC
            LIMIT ?
            """,
            (f"-{args.minutes} minutes", args.limit),
        ).fetchall()
        print("\nslow_by_user")
        print(json.dumps(rows_as_dicts(slow_by_user), indent=2))

        recent = conn.execute(
            """
            SELECT created_at, username, path, status_code, ROUND(elapsed_ms, 1) AS elapsed_ms
            FROM performance_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
        print("\nrecent")
        print(json.dumps(rows_as_dicts(recent), indent=2))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
