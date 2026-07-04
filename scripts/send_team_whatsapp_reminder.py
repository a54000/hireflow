#!/usr/bin/env python3
"""Send scheduled HR Guru team reminders to WhatsApp."""

from __future__ import annotations

import argparse
import json
import os
import sys

import requests


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


REMINDERS = {
    "morning": (
        "Good morning team.\n\n"
        "Please confirm that you have received today's requirements and share the roles you will be working on today."
    ),
    "afternoon": (
        "Afternoon check-in.\n\n"
        "Please share your submissions completed so far today and update the same in ATS."
    ),
    "evening": (
        "Evening reminder.\n\n"
        "Please complete and update your final candidate submissions in ATS before 7 PM. "
        "The daily submission report will be shared at 7 PM."
    ),
}


def load_env_file() -> None:
    env_path = os.path.join(ROOT, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a scheduled WhatsApp reminder to the HR Guru team.")
    parser.add_argument("reminder", choices=sorted(REMINDERS), help="Reminder message to send.")
    parser.add_argument("--message", default="", help="Override message text.")
    parser.add_argument("--send", action="store_true", help="Send to WhatsApp instead of printing.")
    parser.add_argument("--webhook-url", default=os.getenv("TEAM_SUBMISSION_WHATSAPP_WEBHOOK_URL", ""))
    parser.add_argument("--group-id", default=os.getenv("TEAM_SUBMISSION_WHATSAPP_GROUP_ID", ""))
    parser.add_argument("--token", default=os.getenv("TEAM_SUBMISSION_WHATSAPP_TOKEN", ""))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("TEAM_SUBMISSION_WHATSAPP_TIMEOUT", "20")))
    return parser.parse_args()


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
    load_env_file()
    args = parse_args()
    message = args.message.strip() or REMINDERS[args.reminder]
    print(message)
    if not args.send:
        return 0
    ok, detail = send_to_webhook(message, args)
    print(detail, file=sys.stderr)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
