import concurrent.futures
import os
import statistics
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, get_db, hash_password


USER_COUNT = 10
PASSWORD = "LoadTest#2026"


def ms(value):
    return round(value * 1000, 1)


def percentile(values, pct):
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def setup(run_id):
    conn = get_db()
    try:
        title = f"Load Test Requirement {run_id}"
        req_id = conn.execute(
            """
            INSERT INTO requirements (title, description, client_name, status, created_by)
            VALUES (?, ?, ?, 'Open', 'load_test')
            """,
            (title, "Temporary requirement for concurrent candidate-add load test.", "Load Test Client"),
        ).lastrowid
        users = []
        for i in range(USER_COUNT):
            email = f"loadtest-{run_id}-{i}@example.test"
            username = f"loadtest_{run_id}_{i}"
            team_id = conn.execute(
                """
                INSERT INTO team_members (name, email, phone, role, can_bulk_upload, is_fixed)
                VALUES (?, ?, ?, 'Recruiter', 0, 1)
                """,
                (f"Load Test User {i}", email, f"90000{int(run_id[-4:], 16) % 10000:04d}{i:02d}"),
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
                (f"loadtest-{run_id}-%@example.test",),
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
        conn.execute("DELETE FROM user_login_audit WHERE username LIKE ?", (f"loadtest_{run_id}_%",))
        conn.execute("DELETE FROM app_users WHERE username LIKE ?", (f"loadtest_{run_id}_%",))
        conn.execute("DELETE FROM team_members WHERE email LIKE ?", (f"loadtest-{run_id}-%@example.test",))
        conn.commit()
        return {"candidates": len(candidate_ids), "submissions": len(submission_ids), "requirement_id": req_id}
    finally:
        conn.close()


def one_user(user, req_id, barrier):
    candidate_index = user["index"]
    candidate_email = f"loadtest-{RUN_ID}-{candidate_index}@example.test"
    candidate_phone = f"98888{int(RUN_ID[-4:], 16) % 10000:04d}{candidate_index:02d}"
    result = {"user": user["username"], "ok": False}
    with app.test_client() as client:
        barrier.wait()
        total_start = time.perf_counter()

        login_start = time.perf_counter()
        login_res = client.post(
            "/login",
            data={"username": user["username"], "password": PASSWORD},
            follow_redirects=False,
        )
        result["login_ms"] = ms(time.perf_counter() - login_start)
        result["login_status"] = login_res.status_code
        if login_res.status_code not in (302, 303):
            result["error"] = f"login status {login_res.status_code}"
            result["total_ms"] = ms(time.perf_counter() - total_start)
            return result

        candidate_body = {
            "requirement_id": req_id,
            "candidate_name": f"Load Test Candidate {RUN_ID} {candidate_index}",
            "email_addr": candidate_email,
            "phone": candidate_phone,
            "current_company": "Load Test Co",
            "current_role": "Test Engineer",
            "experience_years": "5",
            "key_skills": "Python, Flask, SQL",
            "notice_period": "30 days",
            "current_salary": "10 LPA",
            "expected_salary": "12 LPA",
            "current_location": "Delhi",
            "preferred_location": "Gurgaon",
            "remarks": f"Temporary load test row {RUN_ID}",
            "sourcer_id": user["team_id"],
            "cv_filename": f"loadtest-{RUN_ID}-{candidate_index}.pdf",
            "cv_url": "",
            "cv_public_id": "",
            "cv_summary": "Temporary test CV summary.",
        }
        add_start = time.perf_counter()
        add_res = client.post("/api/candidate", json=candidate_body)
        add_json = add_res.get_json(silent=True) or {}
        result["candidate_ms"] = ms(time.perf_counter() - add_start)
        result["candidate_status"] = add_res.status_code
        result["candidate_id"] = add_json.get("id")
        if add_res.status_code != 200 or not add_json.get("ok"):
            result["error"] = add_json.get("error") or f"candidate status {add_res.status_code}"
            result["total_ms"] = ms(time.perf_counter() - total_start)
            return result

        sub_start = time.perf_counter()
        sub_res = client.post(
            "/api/submissions",
            json={
                "candidate_id": add_json["id"],
                "requirement_id": req_id,
                "sourcer_id": user["team_id"],
                "notes": "Temporary load test submission.",
                "checks": [],
            },
        )
        sub_json = sub_res.get_json(silent=True) or {}
        result["submission_ms"] = ms(time.perf_counter() - sub_start)
        result["submission_status"] = sub_res.status_code
        result["submission_id"] = sub_json.get("id")
        if sub_res.status_code != 200 or not sub_json.get("ok"):
            result["error"] = sub_json.get("error") or f"submission status {sub_res.status_code}"
            result["total_ms"] = ms(time.perf_counter() - total_start)
            return result

        result["ok"] = True
        result["total_ms"] = ms(time.perf_counter() - total_start)
        return result


def summarize(results, key):
    values = [row[key] for row in results if row.get(key) is not None]
    return {
        "min": min(values) if values else 0,
        "avg": round(statistics.mean(values), 1) if values else 0,
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "max": max(values) if values else 0,
    }


RUN_ID = uuid.uuid4().hex[:8]


def main():
    req_id = None
    cleanup_result = {}
    started = time.perf_counter()
    try:
        req_id, users = setup(RUN_ID)
        barrier = threading.Barrier(USER_COUNT)
        with concurrent.futures.ThreadPoolExecutor(max_workers=USER_COUNT) as pool:
            futures = [pool.submit(one_user, user, req_id, barrier) for user in users]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
    finally:
        if req_id:
            cleanup_result = cleanup(RUN_ID, req_id)

    results = sorted(results, key=lambda row: row["user"])
    ok_count = sum(1 for row in results if row.get("ok"))
    print(f"RUN_ID={RUN_ID}")
    print(f"USERS={USER_COUNT} OK={ok_count} FAILED={USER_COUNT - ok_count} WALL_MS={ms(time.perf_counter() - started)}")
    for key in ["login_ms", "candidate_ms", "submission_ms", "total_ms"]:
        print(f"{key}: {summarize(results, key)}")
    failures = [row for row in results if not row.get("ok")]
    if failures:
        print("FAILURES:")
        for row in failures:
            print(row)
    print(f"CLEANUP={cleanup_result}")


if __name__ == "__main__":
    main()
