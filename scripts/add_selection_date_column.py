#!/usr/bin/env python3
"""Add candidates.selection_date for selection-month reporting.

Safe to run multiple times. Uses the app DB adapter so it works with both
SQLite development copies and PostgreSQL production.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import get_db, ensure_candidate_selection_schema  # noqa: E402


def main() -> int:
    conn = get_db(timeout=10)
    try:
        ensure_candidate_selection_schema(conn)
        print("Ensured candidates.selection_date column.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
