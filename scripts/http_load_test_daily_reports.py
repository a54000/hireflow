import concurrent.futures
import os
import statistics
import sys
import threading
import time
import uuid
from datetime import date

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import get_db, hash_password


BASE_URL = os.getenv("ATS_BASE_URL", "http://127.0.0.1:5001").rstrip("/")
USER_COUNT = int(os.getenv("ATS_LOAD_USERS", "10"))
PASSWORD = "DailyReports#2026"


def ms(value):
    return round(value * 1000, 1)


def percentile(values, pct):
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def summarize(results, key):
    values = [row[key] for row in results if row.get(key) is not None]
    return {
        "min": min(values) if values else 0,
        "avg": round(statistics.mean(values), 1) if values else 0,
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "max": max(values) if values else 0,
    }


def setup(run_id):
    conn = get_db()
    try:
        req_id = conn.execute(
            """
            INSERT INTO requirements (title, description, client_name, status, created_by)
            VALUES (?, ?, ?, 'Open', 'daily_reports_load_test')
            """,
            (
                f"Daily Reports Load Test Requirement {run_id}",
                "Temporary requirement for daily reports load test.",
                "Daily Reports Load Test Client",
            ),
        ).lastrowid
        users = []
        for i in range(USER_COUNT):
            email = f"daily-reports-loadtest-{run_id}-{i}@example.test"
            username = f"daily_reports_loadtest_{run_id}_{i}"
            team_id = conn.execute(
                """
                INSERT INTO team_members (name, email, phone, role, can_bulk_upload, is_fixed)
                VALUES (?, ?, ?, 'Recruiter', 0, 1)
                """,
                (f"Daily Reports Load Test User {i}", email, f"92222{int(run_id[-4:], 16) % 10000:04d}{i:02d}"),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO app_users (username, password, email, team_member_id, is_admin, is_bulk_admin, is_active)
                VALUES (?, ?, ?, ?, 0, 0, 1)
                """,
                (username, hash_password(PASSWORD), email, team_id),
            )
            for j in range(15):
                conn.execute(
                    """
                    INSERT INTO candidates
                        (candidate_name, email_addr, phone, current_company, current_role, role_name,
                         status, recruiter_name, recruiter_email, sourcer_id, requirement_id, created_at)
                    VALUES (?, ?, ?, 'Load Test Co', 'Engineer', 'Engineer', 'New', ?, ?, ?, ?, datetime('now','localtime'))
                    """,
                    (
                        f"Daily Reports Candidate {run_id} {i}-{j}",
                        f"daily-reports-loadtest-{run_id}-{i}-{j}@example.test",
                        f"93333{int(run_id[-4:], 16) % 10000:04d}{i:02d}{j:02d}",
                        f"Daily Reports Load Test User {i}",
                        email,
                        team_id,
                        req_id,
                    ),
                )
            users.append({"username": username, "email": email, "team_id": team_id, "index": i})
        conn.commit()
        return req_id, users
    finally:
        conn.close()


def cleanup(run_id, req_id):
    conn = get_db()
    try:
        candidate_ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM candidates WHERE email_addr LIKE ?",
                (f"daily-reports-loadtest-{run_id}-%@example.test",),
            ).fetchall()
        ]
        if candidate_ids:
            placeholders = ",".join("?" * len(candidate_ids))
            conn.execute(f"DELETE FROM alerts WHERE candidate_id IN ({placeholders})", candidate_ids)
            conn.execute(f"DELETE FROM candidates WHERE id IN ({placeholders})", candidate_ids)
        conn.execute("DELETE FROM requirements WHERE id=?", (req_id,))
        conn.execute("DELETE FROM user_login_audit WHERE username LIKE ?", (f"daily_reports_loadtest_{run_id}_%",))
        conn.execute("DELETE FROM app_users WHERE username LIKE ?", (f"daily_reports_loadtest_{run_id}_%",))
        conn.execute("DELETE FROM team_members WHERE email LIKE ?", (f"daily-reports-loadtest-{run_id}-%@example.test",))
        conn.commit()
        return {"candidates": len(candidate_ids), "requirement_id": req_id}
    finally:
        conn.close()


def one_user(user, barrier):
    result = {"user": user["username"], "ok": False}
    session = requests.Session()
    today = date.today().isoformat()
    barrier.wait()
    total_start = time.perf_counter()
    try:
        started = time.perf_counter()
        login_res = session.post(
            f"{BASE_URL}/login",
            data={"username": user["username"], "password": PASSWORD},
            allow_redirects=False,
            timeout=30,
        )
        result["login_ms"] = ms(time.perf_counter() - started)
        result["login_status"] = login_res.status_code
        if login_res.status_code not in (302, 303):
            result["error"] = f"login status {login_res.status_code}"
            return result

        started = time.perf_counter()
        page_res = session.get(f"{BASE_URL}/daily-reports", timeout=30)
        result["page_ms"] = ms(time.perf_counter() - started)
        result["page_status"] = page_res.status_code
        result["page_bytes"] = len(page_res.content)
        if page_res.status_code != 200:
            result["error"] = f"page status {page_res.status_code}"
            return result

        started = time.perf_counter()
        filters_res = session.get(f"{BASE_URL}/api/candidate_search_filters", timeout=30)
        result["filters_ms"] = ms(time.perf_counter() - started)
        result["filters_status"] = filters_res.status_code
        result["filters_bytes"] = len(filters_res.content)
        if filters_res.status_code != 200:
            result["error"] = f"filters status {filters_res.status_code}"
            return result

        started = time.perf_counter()
        candidates_res = session.get(
            f"{BASE_URL}/api/candidates",
            params={
                "all": "1",
                "view": "reporting",
                "date_from": today,
                "date_to": today,
                "sort": "newest",
            },
            timeout=30,
        )
        result["candidates_ms"] = ms(time.perf_counter() - started)
        result["candidates_status"] = candidates_res.status_code
        result["candidates_bytes"] = len(candidates_res.content)
        if candidates_res.status_code != 200:
            result["error"] = f"candidates status {candidates_res.status_code}"
            return result
        payload = candidates_res.json()
        result["candidate_rows"] = len(payload) if isinstance(payload, list) else 0
        result["ok"] = True
        return result
    except Exception as exc:
        result["error"] = str(exc)
        return result
    finally:
        result["total_ms"] = ms(time.perf_counter() - total_start)


def main():
    run_id = uuid.uuid4().hex[:8]
    req_id = None
    started = time.perf_counter()
    results = []
    cleanup_result = {}
    try:
        req_id, users = setup(run_id)
        barrier = threading.Barrier(USER_COUNT)
        with concurrent.futures.ThreadPoolExecutor(max_workers=USER_COUNT) as pool:
            futures = [pool.submit(one_user, user, barrier) for user in users]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
    finally:
        if req_id:
            cleanup_result = cleanup(run_id, req_id)

    results = sorted(results, key=lambda row: row["user"])
    ok_count = sum(1 for row in results if row.get("ok"))
    print(f"BASE_URL={BASE_URL}")
    print(f"RUN_ID={run_id}")
    print(f"USERS={USER_COUNT} OK={ok_count} FAILED={USER_COUNT - ok_count} WALL_MS={ms(time.perf_counter() - started)}")
    for key in ["login_ms", "page_ms", "filters_ms", "candidates_ms", "total_ms"]:
        print(f"{key}: {summarize(results, key)}")
    rows = [r.get("candidate_rows", 0) for r in results if r.get("ok")]
    if rows:
        print(f"candidate_rows_per_user min={min(rows)} avg={round(statistics.mean(rows), 1)} max={max(rows)}")
    bytes_summary = {
        "page_bytes_avg": round(statistics.mean([r.get("page_bytes", 0) for r in results]), 1) if results else 0,
        "filters_bytes_avg": round(statistics.mean([r.get("filters_bytes", 0) for r in results]), 1) if results else 0,
        "candidates_bytes_avg": round(statistics.mean([r.get("candidates_bytes", 0) for r in results]), 1) if results else 0,
    }
    print(f"bytes={bytes_summary}")
    print(f"CLEANUP={cleanup_result}")
    for row in results:
        if not row.get("ok"):
            print(f"FAILED {row['user']}: {row.get('error')} {row}")


if __name__ == "__main__":
    main()
