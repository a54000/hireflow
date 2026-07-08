#!/usr/bin/env python3
"""Daily team submission summary for WhatsApp.

Run at 19:00 IST Monday-Saturday. The script prints a WhatsApp-ready message by
default and POSTs it to TEAM_SUBMISSION_WHATSAPP_WEBHOOK_URL when --send is used.
"""

from __future__ import annotations

import argparse
import html
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


ATTENTION_LABEL = "*Attention Needed*"
ABSENT_LABEL = "*Absent*"
EXCLUDED_NAMES = {"janvi", "janvi singh", "megha", "megha singh"}


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
    parser = argparse.ArgumentParser(description="Send daily ATS submission summary to WhatsApp.")
    parser.add_argument("--date", default="", help="Report date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--days-ago", type=int, default=None, help="Relative report date. 1=yesterday, 2=day before yesterday.")
    parser.add_argument("--send", action="store_true", help="POST the message to TEAM_SUBMISSION_WHATSAPP_WEBHOOK_URL.")
    parser.add_argument("--include-sunday", action="store_true", help="Allow report generation on Sunday.")
    parser.add_argument("--webhook-url", default=os.getenv("TEAM_SUBMISSION_WHATSAPP_WEBHOOK_URL", ""))
    parser.add_argument("--group-id", default=os.getenv("TEAM_SUBMISSION_WHATSAPP_GROUP_ID", ""))
    parser.add_argument("--token", default=os.getenv("TEAM_SUBMISSION_WHATSAPP_TOKEN", ""))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("TEAM_SUBMISSION_WHATSAPP_TIMEOUT", "20")))
    parser.add_argument("--format", choices=("text", "html"), default=os.getenv("TEAM_SUBMISSION_REPORT_FORMAT", "html"))
    parser.add_argument("--output", default="", help="Optional file path to save the generated report.")
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


def normalized_name(value: object) -> str:
    return clean_text(value).lower()


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


def logged_in_members(conn, day: date, members: list[dict]) -> set[int]:
    member_by_id = {member["id"]: member for member in members}
    member_by_email = {member["email"]: member for member in members if member["email"]}
    logged_in = set()
    rows = conn.execute(
        """
        SELECT team_member_id, email
        FROM user_login_audit
        WHERE lower(trim(COALESCE(status,'')))='success'
          AND substr(COALESCE(created_at,''),1,10)=?
        GROUP BY team_member_id, email
        """,
        (day.isoformat(),),
    ).fetchall()
    for row in rows:
        team_member_id = row["team_member_id"]
        email = clean_text(row["email"]).lower()
        member = member_by_id.get(int(team_member_id)) if team_member_id else None
        if not member and email:
            member = member_by_email.get(email)
        if member:
            logged_in.add(member["id"])
    return logged_in


