#!/usr/bin/env python3
"""
Migrate the HR Guru ATS SQLite database to PostgreSQL.

Usage:
  python scripts/migrate_sqlite_to_postgres.py --sqlite ats.db --database-url postgresql://user:pass@127.0.0.1:5432/hrguru_ats
  python scripts/migrate_sqlite_to_postgres.py --drop-existing

By default this script creates missing PostgreSQL tables and stops if a target
table already contains rows. Use --drop-existing for a clean reload.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from typing import Iterable

try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extras import execute_values
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: psycopg2. Install with: pip install psycopg2-binary"
    ) from exc


SKIP_TABLES = {"sqlite_sequence"}
SQLITE_TO_PG_TYPES = {
    "INTEGER": "INTEGER",
    "INT": "INTEGER",
    "TEXT": "TEXT",
    "VARCHAR": "TEXT",
    "CHAR": "TEXT",
    "REAL": "DOUBLE PRECISION",
    "FLOAT": "DOUBLE PRECISION",
    "DOUBLE": "DOUBLE PRECISION",
    "NUMERIC": "NUMERIC",
    "DECIMAL": "NUMERIC",
    "BLOB": "BYTEA",
    "BOOLEAN": "BOOLEAN",
    "DATE": "DATE",
    "DATETIME": "TIMESTAMP",
    "TIMESTAMP": "TIMESTAMP",
}


def clean_identifier(name: str) -> str:
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name or ""):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")
    return name


def sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [row[0] for row in rows if row[0] not in SKIP_TABLES]


def base_sqlite_type(declared_type: str) -> str:
    raw = (declared_type or "TEXT").strip().upper()
    return re.split(r"[\s(]", raw, 1)[0] or "TEXT"


def pg_type_for(declared_type: str) -> str:
    base = base_sqlite_type(declared_type)
    return SQLITE_TO_PG_TYPES.get(base, "TEXT")


def pg_default(sqlite_default):
    if sqlite_default is None:
        return None
    raw = str(sqlite_default).strip()
    low = raw.lower()
    if "datetime('now'" in low or 'datetime("now"' in low:
        return "CURRENT_TIMESTAMP"
    if low in {"current_timestamp", "current_date", "current_time"}:
        return low.upper()
    if raw.startswith("'") and raw.endswith("'"):
        return raw
    if re.match(r"^-?\d+(\.\d+)?$", raw):
        return raw
    if low in {"true", "false"}:
        return low.upper()
    return None


def table_columns(sqlite_conn: sqlite3.Connection, table: str) -> list[dict]:
    clean_identifier(table)
    rows = sqlite_conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [
        {
            "cid": row[0],
            "name": row[1],
            "type": row[2] or "TEXT",
            "notnull": bool(row[3]),
            "default": row[4],
            "pk": int(row[5] or 0),
        }
        for row in rows
    ]


def create_table(pg_conn, table: str, columns: list[dict]):
    clean_identifier(table)
    column_defs = []
    pk_cols = []
    for col in columns:
        name = clean_identifier(col["name"])
        col_type = pg_type_for(col["type"])
        parts = [sql.Identifier(name), sql.SQL(col_type)]
        default = pg_default(col["default"])
        if default:
            parts.extend([sql.SQL("DEFAULT"), sql.SQL(default)])
        if col["notnull"] and not col["pk"]:
            parts.append(sql.SQL("NOT NULL"))
        column_defs.append(sql.SQL(" ").join(parts))
        if col["pk"]:
            pk_cols.append(name)
    if pk_cols:
        column_defs.append(
            sql.SQL("PRIMARY KEY ({})").format(
                sql.SQL(", ").join(sql.Identifier(col) for col in pk_cols)
            )
        )
    query = sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
        sql.Identifier(table),
        sql.SQL(", ").join(column_defs),
    )
    with pg_conn.cursor() as cur:
        cur.execute(query)


def create_unique_indexes(sqlite_conn: sqlite3.Connection, pg_conn, table: str):
    clean_identifier(table)
    indexes = sqlite_conn.execute(f"PRAGMA index_list({table})").fetchall()
    with pg_conn.cursor() as cur:
        for idx in indexes:
            index_name = idx[1]
            is_unique = bool(idx[2])
            origin = idx[3] if len(idx) > 3 else ""
            if not is_unique or origin == "pk":
                continue
            clean_identifier(index_name)
            cols = sqlite_conn.execute(f"PRAGMA index_info({index_name})").fetchall()
            col_names = [row[2] for row in cols if row[2]]
            if not col_names:
                continue
            pg_index_name = f"{table}_{index_name}_uidx"[:60]
            cur.execute(
                sql.SQL("CREATE UNIQUE INDEX IF NOT EXISTS {} ON {} ({})").format(
                    sql.Identifier(pg_index_name),
                    sql.Identifier(table),
                    sql.SQL(", ").join(sql.Identifier(clean_identifier(c)) for c in col_names),
                )
            )


def target_row_count(pg_conn, table: str) -> int:
    with pg_conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table)))
        return int(cur.fetchone()[0])


def sqlite_row_count(sqlite_conn: sqlite3.Connection, table: str) -> int:
    clean_identifier(table)
    return int(sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def iter_sqlite_rows(sqlite_conn: sqlite3.Connection, table: str, columns: list[str], batch_size: int):
    clean_identifier(table)
    quoted_cols = ", ".join(f'"{c}"' for c in columns)
    cursor = sqlite_conn.execute(f'SELECT {quoted_cols} FROM "{table}"')
    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        yield rows


def insert_rows(pg_conn, table: str, columns: list[str], rows: Iterable[sqlite3.Row]):
    rows = [tuple(row[col] for col in columns) for row in rows]
    if not rows:
        return 0
    with pg_conn.cursor() as cur:
        query = sql.SQL("INSERT INTO {} ({}) VALUES %s").format(
            sql.Identifier(table),
            sql.SQL(", ").join(sql.Identifier(col) for col in columns),
        )
        execute_values(cur, query.as_string(pg_conn), rows, page_size=1000)
    return len(rows)


def reset_integer_pk_sequence(pg_conn, table: str, columns: list[dict]):
    pk_cols = [c for c in columns if c["pk"]]
    if len(pk_cols) != 1:
        return
    pk = pk_cols[0]
    if pg_type_for(pk["type"]) != "INTEGER":
        return
    seq_name = f"{table}_{pk['name']}_seq"
    clean_identifier(seq_name)
    with pg_conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SEQUENCE IF NOT EXISTS {}").format(sql.Identifier(seq_name)))
        cur.execute(
            sql.SQL("SELECT COALESCE(MAX({}), 0) + 1 FROM {}").format(
                sql.Identifier(pk["name"]),
                sql.Identifier(table),
            )
        )
        next_id = int(cur.fetchone()[0])
        cur.execute(sql.SQL("SELECT setval({}, %s, false)").format(sql.Literal(seq_name)), (next_id,))
        cur.execute(
            sql.SQL("ALTER TABLE {} ALTER COLUMN {} SET DEFAULT nextval({})").format(
                sql.Identifier(table),
                sql.Identifier(pk["name"]),
                sql.Literal(seq_name),
            )
        )
        cur.execute(sql.SQL("ALTER SEQUENCE {} OWNED BY {}.{}").format(
            sql.Identifier(seq_name),
            sql.Identifier(table),
            sql.Identifier(pk["name"]),
        ))


def migrate(args):
    sqlite_path = args.sqlite
    if not os.path.exists(sqlite_path):
        raise SystemExit(f"SQLite DB not found: {sqlite_path}")
    database_url = args.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("PostgreSQL URL required. Pass --database-url or set DATABASE_URL.")

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = psycopg2.connect(database_url)
    pg_conn.autocommit = False

    try:
        tables = args.tables or sqlite_tables(sqlite_conn)
        tables = [t for t in tables if t not in SKIP_TABLES]
        print(f"SQLite: {sqlite_path}")
        print(f"Tables: {len(tables)}")

        with pg_conn.cursor() as cur:
            if args.drop_existing:
                for table in reversed(tables):
                    print(f"drop {table}")
                    cur.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(sql.Identifier(table)))
            pg_conn.commit()

        results = []
        for table in tables:
            clean_identifier(table)
            columns_meta = table_columns(sqlite_conn, table)
            columns = [clean_identifier(c["name"]) for c in columns_meta]
            print(f"\n== {table} ==")
            create_table(pg_conn, table, columns_meta)
            create_unique_indexes(sqlite_conn, pg_conn, table)
            pg_conn.commit()

            existing = target_row_count(pg_conn, table)
            if existing and not args.append:
                raise RuntimeError(
                    f"Target table {table} already has {existing} rows. "
                    "Use --drop-existing for clean reload or --append to append."
                )

            inserted = 0
            for batch in iter_sqlite_rows(sqlite_conn, table, columns, args.batch_size):
                inserted += insert_rows(pg_conn, table, columns, batch)
                pg_conn.commit()
            reset_integer_pk_sequence(pg_conn, table, columns_meta)
            pg_conn.commit()

            source_count = sqlite_row_count(sqlite_conn, table)
            target_count = target_row_count(pg_conn, table)
            status = "OK" if target_count >= source_count else "MISMATCH"
            print(f"{table}: sqlite={source_count} inserted={inserted} postgres={target_count} {status}")
            results.append((table, source_count, target_count, status))

        bad = [r for r in results if r[3] != "OK"]
        print("\nValidation")
        for table, source_count, target_count, status in results:
            print(f"{table}: sqlite {source_count} -> postgres {target_count} {status}")
        if bad:
            raise SystemExit("Migration completed with row-count mismatches.")
        print("\nMigration completed successfully.")
    except Exception:
        pg_conn.rollback()
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Migrate ATS SQLite database to PostgreSQL.")
    parser.add_argument("--sqlite", default="ats.db", help="Path to SQLite database. Default: ats.db")
    parser.add_argument("--database-url", default="", help="PostgreSQL connection URL. Default: DATABASE_URL env var")
    parser.add_argument("--drop-existing", action="store_true", help="Drop target tables before migrating.")
    parser.add_argument("--append", action="store_true", help="Append into existing target tables.")
    parser.add_argument("--batch-size", type=int, default=1000, help="Rows per insert batch.")
    parser.add_argument("--tables", nargs="*", help="Optional list of tables to migrate.")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        migrate(parse_args())
    except KeyboardInterrupt:
        raise SystemExit("Interrupted.")
    except Exception as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        raise
