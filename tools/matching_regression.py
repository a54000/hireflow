#!/usr/bin/env python3
"""
Lightweight regression checks for representative JD/CV matching cases.

This is intentionally small and practical:
- runs a handful of known case folders
- verifies verdict/score bands and a few key semantic signals
- surfaces regressions without requiring a full test framework
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.matching_lab import process_case  # noqa: E402


DEFAULT_CASES = [
    {
        "case_dir": "uploads/matching_lab/batch_jd94_20260526/case_04",
        "name": "Python Dev batch top candidate",
        "expect_verdict": "Moderate Match",
        "min_score": 65,
        "max_score": 80,
        "manual_review_required": True,
    },
    {
        "case_dir": "uploads/matching_lab/batch_jd94_20260526/case_01",
        "name": "Python Dev lower fit",
        "expect_verdict": "Reject / Not Recommended",
        "max_score": 45,
        "manual_review_required": True,
    },
    {
        "case_dir": "uploads/matching_lab/batch_architect_20260526/case_01",
        "name": "Software architect strong senior case",
        "expect_verdict": "Moderate Match",
        "min_score": 65,
        "max_score": 80,
        "manual_review_required": True,
        "expect_role_family_match": True,
    },
    {
        "case_dir": "uploads/matching_lab/batch_architect_20260526/case_04",
        "name": "Software architect second strong case",
        "expect_verdict": "Moderate Match",
        "min_score": 60,
        "max_score": 75,
        "manual_review_required": True,
        "expect_role_family_match": True,
    },
    {
        "case_dir": "uploads/matching_lab/case_siddharth_tool_shop",
        "name": "Manufacturing / tool-room case",
        "expect_verdict": "Weak Match",
        "max_score": 65,
        "manual_review_required": True,
    },
]


def _load_result(case_dir: Path) -> dict[str, Any]:
    result_path = case_dir / "match_result.json"
    process_case(case_dir, force=True)
    if result_path.exists():
        return json.loads(result_path.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"match_result.json not found for {case_dir}")


def _dashboard(result: dict[str, Any]) -> dict[str, Any]:
    dash = result.get("dashboard") or {}
    if not dash and result.get("parsed_jd") and result.get("parsed_candidate"):
        from services.match_analysis import build_match_dashboard

        dash = build_match_dashboard(result)
    return dash


def check_case(spec: dict[str, Any]) -> tuple[bool, list[str], dict[str, Any]]:
    case_dir = (ROOT / spec["case_dir"]).resolve()
    result = _load_result(case_dir)
    dashboard = _dashboard(result)
    overview = dashboard.get("overview") or {}
    role_cmp = dashboard.get("role_family_comparison") or {}
    manual_review = dashboard.get("manual_review") or {}

    errors: list[str] = []
    score = int(overview.get("final_score") or result.get("final_score") or 0)
    verdict = str(overview.get("verdict") or result.get("verdict") or "")
    if spec.get("expect_verdict") and verdict != spec["expect_verdict"]:
        errors.append(f"verdict expected {spec['expect_verdict']!r}, got {verdict!r}")
    if spec.get("min_score") is not None and score < int(spec["min_score"]):
        errors.append(f"score expected >= {spec['min_score']}, got {score}")
    if spec.get("max_score") is not None and score > int(spec["max_score"]):
        errors.append(f"score expected <= {spec['max_score']}, got {score}")
    if spec.get("manual_review_required") is True and not manual_review.get("required"):
        errors.append("manual review flag expected true")
    if spec.get("manual_review_required") is False and manual_review.get("required"):
        errors.append("manual review flag expected false")
    if spec.get("expect_role_family_match") is True:
        summary = str(role_cmp.get("match_summary") or "")
        if "same role family" not in summary.lower():
            errors.append(f"role-family match expected, got summary: {summary!r}")

    summary = {
        "case": spec["name"],
        "case_dir": str(case_dir),
        "score": score,
        "verdict": verdict,
        "manual_review": bool(manual_review.get("required")),
        "role_family_summary": role_cmp.get("match_summary", ""),
    }
    return (not errors), errors, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run lightweight matching regressions.")
    parser.add_argument("--cases", nargs="*", help="Optional subset of case directories relative to repo root.")
    args = parser.parse_args()

    specs = DEFAULT_CASES
    if args.cases:
        wanted = {str(Path(c).as_posix()).lower() for c in args.cases}
        specs = [spec for spec in DEFAULT_CASES if str(Path(spec["case_dir"]).as_posix()).lower() in wanted]

    results = []
    failures = 0
    for spec in specs:
        ok, errors, summary = check_case(spec)
        results.append({"ok": ok, "summary": summary, "errors": errors})
        if not ok:
            failures += 1

    print(json.dumps(results, indent=2, ensure_ascii=False))
    if failures:
        print(f"\nRegression checks failed for {failures} case(s).", file=sys.stderr)
        return 1
    print(f"\nRegression checks passed for {len(specs)} case(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
