from __future__ import annotations

import json
import time
from typing import Any

import requests


def relay_base_url(webhook_url: str) -> str:
    clean = (webhook_url or "").strip().rstrip("/")
    if clean.endswith("/send"):
        return clean[: -len("/send")]
    return clean


def auth_headers(token: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def wait_for_relay_ready(args: Any, wait_seconds: int = 60, interval_seconds: int = 5) -> tuple[bool, str]:
    base_url = relay_base_url(args.webhook_url)
    if not base_url:
        return False, "TEAM_SUBMISSION_WHATSAPP_WEBHOOK_URL is not configured."
    deadline = time.time() + max(0, wait_seconds)
    attempts = 0
    last_detail = ""
    while True:
        attempts += 1
        try:
            response = requests.get(
                f"{base_url}/healthz",
                headers=auth_headers(args.token),
                timeout=min(float(getattr(args, "timeout", 20) or 20), 10),
            )
            if response.status_code >= 400:
                last_detail = f"relay health HTTP {response.status_code}: {response.text[:300]}"
            else:
                data = response.json()
                if data.get("ok") and data.get("ready"):
                    return True, f"WhatsApp relay ready after {attempts} check(s)."
                last_detail = f"relay not ready: {data}"
        except Exception as exc:
            last_detail = f"relay health check failed: {type(exc).__name__}: {exc}"
        if time.time() >= deadline:
            return False, f"WhatsApp relay not ready after {wait_seconds}s; last status: {last_detail}"
        print(f"Waiting for WhatsApp relay readiness ({last_detail})", flush=True)
        time.sleep(interval_seconds)


def send_to_webhook(message: str, args: Any, html_message: str = "", wait_seconds: int = 60) -> tuple[bool, str]:
    if not args.webhook_url:
        return False, "TEAM_SUBMISSION_WHATSAPP_WEBHOOK_URL is not configured."
    ready, detail = wait_for_relay_ready(args, wait_seconds=wait_seconds)
    if not ready:
        return False, detail
    payload = {
        "message": message,
        "text": message,
        "group_id": args.group_id,
    }
    if html_message:
        payload["html"] = html_message
    try:
        response = requests.post(
            args.webhook_url,
            headers=auth_headers(args.token),
            data=json.dumps(payload),
            timeout=args.timeout,
        )
    except Exception as exc:
        return False, f"Webhook request failed: {type(exc).__name__}: {exc}"
    if response.status_code >= 400:
        return False, f"Webhook failed with HTTP {response.status_code}: {response.text[:500]}"
    return True, f"Webhook accepted message with HTTP {response.status_code}. {detail}"
