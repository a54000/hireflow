#!/usr/bin/env python3
"""Daily team submission summary for WhatsApp.

Run at 19:00 IST Monday-Saturday. The script prints a WhatsApp-ready message by
default and POSTs it to TEAM_SUBMISSION_WHATSAPP_WEBHOOK_URL when --send is used.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import get_db  # noqa: E402


ATTENTION_LABEL = "*Attention Needed*"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send daily ATS submission summary to WhatsApp.")
    parser.add_argument("--date", default="", help="Report date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--days-ago", type=int, default=None, help="Relative report date. 1=yesterday, 2=day before yesterday.")
    parser.add_argument("--send", action="store_true", help="POST the message to TEAM_SUBMISSION_WHATSAPP_WEBHOOK_URL.")
    parser.add_argument("--include-sunday", action="store_true", help="Allow report generation on Sunday.")
    parser.add_argument("--webhook-url", default=os.getenv("TEAM_SUBMISSION_WHATSAPP_WEBHOOK_URL", ""))
    parser.add_argument("--group-id", default=os.getenv("TEAM_SUBMISSION_WHATSAPP_GROUP_ID", ""))
    parser.add_argument("--token", default=os.getenv("TEAM_SUBMISSION_WHATSAPP_TOKEN", ""))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("TEAM_SUBMISSION_WHATSAPP_TIMEOUT", "20")))
    return parser.parse_args()


def report_date(value: str, days_ago: int | None = None) -> date:
    if days_ago is not None:
        if days_ago < 0:
            raise ValueError("--days-ago cannot be negative")
        return date.today() - timedelta(days=days_ago)
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


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
        email = clean_text(row["email"]).lower()
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


def submission_counts(conn, day: date, members: list[dict]) -> tuple[dict[int, int], list[dict]]:
    member_by_id = {member["id"]: member for member in members}
    member_by_email = {member["email"]: member for member in members if member["email"]}
    counts = {member["id"]: 0 for member in members}
    unmapped: dict[str, dict] = {}

    rows = conn.execute(
        """
        SELECT sourcer_id, recruiter_email, recruiter_name, COUNT(*) AS submissions
        FROM candidates
        WHERE COALESCE(is_duplicate,0)=0
          AND substr(COALESCE(created_at,''),1,10)=?
        GROUP BY sourcer_id, recruiter_email, recruiter_name
        """,
        (day.isoformat(),),
    ).fetchall()

    for row in rows:
        count = int(row["submissions"] or 0)
        sourcer_id = row["sourcer_id"]
        email = clean_text(row["recruiter_email"]).lower()
        member = member_by_id.get(int(sourcer_id)) if sourcer_id else None
        if not member and email:
            member = member_by_email.get(email)
        if member:
            counts[member["id"]] += count
            continue
        key = email or clean_text(row["recruiter_name"]) or "Unmapped"
        entry = unmapped.setdefault(key, {
            "name": clean_text(row["recruiter_name"]) or key,
            "email": email,
            "submissions": 0,
        })
        entry["submissions"] += count

    return counts, sorted(unmapped.values(), key=lambda item: item["name"].lower())


def build_report(day: date) -> dict:
    conn = get_db(timeout=20)
    try:
        members = active_team_members(conn)
        counts, unmapped = submission_counts(conn, day, members)
    finally:
        conn.close()

    rows = []
    for member in members:
        count = int(counts.get(member["id"], 0))
        rows.append({
            "name": member["name"],
            "email": member["email"],
            "submissions": count,
            "status": ATTENTION_LABEL if count == 0 else "OK",
        })
    rows.sort(key=lambda item: (item["submissions"] == 0, item["name"].lower()))
    total = sum(row["submissions"] for row in rows)
    active = sum(1 for row in rows if row["submissions"] > 0)
    attention = sum(1 for row in rows if row["submissions"] == 0)
    return {
        "date": day.isoformat(),
        "rows": rows,
        "unmapped": unmapped,
        "totals": {
            "team_members": len(rows),
            "active_submitters": active,
            "attention_needed": attention,
            "submissions": total,
        },
    }


def build_whatsapp_message(report: dict) -> str:
    totals = report["totals"]
    lines = [
        f"*ATS Daily Submission Report*",
        f"Date: {report['date']}",
        "",
        f"Total submissions: *{totals['submissions']}*",
        f"Submitted by: *{totals['active_submitters']}* / {totals['team_members']}",
        f"Attention needed: *{totals['attention_needed']}*",
        "",
        "*Team Member | Submissions | Status*",
    ]
    for row in report["rows"]:
        count = row["submissions"]
        status = row["status"]
        name = row["name"]
        if count == 0:
            lines.append(f"*{name}* | *0* | {ATTENTION_LABEL}")
        else:
            lines.append(f"{name} | {count} | OK")
    if report.get("unmapped"):
        lines.extend(["", "*Unmapped submissions*"])
        for row in report["unmapped"]:
            label = row["name"]
            if row.get("email"):
                label = f"{label} ({row['email']})"
            lines.append(f"{label} | {row['submissions']}")
    return "\n".join(lines)


def send_to_webhook(message: str, args: argparse.Namespace) -> tuple[bool, str]:
    if not args.webhook_url:
        return False, "TEAM_SUBMISSION_WHATSAPP_WEBHOOK_URL is not configured."
    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    payload = {
        "message": message,
        "text": message,
        "group_id": args.group_id,
    }
    response = requests.post(args.webhook_url, headers=headers, data=json.dumps(payload), timeout=args.timeout)
    if response.status_code >= 400:
        return False, f"Webhook failed with HTTP {response.status_code}: {response.text[:500]}"
    return True, f"Webhook accepted message with HTTP {response.status_code}."


def main() -> int:
    args = parse_args()
    day = report_date(args.date, args.days_ago)
    if day.weekday() == 6 and not args.include_sunday:
        print(f"Skipping Sunday report for {day.isoformat()}.")
        return 0

    report = build_report(day)
    message = build_whatsapp_message(report)
    print(message)

    if args.send:
        ok, detail = send_to_webhook(message, args)
        print(detail, file=sys.stderr)
        return 0 if ok else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
