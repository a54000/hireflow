ATS_PIPELINE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_value TEXT,
    canonical_value TEXT NOT NULL UNIQUE,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS skill_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id INTEGER NOT NULL,
    alias TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(skill_id, alias),
    FOREIGN KEY(skill_id) REFERENCES skills(id)
);
CREATE TABLE IF NOT EXISTS candidate_skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER,
    resume_hash TEXT,
    raw_value TEXT,
    canonical_value TEXT NOT NULL,
    confidence REAL DEFAULT 0,
    skill_type TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS candidate_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER,
    resume_hash TEXT,
    raw_value TEXT,
    canonical_value TEXT NOT NULL,
    confidence REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS candidate_domains (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER,
    resume_hash TEXT,
    raw_value TEXT,
    canonical_value TEXT NOT NULL,
    confidence REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS jd_requirements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jd_hash TEXT UNIQUE,
    role_title TEXT,
    parsed_json TEXT,
    pipeline_version TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS match_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jd_hash TEXT,
    resume_hash TEXT,
    pipeline_version TEXT,
    final_score INTEGER,
    structured_score INTEGER,
    semantic_score INTEGER,
    hard_filter_score INTEGER,
    result_json TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS parsed_resume_cache (
    resume_hash TEXT PRIMARY KEY,
    parsed_json TEXT NOT NULL,
    pipeline_version TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS normalized_skill_cache (
    raw_value TEXT PRIMARY KEY,
    canonical_value TEXT NOT NULL,
    aliases_json TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE TABLE IF NOT EXISTS embedding_cache (
    text_hash TEXT NOT NULL,
    model TEXT NOT NULL,
    embedding_json TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY(text_hash, model)
);
CREATE TABLE IF NOT EXISTS match_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    object_type TEXT NOT NULL,
    object_hash TEXT,
    jd_hash TEXT,
    resume_hash TEXT,
    pipeline_version TEXT,
    status TEXT,
    source TEXT,
    parser_confidence TEXT,
    manual_review_required INTEGER DEFAULT 0,
    score INTEGER,
    message TEXT,
    details_json TEXT,
    ip_address TEXT,
    user_agent TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
"""


REQUIRED_COLUMNS = {
    "jd_requirements": {
        "pipeline_version": "TEXT",
    },
    "match_results": {
        "jd_hash": "TEXT",
        "resume_hash": "TEXT",
        "pipeline_version": "TEXT",
        "result_json": "TEXT",
        "hard_filter_score": "INTEGER",
    },
    "skills": {
        "raw_value": "TEXT",
        "canonical_value": "TEXT",
    },
    "candidate_skills": {
        "raw_value": "TEXT",
        "canonical_value": "TEXT",
        "resume_hash": "TEXT",
    },
    "parsed_resume_cache": {
        "pipeline_version": "TEXT",
    },
    "match_audit_log": {
        "pipeline_version": "TEXT",
    },
}


def _is_postgres_conn(conn):
    return conn.__class__.__name__ == "PgConnectionAdapter"


def _table_columns(conn, table):
    if _is_postgres_conn(conn):
        return conn.execute(
            """
            SELECT
                column_name AS name,
                CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END AS notnull
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ?
            ORDER BY ordinal_position
            """,
            (table,),
        ).fetchall()
    return conn.execute(f"PRAGMA table_info({table})").fetchall()


def _column_name(row):
    return row["name"] if hasattr(row, "keys") else row[1]


def _column_not_null(row):
    return row["notnull"] if hasattr(row, "keys") else row[3]


def _table_exists(conn, table):
    if _is_postgres_conn(conn):
        return conn.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ?
            LIMIT 1
            """,
            (table,),
        ).fetchone() is not None
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone() is not None


def _migrate_match_results_if_legacy(conn):
    if not _table_exists(conn, "match_results"):
        return
    columns = _table_columns(conn, "match_results")
    by_name = {_column_name(row): row for row in columns}
    legacy_not_null = (
        "candidate_id" in by_name and _column_not_null(by_name["candidate_id"]) or
        "requirement_id" in by_name and _column_not_null(by_name["requirement_id"])
    )
    if not legacy_not_null:
        return
    conn.execute("DROP TABLE IF EXISTS match_results_legacy")
    conn.execute("ALTER TABLE match_results RENAME TO match_results_legacy")
    conn.execute("""
        CREATE TABLE match_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jd_hash TEXT,
            resume_hash TEXT,
            pipeline_version TEXT,
            final_score INTEGER,
            structured_score INTEGER,
            semantic_score INTEGER,
            hard_filter_score INTEGER,
            result_json TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    legacy_cols = {
        _column_name(row)
        for row in _table_columns(conn, "match_results_legacy")
    }
    if {"final_score", "structured_score", "semantic_score", "created_at"}.issubset(legacy_cols):
        conn.execute("""
            INSERT INTO match_results
                (final_score, structured_score, semantic_score, hard_filter_score, created_at)
            SELECT final_score, structured_score, semantic_score, 0, created_at
            FROM match_results_legacy
        """)


def ensure_ats_pipeline_schema(conn):
    _migrate_match_results_if_legacy(conn)
    conn.executescript(ATS_PIPELINE_TABLES_SQL)
    for table, columns in REQUIRED_COLUMNS.items():
        existing = {
            _column_name(row)
            for row in _table_columns(conn, table)
        }
        for column, column_type in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_match_results_hashes ON match_results(jd_hash, resume_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_match_results_pipeline_version ON match_results(pipeline_version)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_candidate_skills_resume_hash ON candidate_skills(resume_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_candidate_roles_resume_hash ON candidate_roles(resume_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_candidate_domains_resume_hash ON candidate_domains(resume_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_match_audit_log_object ON match_audit_log(object_type, object_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_match_audit_log_hashes ON match_audit_log(jd_hash, resume_hash)")
