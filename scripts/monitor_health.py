#!/usr/bin/env python3
"""
External health monitor for HR Guru ATS.

Intended EC2 usage:
  /home/ubuntu/hrguru-ats/venv/bin/python /home/ubuntu/hrguru-ats/scripts/monitor_health.py

Run from cron/systemd timer every 1-2 minutes. The script checks the public and
local health endpoints, records incidents, emails a compact log bundle, and can
restart the app service once per cooldown window.
"""

import argparse
import json
import os
import re
import smtplib
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path

try:
    import psycopg2
except Exception:
    psycopg2 = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_DB = ROOT / "instance" / "health_monitor.db"


def load_dotenv(path):
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv(ROOT / ".env")


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def redact(text):
    text = str(text or "")
    patterns = [
        (r"code=[^&\s]+", "code=[redacted]"),
        (r"state=[^&\s]+", "state=[redacted]"),
        (r"access_token['\"]?\s*[:=]\s*['\"]?[^,'\"\s]+", "access_token=[redacted]"),
        (r"refresh_token['\"]?\s*[:=]\s*['\"]?[^,'\"\s]+", "refresh_token=[redacted]"),
        (r"password\s*[:=]\s*[^,\s]+", "password=[redacted]"),
        (r"postgresql://([^:]+):([^@]+)@", r"postgresql://\1:[redacted]@"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return text


def run_cmd(command, timeout=12):
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
        return completed.returncode, redact(completed.stdout)
    except Exception as exc:
        return 999, f"{type(exc).__name__}: {exc}"


def check_url(url, timeout):
    started = time.perf_counter()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hrguru-health-monitor/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            return {
                "url": url,
                "ok": 200 <= response.status < 300,
                "status_code": response.status,
                "elapsed_ms": elapsed_ms,
                "body": redact(body[:1000]),
                "error": "",
            }
    except urllib.error.HTTPError as exc:
        body = exc.read(2048).decode("utf-8", errors="replace") if exc.fp else ""
        return {
            "url": url,
            "ok": False,
            "status_code": exc.code,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "body": redact(body[:1000]),
            "error": f"HTTPError: {exc}",
        }
    except Exception as exc:
        return {
            "url": url,
            "ok": False,
            "status_code": 0,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            "body": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def get_journal_lines(lines=160, since_minutes=None):
    command = ["journalctl", "-u", os.getenv("ATS_SERVICE_NAME", "hrguru-ats.service")]
    if since_minutes:
        command.extend(["--since", f"{int(since_minutes)} minutes ago"])
    else:
        command.extend(["-n", str(lines)])
    command.append("--no-pager")
    code, output = run_cmd(command, timeout=15)
    return output[-30000:]


def parse_journal_signals(journal):
    queue_depths = [int(value) for value in re.findall(r"Task queue depth is\s+(\d+)", journal)]
    stuck = []
    for match in re.finditer(
        r"PERF inflight_stuck age_s=([0-9.]+)\s+method=(\S+)\s+path=(.*?)\s+endpoint=(\S+)\s+user=(.*?)\s+active=(\d+)",
        journal,
    ):
        stuck.append({
            "age_s": float(match.group(1)),
            "method": match.group(2),
            "path": match.group(3),
            "endpoint": match.group(4),
            "user": match.group(5).strip(),
            "active": int(match.group(6)),
        })
    slow_active = []
    for match in re.finditer(
        r"PERF slow_request method=(\S+)\s+path=(.*?)\s+endpoint=(\S+)\s+status=(\d+)\s+elapsed_ms=([0-9.]+)\s+active_at_start=(\d+)\s+user=(.*)",
        journal,
    ):
        elapsed_ms = float(match.group(5))
        active_at_start = int(match.group(6))
        if active_at_start >= int(os.getenv("ATS_ACTIVE_WARN_THRESHOLD", "10")) or elapsed_ms >= float(os.getenv("ATS_SLOW_WARN_MS", "5000")):
            slow_active.append({
                "method": match.group(1),
                "path": match.group(2),
                "endpoint": match.group(3),
                "status": int(match.group(4)),
                "elapsed_ms": elapsed_ms,
                "active_at_start": active_at_start,
                "user": match.group(7).strip(),
            })

    max_queue = max(queue_depths) if queue_depths else 0
    max_stuck_age = max((item["age_s"] for item in stuck), default=0)
    restart_reasons = []
    alert_reasons = []

    queue_restart = int(os.getenv("ATS_QUEUE_RESTART_THRESHOLD", "20"))
    queue_alert = int(os.getenv("ATS_QUEUE_ALERT_THRESHOLD", "20"))
    stuck_restart = float(os.getenv("ATS_STUCK_RESTART_SECONDS", "120"))
    stuck_alert = float(os.getenv("ATS_STUCK_ALERT_SECONDS", "120"))
    slow_active_alert_count = int(os.getenv("ATS_SLOW_ACTIVE_ALERT_COUNT", "5"))

    if max_queue >= queue_restart:
        restart_reasons.append(f"waitress queue depth reached {max_queue}")
    elif max_queue >= queue_alert:
        alert_reasons.append(f"waitress queue depth reached {max_queue}")

    if max_stuck_age >= stuck_restart:
        worst = max(stuck, key=lambda item: item["age_s"])
        restart_reasons.append(f"inflight request stuck for {max_stuck_age:.1f}s: {worst['method']} {worst['path']}")
    elif max_stuck_age >= stuck_alert:
        worst = max(stuck, key=lambda item: item["age_s"])
        alert_reasons.append(f"inflight request stuck for {max_stuck_age:.1f}s: {worst['method']} {worst['path']}")

    if len(slow_active) >= slow_active_alert_count:
        alert_reasons.append(f"{len(slow_active)} slow/high-concurrency requests in recent journal")

    return {
        "max_queue_depth": max_queue,
        "queue_warning_count": len(queue_depths),
        "stuck_requests": stuck[-10:],
        "max_stuck_age_s": max_stuck_age,
        "slow_active_requests": slow_active[-10:],
        "restart_reasons": restart_reasons,
        "alert_reasons": alert_reasons,
        "needs_alert": bool(alert_reasons or restart_reasons),
        "needs_restart": bool(restart_reasons),
    }


def get_service_status():
    service = os.getenv("ATS_SERVICE_NAME", "hrguru-ats.service")
    code, output = run_cmd(["systemctl", "is-active", service], timeout=8)
    return output.strip() or f"unknown rc={code}"


def restart_service():
    service = os.getenv("ATS_SERVICE_NAME", "hrguru-ats.service")
    code, output = run_cmd(["systemctl", "restart", service], timeout=30)
    time.sleep(3)
    return code, output


def sqlite_state_conn(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS monitor_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS health_incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            severity TEXT,
            status TEXT,
            summary TEXT,
            public_status_code INTEGER,
            local_status_code INTEGER,
            public_elapsed_ms REAL,
            local_elapsed_ms REAL,
            auto_restart_attempted INTEGER DEFAULT 0,
            auto_restart_success INTEGER DEFAULT 0,
            email_sent INTEGER DEFAULT 0,
            details_json TEXT,
            journal_excerpt TEXT
        )
        """
    )
    conn.commit()
    return conn


def get_state(conn, key):
    row = conn.execute("SELECT value FROM monitor_state WHERE key=?", (key,)).fetchone()
    return row[0] if row else ""


def set_state(conn, key, value):
    conn.execute(
        "INSERT OR REPLACE INTO monitor_state(key,value) VALUES (?,?)",
        (key, str(value)),
    )
    conn.commit()


def should_attempt_restart(conn, cooldown_minutes):
    raw = get_state(conn, "last_restart_at")
    if not raw:
        return True
    try:
        last = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return True
    return datetime.now() - last >= timedelta(minutes=cooldown_minutes)


def cooldown_elapsed(conn, key, cooldown_minutes):
    raw = get_state(conn, key)
    if not raw:
        return True
    try:
        last = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return True
    return datetime.now() - last >= timedelta(minutes=cooldown_minutes)


def incident_db_conn():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url.startswith(("postgres://", "postgresql://")) and psycopg2:
        conn = psycopg2.connect(database_url, connect_timeout=3)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS health_incidents (
                id SERIAL PRIMARY KEY,
                created_at TEXT,
                severity TEXT,
                status TEXT,
                summary TEXT,
                public_status_code INTEGER,
                local_status_code INTEGER,
                public_elapsed_ms REAL,
                local_elapsed_ms REAL,
                auto_restart_attempted INTEGER DEFAULT 0,
                auto_restart_success INTEGER DEFAULT 0,
                email_sent INTEGER DEFAULT 0,
                details_json TEXT,
                journal_excerpt TEXT
            )
            """
        )
        return conn
    return None


def insert_incident(local_state, incident):
    local_state.execute(
        """
        INSERT INTO health_incidents
            (created_at,severity,status,summary,public_status_code,local_status_code,
             public_elapsed_ms,local_elapsed_ms,auto_restart_attempted,auto_restart_success,
             email_sent,details_json,journal_excerpt)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            incident["created_at"],
            incident["severity"],
            incident["status"],
            incident["summary"],
            incident["public"].get("status_code", 0),
            incident["local"].get("status_code", 0),
            incident["public"].get("elapsed_ms", 0),
            incident["local"].get("elapsed_ms", 0),
            1 if incident.get("auto_restart_attempted") else 0,
            1 if incident.get("auto_restart_success") else 0,
            1 if incident.get("email_sent") else 0,
            json.dumps(incident.get("details", {}), ensure_ascii=False),
            incident.get("journal_excerpt", ""),
        ),
    )
    local_state.commit()

    pg = None
    try:
        pg = incident_db_conn()
        if not pg:
            return
        cur = pg.cursor()
        cur.execute(
            """
            INSERT INTO health_incidents
                (created_at,severity,status,summary,public_status_code,local_status_code,
                 public_elapsed_ms,local_elapsed_ms,auto_restart_attempted,auto_restart_success,
                 email_sent,details_json,journal_excerpt)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                incident["created_at"],
                incident["severity"],
                incident["status"],
                incident["summary"],
                incident["public"].get("status_code", 0),
                incident["local"].get("status_code", 0),
                incident["public"].get("elapsed_ms", 0),
                incident["local"].get("elapsed_ms", 0),
                1 if incident.get("auto_restart_attempted") else 0,
                1 if incident.get("auto_restart_success") else 0,
                1 if incident.get("email_sent") else 0,
                json.dumps(incident.get("details", {}), ensure_ascii=False),
                incident.get("journal_excerpt", ""),
            ),
        )
    except Exception as exc:
        print(f"Unable to write incident to PostgreSQL: {type(exc).__name__}: {exc}", file=sys.stderr)
    finally:
        try:
            if pg:
                pg.close()
        except Exception:
            pass


def send_email(subject, body):
    gmail_user = os.getenv("GMAIL_USER", "")
    gmail_pass = os.getenv("GMAIL_APP_PASS", "")
    recipients = os.getenv("HEALTH_ALERT_EMAILS") or os.getenv("ADMIN_EMAIL", "")
    recipients = [item.strip() for item in re.split(r"[,;]", recipients) if item.strip()]
    if not gmail_user or not gmail_pass or not recipients:
        return False, "Email is not configured. Set GMAIL_USER, GMAIL_APP_PASS, and HEALTH_ALERT_EMAILS or ADMIN_EMAIL."
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = ", ".join(recipients)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
        smtp.login(gmail_user, gmail_pass)
        smtp.sendmail(gmail_user, recipients, msg.as_string())
    return True, f"sent to {', '.join(recipients)}"


def build_email_body(incident):
    return redact(
        f"""HR Guru ATS Health Incident

Time: {incident['created_at']}
Severity: {incident['severity']}
Status: {incident['status']}
Summary: {incident['summary']}

Public check:
  URL: {incident['public']['url']}
  OK: {incident['public']['ok']}
  Status: {incident['public']['status_code']}
  Elapsed ms: {incident['public']['elapsed_ms']}
  Error: {incident['public'].get('error') or '-'}

Local check:
  URL: {incident['local']['url']}
  OK: {incident['local']['ok']}
  Status: {incident['local']['status_code']}
  Elapsed ms: {incident['local']['elapsed_ms']}
  Error: {incident['local'].get('error') or '-'}

Service status before action: {incident['details'].get('service_status_before')}
Action wait seconds: {incident['details'].get('action_wait_seconds')}
Auto restart attempted: {incident.get('auto_restart_attempted')}
Auto restart success: {incident.get('auto_restart_success')}
Service status after action: {incident['details'].get('service_status_after')}

Log signals:
{json.dumps(incident['details'].get('journal_signals', {}), indent=2)}

Codex-ready prompt:
The HR Guru ATS production app became unhealthy. Please diagnose from this incident summary and journal excerpt. Recommend a safe fix first, and avoid production code changes unless clearly required.

Recent journal excerpt:
{incident.get('journal_excerpt') or '-'}
"""
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-url", default=os.getenv("ATS_PUBLIC_HEALTH_URL", "https://ats.hrgp.in/healthz"))
    parser.add_argument("--local-url", default=os.getenv("ATS_LOCAL_HEALTH_URL", "http://127.0.0.1:5001/healthz"))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("ATS_HEALTH_TIMEOUT_SECONDS", "8")))
    parser.add_argument("--restart", action="store_true", default=os.getenv("ATS_HEALTH_AUTO_RESTART", "1").lower() in {"1", "true", "yes"})
    parser.add_argument("--no-restart", action="store_true", help="Disable automatic restart for this run.")
    parser.add_argument("--restart-cooldown-minutes", type=int, default=int(os.getenv("ATS_RESTART_COOLDOWN_MINUTES", "15")))
    parser.add_argument("--email-cooldown-minutes", type=int, default=int(os.getenv("ATS_ALERT_EMAIL_COOLDOWN_MINUTES", "15")))
    parser.add_argument("--action-wait-seconds", type=int, default=int(os.getenv("ATS_ACTION_WAIT_SECONDS", "120")))
    parser.add_argument("--state-db", default=os.getenv("ATS_HEALTH_STATE_DB", str(DEFAULT_STATE_DB)))
    parser.add_argument("--journal-lines", type=int, default=int(os.getenv("ATS_HEALTH_JOURNAL_LINES", "180")))
    parser.add_argument("--signal-window-minutes", type=int, default=int(os.getenv("ATS_SIGNAL_WINDOW_MINUTES", "5")))
    args = parser.parse_args()

    state = sqlite_state_conn(Path(args.state_db))
    public = check_url(args.public_url, args.timeout)
    local = check_url(args.local_url, args.timeout)
    healthy = public["ok"] and local["ok"]
    signal_journal = get_journal_lines(args.journal_lines, since_minutes=args.signal_window_minutes)
    journal = get_journal_lines(args.journal_lines)
    signals = parse_journal_signals(signal_journal)

    if healthy and not signals["needs_alert"]:
        set_state(state, "last_healthy_at", now_text())
        print(f"OK public={public['status_code']} {public['elapsed_ms']}ms local={local['status_code']} {local['elapsed_ms']}ms")
        return 0

    service_before = get_service_status()
    restart_attempted = False
    restart_success = False
    restart_output = ""
    restart_enabled = args.restart and not args.no_restart
    restart_needed = (not healthy) or signals["needs_restart"]

    if not healthy:
        summary = f"ATS unhealthy: public={public['status_code']} local={local['status_code']}"
    else:
        reasons = signals["restart_reasons"] or signals["alert_reasons"]
        summary = "ATS degraded: " + "; ".join(reasons[:3])

    incident = {
        "created_at": now_text(),
        "severity": "Critical" if restart_needed else "Watch",
        "status": "pending_action" if restart_needed and restart_enabled else "open",
        "summary": summary,
        "public": public,
        "local": local,
        "auto_restart_attempted": False,
        "auto_restart_success": False,
        "email_sent": False,
        "details": {
            "service_status_before": service_before,
            "service_status_after": service_before,
            "restart_output": "",
            "after_public": public,
            "after_local": local,
            "journal_signals": signals,
            "signal_window_minutes": args.signal_window_minutes,
            "action_wait_seconds": args.action_wait_seconds if restart_needed and restart_enabled else 0,
        },
        "journal_excerpt": journal,
    }

    email_allowed = cooldown_elapsed(state, "last_email_at", args.email_cooldown_minutes)
    if email_allowed:
        try:
            ok, email_msg = send_email(
                f"[ATS] Health incident - {incident['status']} - {incident['severity']}",
                build_email_body(incident),
            )
            incident["email_sent"] = ok
            incident["details"]["email_result"] = email_msg
            set_state(state, "last_email_at", now_text())
        except Exception as exc:
            incident["details"]["email_result"] = f"{type(exc).__name__}: {exc}"

    if restart_enabled and restart_needed and should_attempt_restart(state, args.restart_cooldown_minutes):
        if args.action_wait_seconds > 0:
            time.sleep(args.action_wait_seconds)
        recheck_public = check_url(args.public_url, args.timeout)
        recheck_local = check_url(args.local_url, args.timeout)
        recheck_journal = get_journal_lines(args.journal_lines, since_minutes=args.signal_window_minutes)
        recheck_signals = parse_journal_signals(recheck_journal)
        still_needs_restart = (not (recheck_public["ok"] and recheck_local["ok"])) or recheck_signals["needs_restart"]
        incident["details"]["recheck_public"] = recheck_public
        incident["details"]["recheck_local"] = recheck_local
        incident["details"]["recheck_journal_signals"] = recheck_signals
        if still_needs_restart:
            restart_attempted = True
            set_state(state, "last_restart_at", now_text())
            rc, restart_output = restart_service()
            after_local = check_url(args.local_url, args.timeout)
            after_public = check_url(args.public_url, args.timeout)
            restart_success = rc == 0 and after_local["ok"] and after_public["ok"]
        else:
            after_local = recheck_local
            after_public = recheck_public
            incident["status"] = "recovered_without_restart"
    else:
        after_local = local
        after_public = public

    service_after = get_service_status()
    if restart_attempted:
        summary += f"; auto_restart_success={restart_success}"
    incident["summary"] = summary
    if restart_attempted:
        incident["status"] = "recovered" if restart_success else "open"
    elif incident["status"] == "pending_action":
        incident["status"] = "open"
    incident["auto_restart_attempted"] = restart_attempted
    incident["auto_restart_success"] = restart_success
    incident["details"]["service_status_after"] = service_after
    incident["details"]["restart_output"] = restart_output[-4000:]
    incident["details"]["after_public"] = after_public
    incident["details"]["after_local"] = after_local

    insert_incident(state, incident)
    print(summary)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
