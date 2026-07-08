#!/usr/bin/env python3
"""Weekly team submission summary for WhatsApp.

Run on Saturday evening. The report covers Monday through the selected end date.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import get_db  # noqa: E402
from scripts.whatsapp_send import send_to_webhook  # noqa: E402


EXCLUDED_NAMES = {"reetu", "reetu saini", "megha", "megha singh", "parul", "parul yadav"}


def load_env_file() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send weekly ATS submission summary to WhatsApp.")
    parser.add_argument("--date", default="", help="Week ending date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--days-ago", type=int, default=None, help="Relative week ending date. 1=yesterday.")
    parser.add_argument("--send", action="store_true", help="POST the message to TEAM_SUBMISSION_WHATSAPP_WEBHOOK_URL.")
    parser.add_argument("--webhook-url", default=os.getenv("TEAM_SUBMISSION_WHATSAPP_WEBHOOK_URL", ""))
    parser.add_argument("--group-id", default=os.getenv("TEAM_SUBMISSION_WHATSAPP_GROUP_ID", ""))
    parser.add_argument("--token", default=os.getenv("TEAM_SUBMISSION_WHATSAPP_TOKEN", ""))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("TEAM_SUBMISSION_WHATSAPP_TIMEOUT", "20")))
    parser.add_argument("--output", default="", help="Optional file path to save the generated text report.")
    return parser.parse_args()


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalized_name(value: object) -> str:
    return clean_text(value).lower()


def report_end_date(value: str, days_ago: int | None = None) -> date:
    if days_ago is not None:
        if days_ago < 0:
            raise ValueError("--days-ago cannot be negative")
        return date.today() - timedelta(days=days_ago)
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def active_team_members(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, name, email, role
        FROM team_members
        WHERE COALESCE(is_ex_employee,0)=0
          AND lower(trim(COALESCE(role,''))) NOT IN (
              'admin',
              'bulk admin',
              'client viewer',
              'client_viewer',
              'external client',
              'external_client',
              'client user',
              'client_user'
          )
          AND NOT EXISTS (
              SELECT 1
              FROM app_users u
              WHERE u.team_member_id=team_members.id
                AND COALESCE(u.is_active,1)=1
                AND COALESCE(u.is_admin,0)=1
          )
          AND (
              NOT EXISTS (
                  SELECT 1
                  FROM app_users u
                  WHERE u.team_member_id=team_members.id
              )
              OR EXISTS (
                  SELECT 1
                  FROM app_users u
                  WHERE u.team_member_id=team_members.id
                    AND COALESCE(u.is_active,1)=1
              )
          )
        ORDER BY lower(COALESCE(name,email,'')), id
        """
    ).fetchall()
    members = []
    seen = set()
    for row in rows:
        name = clean_text(row["name"]) or clean_text(row["email"]) or f"Team Member {row['id']}"
        if normalized_name(name) in EXCLUDED_NAMES:
            continue
        email = clean_text(row["email"]).lower()
        if email in EXCLUDED_NAMES:
            continue
        key = (int(row["id"]), email)
        if key in seen:
            continue
        seen.add(key)
        members.append({
            "id": int(row["id"]),
            "name": name,
            "email": email,
            "role": clean_text(row["role"]),
        })
    return members