def build_report(day: date) -> dict:
    conn = get_db(timeout=20)
    try:
        members = active_team_members(conn)
        counts, unmapped = submission_counts(conn, day, members)
        logged_in = logged_in_members(conn, day, members)
    finally:
        conn.close()

    rows = []
    for member in members:
        count = int(counts.get(member["id"], 0))
        if count > 0:
            status = "OK"
        elif member["id"] in logged_in:
            status = ATTENTION_LABEL
        else:
            status = ABSENT_LABEL
        rows.append({
            "name": member["name"],
            "email": member["email"],
            "submissions": count,
            "status": status,
        })
    rows.sort(key=lambda item: (item["submissions"] == 0, item["status"] == ABSENT_LABEL, item["name"].lower()))
    total = sum(row["submissions"] for row in rows)
    active = sum(1 for row in rows if row["submissions"] > 0)
    attention = sum(1 for row in rows if row["status"] == ATTENTION_LABEL)
    absent = sum(1 for row in rows if row["status"] == ABSENT_LABEL)
    return {
        "date": day.isoformat(),
        "rows": rows,
        "unmapped": unmapped,
        "totals": {
            "team_members": len(rows),
            "active_submitters": active,
            "attention_needed": attention,
            "absent": absent,
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
        f"Absent: *{totals['absent']}*",
        "",
        "*Team Member | Submissions | Status*",
    ]
    for row in report["rows"]:
        count = row["submissions"]
        status = row["status"]
        name = row["name"]
        if count == 0:
            lines.append(f"*{name}* | *0* | {status}")
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


def build_html_report(report: dict) -> str:
    totals = report["totals"]
    rows = []
    for row in report["rows"]:
        absent = row["status"] == ABSENT_LABEL
        attention = row["status"] == ATTENTION_LABEL
        tr_class = "absent" if absent else ("attention" if attention else "ok")
        status = "Absent" if absent else ("Attention Needed" if attention else "OK")
        rows.append(
            "<tr class=\"{tr_class}\">"
            "<td>{name}</td>"
            "<td class=\"count\">{count}</td>"
            "<td><strong>{status}</strong></td>"
            "</tr>".format(
                tr_class=tr_class,
                name=html.escape(row["name"]),
                count=int(row["submissions"]),
                status=html.escape(status),
            )
        )

    unmapped_rows = ""
    if report.get("unmapped"):
        unmapped_items = []
        for row in report["unmapped"]:
            label = row["name"]
            if row.get("email"):
                label = f"{label} ({row['email']})"
            unmapped_items.append(
                "<tr><td>{label}</td><td class=\"count\">{count}</td></tr>".format(
                    label=html.escape(label),
                    count=int(row["submissions"]),
                )
            )
        unmapped_rows = """
        <section class="panel">
          <h2>Unmapped Submissions</h2>
          <table>
            <thead><tr><th>Name / Email</th><th>Submissions</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </section>
        """.format(rows="\n".join(unmapped_items))

    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body{{margin:0;background:#f6f7fb;color:#121827;font-family:Arial,Helvetica,sans-serif}}
    .wrap{{max-width:840px;margin:0 auto;padding:18px}}
    .title{{background:#172033;color:white;border-radius:10px 10px 0 0;padding:16px 18px}}
    .title h1{{font-size:20px;line-height:1.2;margin:0 0 4px}}
    .title p{{margin:0;color:#c9d4ef;font-size:13px}}
    .summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;background:white;padding:12px;border:1px solid #d9deea;border-top:0}}
    .metric{{border:1px solid #e2e6f0;border-radius:8px;padding:10px;background:#fbfcff}}
    .metric strong{{display:block;font-size:22px;color:#0d172a}}
    .metric span{{font-size:12px;color:#5b6578}}
    .panel{{background:white;border:1px solid #d9deea;border-radius:0 0 10px 10px;padding:12px}}
    h2{{font-size:15px;margin:4px 0 10px;color:#172033}}
    table{{width:100%;border-collapse:collapse;font-size:13px}}
    th{{text-align:left;background:#eef2f8;color:#34405a;padding:8px;border-bottom:1px solid #d5dbea}}
    td{{padding:7px 8px;border-bottom:1px solid #edf0f6;vertical-align:middle}}
    .count{{text-align:right;font-weight:700}}
    tr.attention td{{background:#fff1f1;color:#7f1d1d}}
    tr.absent td{{background:#fff7ed;color:#7c2d12}}
    tr.ok td{{background:#ffffff}}
    @media(max-width:640px){{
      .wrap{{padding:8px}}
      .summary{{grid-template-columns:1fr}}
      table{{font-size:12px}}
      th,td{{padding:6px}}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="title">
      <h1>ATS Daily Submission Report</h1>
      <p>Date: {date}</p>
    </div>
    <div class="summary">
      <div class="metric"><strong>{submissions}</strong><span>Total submissions</span></div>
      <div class="metric"><strong>{active_submitters}/{team_members}</strong><span>Submitted by</span></div>
      <div class="metric"><strong>{attention_needed}</strong><span>Attention needed</span></div>
      <div class="metric"><strong>{absent}</strong><span>Absent</span></div>
    </div>
    <section class="panel">
      <h2>Team Submission Status</h2>
      <table>
        <thead><tr><th>Team Member</th><th>Submissions</th><th>Status</th></tr></thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </section>
    {unmapped_rows}
  </div>
</body>
</html>
""".format(
        date=html.escape(report["date"]),
        submissions=int(totals["submissions"]),
        active_submitters=int(totals["active_submitters"]),
        team_members=int(totals["team_members"]),
        attention_needed=int(totals["attention_needed"]),
        absent=int(totals["absent"]),
        rows="\n".join(rows),
        unmapped_rows=unmapped_rows,
    )


def main() -> int:
    load_env_file()
    args = parse_args()
    day = report_date(args.date, args.days_ago)
    if day.weekday() == 6 and not args.include_sunday:
        print(f"Skipping Sunday report for {day.isoformat()}.")
        return 0

    report = build_report(day)
    message = build_whatsapp_message(report)
    html_message = build_html_report(report)
    output = html_message if args.format == "html" else message

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(output)

    if args.send:
        ok, detail = send_to_webhook(message, args, html_message if args.format == "html" else "")
        print(detail, file=sys.stderr)
        return 0 if ok else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
