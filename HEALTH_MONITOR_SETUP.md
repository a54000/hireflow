# HR Guru ATS Health Monitor

This monitor checks the ATS from outside Flask, records incidents, emails logs, and can restart the app service once per cooldown window.

## Files

- `app.py`
  - `/healthz` now returns JSON and checks PostgreSQL.
- `scripts/monitor_health.py`
  - Checks public and local health URLs.
  - Saves incidents to local SQLite: `instance/health_monitor.db`.
  - Also writes incidents to PostgreSQL table `health_incidents` when `DATABASE_URL` is configured.
  - Emails a redacted incident bundle.
  - Restarts `hrguru-ats.service` at most once per cooldown window.

## Required Environment

Set these in `/etc/systemd/system/hrguru-ats.service`, `/home/ubuntu/hrguru-ats/.env`, or the monitor service environment:

```bash
DATABASE_URL=postgresql://hrguru:xxxxx@127.0.0.1:5432/hrguru_ats
GMAIL_USER=your-central-sender@gmail.com
GMAIL_APP_PASS=your-gmail-app-password
HEALTH_ALERT_EMAILS=your-email@example.com
ATS_SERVICE_NAME=hrguru-ats.service
ATS_PUBLIC_HEALTH_URL=https://ats.hrgp.in/healthz
ATS_LOCAL_HEALTH_URL=http://127.0.0.1:5001/healthz
ATS_HEALTH_AUTO_RESTART=1
ATS_RESTART_COOLDOWN_MINUTES=15
ATS_ALERT_EMAIL_COOLDOWN_MINUTES=15
ATS_ACTION_WAIT_SECONDS=120
ATS_SIGNAL_WINDOW_MINUTES=5
ATS_QUEUE_ALERT_THRESHOLD=20
ATS_QUEUE_RESTART_THRESHOLD=20
ATS_STUCK_ALERT_SECONDS=120
ATS_STUCK_RESTART_SECONDS=120
```

## Manual Test

```bash
cd /home/ubuntu/hrguru-ats
/home/ubuntu/hrguru-ats/venv/bin/python scripts/monitor_health.py --no-restart
```

Expected healthy output:

```text
OK public=200 ...ms local=200 ...ms
```

## Cron Setup

Run every 2 minutes:

```bash
crontab -e
```

Add:

```cron
*/2 * * * * cd /home/ubuntu/hrguru-ats && /home/ubuntu/hrguru-ats/venv/bin/python scripts/monitor_health.py >> /home/ubuntu/hrguru-ats/instance/health_monitor.log 2>&1
```

## Check Incident History

Local fallback DB:

```bash
sqlite3 /home/ubuntu/hrguru-ats/instance/health_monitor.db "select id,created_at,severity,status,summary from health_incidents order by id desc limit 10;"
```

PostgreSQL:

```bash
psql "$DATABASE_URL" -c "select id,created_at,severity,status,summary from health_incidents order by id desc limit 10;"
```

## Safety Rules

- The monitor restarts the app only once per cooldown window.
- For log-based degradation, the monitor emails first, waits `ATS_ACTION_WAIT_SECONDS`, rechecks, and restarts only if the problem is still present.
- It captures logs before restart.
- It does not edit code.
- It redacts OAuth codes, tokens, passwords, and database passwords from email/log bundles.
