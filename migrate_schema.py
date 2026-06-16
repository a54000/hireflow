import argparse
import os
import shutil
import sqlite3
from datetime import datetime

from ats_schema import ensure_ats_pipeline_schema


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


CORE_ALTERS = {
    "candidates": {
        "sourcer_id": "INTEGER",
        "requirement_id": "INTEGER",
    },
    "app_users": {
        "is_bulk_admin": "INTEGER DEFAULT 0",
        "is_active": "INTEGER DEFAULT 1",
    },
    "requirements": {
        "jd_filename": "TEXT",
        "jd_url": "TEXT",
        "jd_public_id": "TEXT",
    },
}


CORE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS requirements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    client_name TEXT,
    jd_filename TEXT,
    jd_url TEXT,
    jd_public_id TEXT,
    assigned_sourcer_id INTEGER,
    assigned_recruiter_id INTEGER,
    daily_target INTEGER DEFAULT 3,
    status TEXT DEFAULT 'Open',
    created_by TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS requirement_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requirement_id INTEGER NOT NULL,
    check_name TEXT NOT NULL,
    check_description TEXT,
    check_type TEXT DEFAULT 'boolean',
    pass_criteria TEXT,
    is_mandatory INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS requirement_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    requirement_id INTEGER NOT NULL,
    sourcer_id INTEGER,
    submitted_by TEXT,
    status TEXT DEFAULT 'Submitted',
    notes TEXT,
    recruiter_feedback TEXT,
    feedback_by INTEGER,
    submitted_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS submission_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id INTEGER NOT NULL,
    check_id INTEGER NOT NULL,
    check_name TEXT,
    passed INTEGER DEFAULT 0,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    used INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS user_registration_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT NOT NULL,
    username TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    token TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'pending',
    approved_by INTEGER,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    approved_at TEXT
);
"""


def table_exists(conn, table):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def column_names(conn, table):
    if not table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def migrate(db_path, backup=True):
    db_path = os.path.abspath(db_path)
    if not os.path.exists(db_path):
        raise FileNotFoundError(db_path)
    if backup:
        backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(db_path, backup_path)
        print(f"Backup created: {backup_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_ats_pipeline_schema(conn)
    conn.executescript(CORE_TABLES_SQL)
    for table, columns in CORE_ALTERS.items():
        existing = column_names(conn, table)
        if not existing:
            continue
        for column, column_type in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
                print(f"Added {table}.{column}")
    conn.commit()
    tables = [
        "skills", "skill_aliases", "candidate_skills", "candidate_roles", "candidate_domains",
        "jd_requirements", "match_results", "parsed_resume_cache", "normalized_skill_cache",
        "embedding_cache", "requirements", "requirement_checks",
        "password_reset_tokens", "user_registration_requests",
    ]
    for table in tables:
        status = "ok" if table_exists(conn, table) else "missing"
        print(f"{table}: {status}")
    conn.close()
    print("Schema migration complete. Candidate data was not modified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate an ATS SQLite database to the latest schema.")
    parser.add_argument("--db", default=os.path.join(BASE_DIR, "ats.db"), help="Path to ats.db")
    parser.add_argument("--no-backup", action="store_true", help="Skip backup copy")
    args = parser.parse_args()
    migrate(args.db, backup=not args.no_backup)