def submission_counts(conn, start_day: date, end_day: date, members: list[dict]) -> tuple[dict[int, int], list[dict]]:
    member_by_id = {member["id"]: member for member in members}
    member_by_email = {member["email"]: member for member in members if member["email"]}
    counts = {member["id"]: 0 for member in members}
    unmapped: dict[str, dict] = {}

    rows = conn.execute(
        """
        SELECT sourcer_id, recruiter_email, recruiter_name, COUNT(*) AS submissions
        FROM candidates
        WHERE COALESCE(is_duplicate,0)=0
          AND substr(COALESCE(created_at,''),1,10) BETWEEN ? AND ?
        GROUP BY sourcer_id, recruiter_email, recruiter_name
        """,
        (start_day.isoformat(), end_day.isoformat()),
    ).fetchall()

    for row in rows:
        count = int(row["submissions"] or 0)
        sourcer_id = row["sourcer_id"]
        email = clean_text(row["recruiter_email"]).lower()
        name = clean_text(row["recruiter_name"])
        if normalized_name(name) in EXCLUDED_NAMES or email in EXCLUDED_NAMES:
            continue
        member = member_by_id.get(int(sourcer_id)) if sourcer_id else None
        if not member and email:
            member = member_by_email.get(email)
        if member:
            counts[member["id"]] += count
            continue
        key = email or name or "Unmapped"
        entry = unmapped.setdefault(key, {
            "name": name or key,
            "email": email,
            "submissions": 0,
        })
        entry["submissions"] += count

    return counts, sorted(unmapped.values(), key=lambda item: item["name"].lower())


def build_report(end_day: date) -> dict:
    start_day = week_start(end_day)
    conn = get_db(timeout=20)
    try:
        members = active_team_members(conn)
        counts, unmapped = submission_counts(conn, start_day, end_day, members)
    finally:
        conn.close()

    rows = []
    for member in members:
        rows.append({
            "name": member["name"],
            "email": member["email"],
            "submissions": int(counts.get(member["id"], 0)),
        })
    rows.sort(key=lambda item: (-item["submissions"], item["name"].lower()))
    total = sum(row["submissions"] for row in rows)
    active = sum(1 for row in rows if row["submissions"] > 0)
    return {
        "start_date": start_day.isoformat(),
        "end_date": end_day.isoformat(),
        "rows": rows,
        "unmapped": unmapped,
        "totals": {
            "team_members": len(rows),
            "active_submitters": active,
            "zero_submitters": len(rows) - active,
            "submissions": total,
        },
    }


def build_whatsapp_message(report: dict) -> str:
    totals = report["totals"]
    active_rows = [row for row in report["rows"] if row["submissions"] > 0]
    zero_rows = [row for row in report["rows"] if row["submissions"] == 0]
    top_rows = active_rows[:5]
    lines = [
        "*ATS Weekly Submission Report*",
        f"{report['start_date']} to {report['end_date']}",
        "",
        "*Summary*",
        f"Total: *{totals['submissions']}* submissions",
        f"Submitted by: *{totals['active_submitters']}* of {totals['team_members']}",
        f"Attention needed: *{totals['zero_submitters']}*",
        "",
    ]
    if top_rows:
        lines.append("*Top 5 This Week*")
        for index, row in enumerate(top_rows, start=1):
            lines.append(f"{index}. {row['name']} - *{row['submissions']}*")
        lines.append("")

    if active_rows:
        lines.append("*Full Team Ranking*")
        for index, row in enumerate(active_rows, start=1):
            lines.append(f"{index}. {row['name']} - {row['submissions']}")
    else:
        lines.append("*Full Team Ranking*")
        lines.append("No submissions recorded in this period.")

    if zero_rows:
        lines.extend(["", "*Attention Needed - No Submissions*"])
        for row in zero_rows:
            lines.append(f"- *{row['name']}*")

    if report.get("unmapped"):
        lines.extend(["", "*Unmapped submissions*"])
        for row in report["unmapped"]:
            label = row["name"]
            if row.get("email"):
                label = f"{label} ({row['email']})"
            lines.append(f"{label} | {row['submissions']}")
    return "\n".join(lines)


def main() -> int:
    load_env_file()
    args = parse_args()
    end_day = report_end_date(args.date, args.days_ago)
    report = build_report(end_day)
    message = build_whatsapp_message(report)
    if args.output:
        Path(args.output).write_text(message, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(message)
    if args.send:
        ok, detail = send_to_webhook(message, args)
        print(detail, file=sys.stderr)
        return 0 if ok else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
