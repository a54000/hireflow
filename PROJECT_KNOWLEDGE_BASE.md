# HR Guru ATS Knowledge Base

Last updated: 2026-06-10

This document is meant for two use cases:

1. Rebuild the HR Guru ATS from scratch if the codebase is unavailable.
2. Help a future engineer or Codex session debug, modify, or deploy the existing app without needing the original development conversation.

## 1. Product Overview

HR Guru ATS is a recruiting workflow application used by HR Guru Placement Services. It is optimized for recruiter productivity, bulk candidate upload, requirement management, candidate tracking, daily reporting, and admin oversight.

The most frequently used recruiter workflows are:

- Bulk Upload candidates with CV files and JD files.
- Add Requirement.
- Add Candidate.
- Candidate List and status updates.
- Daily Reports.
- My Follow-ups.
- Client mapping self-service.

Admin workflows include:

- User and access management.
- Team leader mapping.
- Candidate Follow-up Queue.
- Client SLA Dashboard.
- Data Quality Console.
- Team Analytics.
- Recruiter reports.
- Taggd Recruiter setup.
- Impersonify User.

External client users have a restricted single-page candidate view where they can see candidates mapped to their client and update candidate status.

## 2. Current Production Setup

Production URL:

```text
https://ats.hrgp.in
```

Previous/local tunnel URL:

```text
https://hireflow.hrgp.in
```

Hosting:

```text
AWS EC2 micro instance
Ubuntu
Nginx
Waitress
Flask
PostgreSQL on same EC2
Cloudflare DNS/proxy
```

Request path:

```text
Browser
-> Cloudflare
-> EC2 public IP
-> Nginx HTTPS
-> Waitress on 127.0.0.1:5001
-> Flask app.py
-> PostgreSQL hrguru_ats
```

Systemd service:

```text
/etc/systemd/system/hrguru-ats.service
```

Typical service command:

```text
waitress-serve --host=127.0.0.1 --port=5001 --threads=18 app:app
```

Important service environment variables:

```text
DATABASE_URL=postgresql://hrguru:<password>@127.0.0.1:5432/hrguru_ats
PUBLIC_BASE_URL=https://ats.hrgp.in
GOOGLE_REDIRECT_URI=https://ats.hrgp.in/login/callback
PREFERRED_URL_SCHEME=https
GOOGLE_CLIENT_ID=<active OAuth client ID>
GOOGLE_CLIENT_SECRET=<active OAuth client secret>
GOOGLE_OAUTH_SCOPE=openid email profile
GMAIL_USER=<central sender email>
GMAIL_APP_PASS=<central sender app password>
```

Nginx active site:

```text
/etc/nginx/sites-available/hrguru-ats
/etc/nginx/sites-enabled/hrguru-ats
```

Expected Nginx shape:

