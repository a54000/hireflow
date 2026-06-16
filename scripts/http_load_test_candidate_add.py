import concurrent.futures
import os
import statistics
import sys
import threading
import time
import uuid

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import get_db, hash_password


BASE_URL = os.getenv("ATS_BASE_URL", "http://127.0.0.1:5001").rstrip("/")
USER_COUNT = int(os.getenv("ATS_LOAD_USERS", "10"))
PASSWORD = "LoadTest#2026"
DETAIL = os.getenv("ATS_LOAD_DETAIL", "0").strip().lower() in {"1", "true", "yes"}


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
            VALUES (?, ?, ?, 'Open', 'http_load_test')
            """,
            (
                f"HTTP Load Test Requirement {run_id}",
                "Temporary requirement for HTTP concurrent candidate-add load test.",
                "HTTP Load Test Client",
            ),
        ).lastrowid
        users = []
        for i in range(USER_COUNT):
            email = f"http-loadtest-{run_id}-{i}@example.test"
            username = f"http_loadtest_{run_id}_{i}"
            team_id = conn.execute(
                """
                INSERT INTO team_members (name, email, phone, role, can_bulk_upload, is_fixed)
                VALUES (?, ?, ?, 'Recruiter', 0, 1)
                """,
                (f"HTTP Load Test User {i}", email, f"91111{int(run_id[-4:], 16) % 10000:04d}{i:02d}"),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO app_users (username, password, email, team_member_id, is_admin, is_bulk_admin, is_active)
                VALUES (?, ?, ?, ?, 0, 0, 1)
                """,
                (username, hash_password(PASSWORD), email, team_id),
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
                (f"http-loadtest-{run_id}-%@example.test",),
            ).fetchall()
        ]
        submission_ids = []
        if candidate_ids:
            placeholders = ",".join("?" * len(candidate_ids))
            submission_ids = [
                row["id"]
                for row in conn.execute(
                    f"SELECT id FROM requirement_submissions WHERE candidate_id IN ({placeholders})",
                    candidate_ids,
                ).fetchall()
            ]
            if submission_ids:
                sub_placeholders = ",".join("?" * len(submission_ids))
                conn.execute(f"DELETE FROM submission_checks WHERE submission_id IN ({sub_placeholders})", submission_ids)
                conn.execute(f"DELETE FROM requirement_submissions WHERE id IN ({sub_placeholders})", submission_ids)
            conn.execute(f"DELETE FROM alerts WHERE candidate_id IN ({placeholders})", candidate_ids)
            conn.execute(f"DELETE FROM candidates WHERE id IN ({placeholders})", candidate_ids)
        conn.execute("DELETE FROM requirements WHERE id=?", (req_id,))
        conn.execute("DELETE FROM user_login_audit WHERE username LIKE ?", (f"http_loadtest_{run_id}_%",))
        conn.execute("DELETE FROM app_users WHERE username LIKE ?", (f"http_loadtest_{run_id}_%",))
        conn.execute("DELETE FROM team_members WHERE email LIKE ?", (f"http-loadtest-{run_id}-%@example.test",))
        conn.commit()
        return {"candidates": len(candidate_ids), "submissions": len(submission_ids), "requirement_id": req_id}
    finally:
        conn.close()


def one_user(run_id, user, req_id, barrier):
    idx = user["index"]
    result = {"user": user["username"], "ok": False}
    session = requests.Session()
    barrier.wait()
    total_start = time.perf_counter()
    try:
        login_start = time.perf_counter()
        login_res = session.post(
            f"{BASE_URL}/login",
            data={"username": user["username"], "password": PASSWORD},
            allow_redirects=False,
            timeout=30,
        )
        result["login_ms"] = ms(time.perf_counter() - login_start)
        result["login_status"] = login_res.status_code
        if login_res.status_code not in (302, 303):
            result["error"] = f"login status {login_res.status_code}"
            return result

        candidate_body = {
            "requirement_id": req_id,
            "candidate_name": f"HTTP Load Test Candidate {run_id} {idx}",
            "email_addr": f"http-loadtest-{run_id}-{idx}@example.test",
            "phone": f"97777{int(run_id[-4:], 16) % 10000:04d}{idx:02d}",
            "current_company": "HTTP Load Test Co",
            "current_role": "Test Engineer",
            "experience_years": "5",
            "key_skills": "Python, Flask, SQL",
            "notice_period": "30 days",
            "current_salary": "10 LPA",
            "expected_salary": "12 LPA",
            "current_location": "Delhi",
            "preferred_location": "Gurgaon",
            "remarks": f"Temporary HTTP load test row {run_id}",
            "sourcer_id": user["team_id"],
            "cv_filename": f"http-loadtest-{run_id}-{idx}.pdf",
            "cv_url": "",
            "cv_public_id": "",
            "cv_summary": "Temporary test CV summary.",
        }
        add_start = time.perf_counter()
        add_res = session.post(f"{BASE_URL}/api/candidate", json=candidate_body, timeout=30)
        add_json = add_res.json() if add_res.headers.get("content-type", "").startswith("application/json") else {}
        result["candidate_ms"] = ms(time.perf_counter() - add_start)
        result["candidate_status"] = add_res.status_code
        result["candidate_id"] = add_json.get("id")
        if add_res.status_code != 200 or not add_json.get("ok"):
            result["error"] = add_json.get("error") or f"candidate status {add_res.status_code}"
            return result

        sub_start = time.perf_counter()
        sub_res = session.post(
            f"{BASE_URL}/api/submissions",
            json={
                "candidate_id": add_json["id"],
                "requirement_id": req_id,
                "sourcer_id": user["team_id"],
                "notes": "Temporary HTTP load test submission.",
                "checks": [],
            },
            timeout=30,
        )
        sub_json = sub_res.json() if sub_res.headers.get("content-type", "").startswith("application/json") else {}
        result["submission_ms"] = ms(time.perf_counter() - sub_start)
        result["submission_status"] = sub_res.status_code
        result["submission_id"] = sub_json.get("id")
        if sub_res.status_code != 200 or not sub_json.get("ok"):
            result["error"] = sub_json.get("error") or f"submission status {sub_res.status_code}"
            return result

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
    results = []
    cleanup_result = {}
    started = time.perf_counter()
    try:
        req_id, users = setup(run_id)
        barrier = threading.Barrier(USER_COUNT)
        with concurrent.futures.ThreadPoolExecutor(max_workers=USER_COUNT) as pool:
            futures = [pool.submit(one_user, run_id, user, req_id, barrier) for user in users]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
    finally:
        if req_id:
            cleanup_result = cleanup(run_id, req_id)

    results = sorted(results, key=lambda row: row["user"])
    ok_count = sum(1 for row in results if row.get("ok"))
    print(f"BASE_URL={BASE_URL}")
    print(f"RUN_ID={run_id}")
    print(f"USERS={USER_COUNT} OK={ok_count} FAILED={USER_COUNT - ok_count} WALL_MS={ms(time.perf_counter() - started)}")
    for key in ["login_ms", "candidate_ms", "submission_ms", "total_ms"]:
        print(f"{key}: {summarize(results, key)}")
    failures = [row for row in results if not row.get("ok")]
    if failures:
        print("FAILURES:")
        for row in failures:
            print(row)
    if DETAIL:
        print("DETAIL:")
        for row in results:
            print(row)
    print(f"CLEANUP={cleanup_result}")


if __name__ == "__main__":
    main()