```nginx
server {
    listen 80;
    server_name ats.hrgp.in;

    client_max_body_size 100M;

    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name ats.hrgp.in;

    client_max_body_size 100M;

    ssl_certificate /etc/letsencrypt/live/ats.hrgp.in/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ats.hrgp.in/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

Important warning:

Do not place this line inside the HTTPS `listen 443 ssl` block:

```nginx
return 301 https://$host$request_uri;
```

That creates an infinite redirect loop.

## 3. Repository Layout

The original development workspace was:

```text
D:\hrguru-ats
```

The PostgreSQL-compatible merged deployment copy was:

```text
D:\hireflow_app
```

Important files and folders:

```text
app.py                                  Main Flask monolith
templates/                             HTML templates
static/                                Static JS/CSS/assets
uploads/                               Uploaded CV/JD/invoice files
scripts/migrate_sqlite_to_postgres.py  SQLite to PostgreSQL migration script
requirements.txt                       Python dependencies
.env                                   Local environment config
ats.db                                 Legacy SQLite database
```

Important deployable files after PostgreSQL migration:

```text
D:\hireflow_app\app.py
D:\hireflow_app\templates\*.html
D:\hireflow_app\scripts\migrate_sqlite_to_postgres.py
```

Do not blindly overwrite production `app.py` with an older SQLite-only version. The production-ready file must contain:

```text
DATABASE_URL
USE_POSTGRES
PgConnectionAdapter
psycopg2
translate_sql_for_postgres
```

## 4. Tech Stack

Backend:

```text
Python
Flask
Waitress
PostgreSQL
SQLite legacy/local support
psycopg2-binary
openpyxl
Werkzeug password hashing
Authlib OAuth client
Google APIs client libraries
```

Frontend:

```text
Server-rendered HTML templates
Vanilla JavaScript
Fetch API
CSS embedded in lightweight standalone templates
No frontend build step required
```

Infrastructure:

```text
AWS EC2
Ubuntu
Nginx reverse proxy
Certbot SSL certificate
Cloudflare DNS/proxy
systemd service
```

Email:

```text
Central Gmail/Google Workspace SMTP account using GMAIL_USER and GMAIL_APP_PASS
Reply-To header set to logged-in recruiter email
```

Google OAuth:

```text
Used only as optional login identity
Scope should be limited to: openid email profile
Avoid gmail.send, drive.readonly, spreadsheets.readonly in normal login scope
```

## 5. Authentication And User Types

Supported login modes:

- Username/password login.
- Optional Google OAuth login.

Primary production recommendation:

```text
Username/password for all normal users.
Google OAuth as optional alternate login only.
Central SMTP for email sending.
```

User categories:

### Admin

Admin has full access to:

- User Management.
- Access Management.
- Team Leader Mapping.
- Candidate Follow-up Queue.
- Client SLA Dashboard.
- Data Quality Console.
- Team Analytics.
- Reports.
- Impersonify User.
- Full Admin workspace.

### Recruiter

Recruiters use lightweight pages only. They should not load the old full `index.html` shell for routine work.

Recruiter actions:

- Add Requirement.
- Bulk Upload, if permitted.
- Add Candidate.
- Candidate List.
- Requirement List.
- Candidate Search.
- Daily Reports.
- My Follow-ups.
- My Clients Mapping.
- Weekly Performance.
- Daily Performance Summary.

Bulk upload is controlled by:

```text
team_members.can_bulk_upload
app_users.is_bulk_admin
role == Bulk Admin
```

### Team Leader

Team Leader has visibility over mapped team members only.

Team Leader access is controlled through:

```text
team_leader_mappings
```

Team Leader can use:

- Team Analytics.
- Recruiter Requirement-wise Report.
- Team Selection Report.
- Candidate/requirement views scoped to their team.
- Taggd Recruiter setup if allowed.

### External Client / Client Viewer

Client viewer has restricted access.

They should only see candidate records mapped to their client and can update candidate status where permitted.

Client mapping is controlled through:

```text
team_client_mappings
clients
```

Client viewer should be redirected to:

```text
/client/candidates
```

## 6. Important Pages And Routes

Lightweight page routes:

```text
/                         Dashboard route; admin gets admin_landing, non-admin gets recruiter_landing
/admin                    Admin dashboard
/admin/users              User and Access Management
/admin/team               Team setup / access management
/admin/reports            Admin reports
/admin/impersonify        Switch profile / impersonify user
/admin/team-leader-mapping
/admin/followups          Candidate Follow-up Queue
/admin/client-sla         Client SLA Dashboard
/admin/data-quality       Data Quality Console
/add-candidate            Standalone Add Candidate page
/add-requirement          Standalone Add Requirement page
/daily-reports            Standalone Daily Reports page
/weekly-performance       Opens recruiter landing with weekly performance
/my-followups             Recruiter follow-up queue
/team-reports
/team-selection-report
/team-analytics
/candidate-search
/power-search
/ai-screening
/candidates               Lightweight candidate list
/requirements             Lightweight requirement list
/taggd-recruiters
/upload                   Bulk upload page
/bulk-upload-guide
/profile
/client/candidates
```

Legacy heavy shell route:

```text
/admin/workspace
```

The old heavy ATS shell renders:

```text
templates/index.html
```

Avoid sending recruiters or common admin workflows to `index.html` unless absolutely needed.

## 7. UI/UX Design Principles

Performance-first UI decisions:

- Do not auto-load graphs or summary-heavy APIs on dashboard unless required.
- Use lightweight standalone pages instead of loading full `index.html`.
- Fetch heavy data only when the user clicks `Load`, `Run Check`, or opens the relevant page.
- Dashboard tiles should be navigation only, not hidden heavy data loaders.
- Avoid loading candidate lists with all records. First page should load limited rows, typically 15.
- Daily Reports should default to today only.

Visual direction:

- Dark, work-focused operational UI.
- Compact but readable.
- Avoid tiny admin font sizes. Important dashboard text should be readable at normal desktop scale.
- Cards should be functional tiles, not nested decorative cards.
- Use consistent tile colors by intent.
- Avoid one-note palettes.
- Keep buttons and links clearly aligned.
- Use loading/pressed states on buttons and tiles.
- Keep profile/sign-out in top-right profile menu rather than as dashboard tiles.

Current dashboard structure:

Admin dashboard:

- Snapshot at top.
- Admin Actions below snapshot.
- Insights below Admin Actions.
- Right sidebar for Create & Review and Shortcuts.
- Profile menu top right.

Recruiter dashboard:

- Workflow-based action tiles.
- No heavy graphs by default.
- Daily/weekly performance available on demand.
- My Clients Mapping tile for client mapping self-service.

## 8. Core Business Rules

### Requirements

Requirement records represent client jobs/open positions.

Important fields:

```text
title
client_name
status
taggd_recruiter_id
taggd_recruiter_name
jd_filename
jd_url
created_at
updated_at
```

Add Requirement requires Taggd Recruiter once the Taggd workflow is enabled.

Taggd Recruiter:

- Admin or Team Leader can create/manage Taggd recruiters.
- Taggd recruiters are mapped to clients.
- Recruiters can only see Taggd recruiter names mapped to clients they can access.
- Requirement reports should show Taggd Recruiter.

### Candidates

Candidate records are mapped to requirements.

Important fields:

```text
candidate_name
email_addr
phone
current_company
current_role
experience_years
key_skills
notice_period
current_salary
expected_salary
current_location
preferred_location
status
requirement_id
recruiter_name
recruiter_email
sourcer_id
cv_filename
cv_url
cv_public_id
created_at
updated_at
is_duplicate
candidate_feedback
```

Candidate list should be lightweight and paginated/limited.

Recruiters should see their own candidates. Team leaders should see their mapped team’s candidates. Admin sees all.

Status list should be synced with database/master status list. Do not rely only on hardcoded status arrays.

Important candidate statuses include:

```text
New
Screening Pending
Feedback Pending
Duplicate
Selected
Offered
Joined
Dropped
Rejected
HM Rejected
Screen Rejected
L1 Reject
```

### Bulk Upload

Bulk upload is one of the highest-value workflows.

Rules:

- User must have bulk upload permission.
- User uploads JD file(s), candidate spreadsheet, and CV files.
- Bulk upload must map every spreadsheet row to an existing requirement.
- Auto-creation of requirements from bulk upload is disabled.
- If a requirement is missing, upload should fail clearly and explain why.
- JD file names may be attached to matched requirements, but candidate rows must map by spreadsheet Requirement column to an existing requirement.
- CV files are matched by candidate email, phone, or candidate name.
- If no rows are found, the spreadsheet likely lacks a proper header row or data rows.
- Upload template may need update whenever mandatory requirement/candidate fields change.

Nginx must allow larger uploads:

```nginx
client_max_body_size 100M;
```

If users get:

```text
413 Request Entity Too Large
```

increase `client_max_body_size` in Nginx and reload Nginx.

### Daily Reports

Daily Reporting should default to today.

Email should include:

- Candidate details.
- Current Company.
- Current Designation.
- CV attachments where required.
- Signature with recruiter first and last name, not username slug.

Daily report modal should stay stable and re-open correctly.

Recipient name field was replaced by another CC email field in one UX update.

### Email Rules

Current recommended email behavior:

```text
From: central sender configured in GMAIL_USER
Reply-To: logged-in recruiter's email
```

This allows username/password users to send email without Google OAuth Gmail scope.

Google login should not request Gmail send scope in normal login.

If SMTP is not configured, email APIs should return:

```text
Email is not configured. Please set GMAIL_USER and GMAIL_APP_PASS.
```

### Follow-up Queue

Purpose:

Show candidate records requiring recruiter action.

Initial behavior:

- Alert users once daily on first login if follow-ups exist.
- Later this may become a login restriction.

Recruiter follow-up page:

- Should not check CV attached.
- Should not show Requirement Actions.
- Should be compact.
- Rows should not need an Open/Update button if status can be changed directly.

Admin Candidate Follow-up Queue:

```text
/admin/followups
/api/admin/candidate-followups
```

Recruiter My Follow-ups:

```text
/my-followups
/api/my/followups
/api/my/followups/today
```

### Client SLA Dashboard

Purpose:

Show client-side bottlenecks and response delays.

Default thresholds:

```text
Feedback pending: 2 days
No recent submission: 3 days
Requirement aging: 7 days
Critical aging: 14 days
```

Useful columns:

```text
Client
Active requirements
Pending feedback
Oldest pending feedback age
No-submission requirements
Current month selections
Risk level
Risk reasons
```

Risk rules:

Healthy:

```text
pending feedback <= 2 and no stale requirements
```

Watch:

```text
feedback pending > 2
or no submissions in 3 days
```

Critical:

```text
feedback pending > 5
or requirement open > 14 days without movement
```

### Data Quality Console

Admin-only, standalone, on-demand.

Purpose:

Identify data that will break reporting, SLA, follow-ups, or recruiter workflows.

Checks include:

- Candidate statuses not in master list.
- Candidates missing valid requirement mapping.
- Candidates missing email and phone.
- Possible duplicate candidate identities.
- Active requirements missing client.
- Active requirements missing Taggd recruiter.
- Active requirements not updated for 14+ days.

CV checks were removed from My Follow-ups, but Data Quality may still check missing CVs if desired.

### Team Analytics

Used by Admin and Team Leaders.

Should be on-demand only.

Concurrency guard:

```text
ANALYTICS_SEMAPHORE = threading.BoundedSemaphore(3)
```

If more than 3 concurrent users hit analytics, show a clear busy message.

Team Analytics should include:

- Last 14 days submissions.
- Current month submissions heatmap.
- Weekly recruiter contribution.
- Top 3 this week.
- Bottom 3 this week.
- Names and numbers visible.

## 9. PostgreSQL Migration

Migration script:

```text
scripts/migrate_sqlite_to_postgres.py
```

Run with:

```bash
export DATABASE_URL="postgresql://hrguru:<password>@127.0.0.1:5432/hrguru_ats"
python scripts/migrate_sqlite_to_postgres.py --drop-existing
```

Important migration behavior:

- Reads SQLite DB.
- Creates/copies PostgreSQL tables.
- Preserves row counts.
- Resets sequences.
- Validates table counts.

Known migrated count from one successful migration:

```text
candidates: 3622
requirements: 409
team_members: 45
taggd_recruiters: 36
team_client_mappings: 121
```

For end-of-day cutover from SQLite to PostgreSQL:

1. Stop the live SQLite app so no writes continue.
2. Backup SQLite DB.
3. Backup current PostgreSQL DB.
4. Run migration with `--drop-existing`.
5. Start PostgreSQL-compatible app.
6. Validate key counts.

Do not run `--drop-existing` if users have already written new production data to PostgreSQL.

## 10. PostgreSQL Compatibility Notes

The app originated on SQLite, so PostgreSQL compatibility is handled in `app.py`.

Important adapter elements:

```text
DATABASE_URL
USE_POSTGRES
translate_sql_for_postgres()
PgConnectionAdapter
PgCursorAdapter
```

Common SQLite patterns that break in PostgreSQL:

```text
datetime(column)
julianday(...)
date('now','localtime', ?)
ORDER BY datetime(column)
SELECT DISTINCT x ORDER BY lower(x)
PRAGMA table_info(...)
INSERT OR IGNORE
INSERT OR REPLACE
AUTOINCREMENT
```

Known fixes already made:

- `ORDER BY datetime(created_at)` replaced by text ordering.
- `julianday(...)` stale requirement check replaced by Python cutoff timestamp.
- `datetime(column)` translated to timestamp cast.
- `SELECT DISTINCT trim(status) ORDER BY lower(trim(status))` changed to `ORDER BY status`.
- Aware datetimes normalized in `parse_local_datetime()` to avoid:

```text
can't compare offset-naive and offset-aware datetimes
```

If a PostgreSQL error appears, search for the failing SQL function or expression in `app.py`, then patch either:

- The specific query.
- `translate_sql_for_postgres()` if it is a broad pattern.

## 11. Deployment Procedure

Typical deployment from Windows to EC2:

1. Update and test in:

```text
D:\hireflow_app
```

2. Syntax check:

```powershell
D:\hireflow_app\venv\Scripts\python.exe -m py_compile D:\hireflow_app\app.py
```

3. Copy changed files to EC2.

Usually:

```text
app.py
templates/*.html
static/* if changed
```

4. On EC2, backup current app file before replacement:

```bash
cp app.py app.py.backup_$(date +%Y%m%d_%H%M%S)
```

5. Restart service:

```bash
sudo systemctl restart hrguru-ats.service
sudo systemctl status hrguru-ats.service
```

6. Check logs:

```bash
sudo journalctl -u hrguru-ats.service -n 100 --no-pager
```

7. Test:

```bash
curl -I https://ats.hrgp.in/login
curl -I http://127.0.0.1:5001/login
```

Template-only changes may not require restart, but restart is safe if done during a maintenance window.

## 12. Common Errors And Fixes

### `Access not provisioned. Contact Admin.`

Cause:

- Google email/user does not exist in `app_users` or `team_members`.
- App is reading SQLite instead of PostgreSQL.

Checks:

```sql
SELECT * FROM team_members WHERE lower(trim(email))=lower(trim('<email>'));
SELECT * FROM app_users WHERE lower(trim(email))=lower(trim('<email>'));
```

On EC2, ensure `app.py` contains PostgreSQL support and systemd has `DATABASE_URL`.

### `redirect_uri_mismatch`

Cause:

- Google OAuth redirect URI differs from Google Cloud Console.

Correct URI:

```text
https://ats.hrgp.in/login/callback
```

### `deleted_client`

Cause:

- `GOOGLE_CLIENT_ID` in systemd points to a deleted OAuth client.

Fix:

- Create active OAuth Client ID.
- Update systemd env.
- Restart service.

### `Unexpected token < ... is not valid JSON`

Cause:

- Frontend expected JSON but backend returned HTML error page.

Fix:

- API endpoint should catch exceptions and return JSON.
- Frontend should parse text first and handle non-JSON response cleanly.

Bulk upload now has improved handling in:

```text
templates/upload.html
/api/upload
```

### `413 Request Entity Too Large`

Cause:

- Nginx upload limit too small.

Fix:

```nginx
client_max_body_size 100M;
```

Then:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### `ERR_TOO_MANY_REDIRECTS`

Cause:

- HTTPS block redirects to itself.
- Or Cloudflare Flexible SSL with Nginx HTTP-to-HTTPS redirect.

Fix:

- Remove `return 301 https://$host$request_uri;` from `listen 443 ssl` block.
- Use Cloudflare SSL mode Full or Full Strict for `ats.hrgp.in`.

### `function datetime(text) does not exist`

Cause:

- SQLite `datetime(column)` in PostgreSQL.

Fix:

- Replace with text ordering or PostgreSQL cast.
- Add translator rule if common.

### `for SELECT DISTINCT, ORDER BY expressions must appear in select list`

Cause:

- PostgreSQL strictness.

Fix:

- Order by selected alias or include order expression in select list.

### `can't compare offset-naive and offset-aware datetimes`

Cause:

- Python compares `datetime.now()` with PostgreSQL timezone-aware timestamp.

Fix:

- Normalize parsed datetimes in `parse_local_datetime()`.

## 13. Monitoring And Outage Handling

Recommended monitoring:

```text
Better Stack monitor: https://ats.hrgp.in/login
Expected status: 200
Keyword: HR Guru ATS
```

Recommended status page:

```text
https://status.hrgp.in
```

DNS:

```text
CNAME status -> statuspage.betteruptime.com
Proxy: DNS only
```

If old `hireflow.hrgp.in` should redirect to new ATS:

Use Cloudflare Redirect Rule:

```text
if hostname == hireflow.hrgp.in
redirect to https://ats.hrgp.in${uri.path}
preserve query string
status 302 while testing, 301 when final
```

Cloudflare redirect works even if the old tunnel app is down, because redirect happens at Cloudflare edge.

If EC2 is down, redirecting to `ats.hrgp.in` does not provide failover. Users will still see an outage. Use status page or Cloudflare Load Balancer for automated failover.

## 14. Important Database Tables

Core user/access:

```text
app_users
team_members
team_client_mappings
team_leader_mappings
user_login_audit
password_reset_tokens
user_registration_requests
```

Recruiting:

```text
candidates
requirements
requirement_submissions
clients
taggd_recruiters
upload_log
alerts
followup_daily_alerts
```

Email/communication:

```text
email_templates
email_log
communication_campaigns
communication_campaign_recipients
```

AI/search:

```text
ai_screening_logs
embedding_cache
parsed_resume_cache
match_results
match_audit_log
skills
skill_aliases
standard_skills
standard_roles
```

Operational:

```text
performance_logs
app_settings
```

## 15. User Removal Rules

Prefer deactivation for normal ex-employees:

```sql
UPDATE app_users SET is_active=0 WHERE ...;
UPDATE team_members SET is_ex_employee=1 WHERE ...;
```

Hard delete only if explicitly requested and if references are safe.

When hard deleting users, remove related rows from:

```text
app_users
team_members
team_client_mappings
team_leader_mappings
followup_daily_alerts
user_login_audit
password_reset_tokens
user_registration_requests
```

Avoid deleting candidate records created by that user unless explicitly required, because that damages historical recruiting data.

## 16. Rebuild From Scratch Blueprint

If rebuilding without code, implement these modules:

1. Authentication:
   - Username/password with secure password hashing.
   - Optional Google OAuth identity login.
   - Roles: Admin, Recruiter, Team Leader, Client Viewer.

2. Access control:
   - Client mappings.
   - Team leader mappings.
   - Candidate visibility by role.
   - Bulk upload permission.

3. Core data:
   - Clients.
   - Requirements.
   - Taggd recruiters.
   - Candidates.
   - Candidate statuses.
   - Upload logs.

4. Recruiter workflow pages:
   - Dashboard.
   - Add Requirement.
   - Add Candidate.
   - Bulk Upload.
   - Candidate List.
   - Requirement List.
   - Daily Reports.
   - My Follow-ups.
   - My Clients Mapping.

5. Admin workflow pages:
   - Dashboard.
   - User and Access Management.
   - Team Leader Mapping.
   - Client SLA Dashboard.
   - Candidate Follow-up Queue.
   - Data Quality Console.
   - Team Analytics.
   - Recruiter reports.
   - Taggd Recruiter setup.
   - Impersonify User.

6. Email:
   - Central SMTP.
   - Reply-To recruiter email.
   - Email templates.
   - Daily report email with attachments.
   - Candidate/feedback emails.

7. File handling:
   - Upload CV files.
   - Upload JD files.
   - Bulk upload CV matching.
   - Download/view uploaded files.

8. Performance:
   - Lightweight dashboards.
   - Lazy fetch only on demand.
   - Candidate list pagination.
   - Avoid loading full app shell for common pages.
   - Avoid auto AI screening on add/update unless explicitly requested.

9. Operations:
   - PostgreSQL database.
   - Nginx reverse proxy.
   - HTTPS cert.
   - systemd service.
   - Monitoring/status page.
   - Backup/restore process.

## 17. What Future Codex Should Read First

When opening this project in a new Codex environment, instruct Codex:

```text
Read PROJECT_KNOWLEDGE_BASE.md first.
Then inspect app.py for DATABASE_URL, USE_POSTGRES, PgConnectionAdapter, route definitions, and email functions.
Then inspect templates/admin_landing.html, templates/recruiter_landing.html, templates/upload.html, templates/candidate_list.html, templates/requirement_list.html, templates/daily_reports.html.
Production is PostgreSQL on EC2 and should not be treated as SQLite-only.
```

Recommended first commands:

```bash
rg -n "DATABASE_URL|USE_POSTGRES|PgConnectionAdapter|@app.route" app.py
rg -n "api/admin|team-analytics|candidate-followups|client-sla|data-quality" app.py templates
rg -n "datetime\\(|julianday\\(|INSERT OR|PRAGMA|AUTOINCREMENT" app.py
```

## 18. Open Maintenance Recommendations

- Keep `D:\hireflow_app` and `D:\hrguru-ats` synchronized or retire one to avoid version drift.
- Move business logic out of monolithic `app.py` over time.
- Add migrations instead of ad hoc schema creation.
- Add automated smoke tests for:
  - Login.
  - Dashboard.
  - Candidate list.
  - Requirement list.
  - Bulk upload.
  - Daily report send.
  - Admin Data Quality.
  - Client SLA.
  - Team Analytics.
- Add structured logging for API errors.
- Add database backups and restore drills.
- Add Better Stack/Uptime monitoring and public status page.
- Keep Google OAuth scope limited.
- Prefer username/password plus central SMTP Reply-To for recruiter email flows.

