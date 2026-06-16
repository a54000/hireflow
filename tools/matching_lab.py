#!/usr/bin/env python3
"""
Matching lab runner for CV + JD case folders.

Expected folder shape:
  uploads/matching_lab/case_001/
    resume.pdf|docx|doc|txt
    jd.pdf|docx|doc|txt
    metadata.json          optional

Generated outputs:
    codex_prompt.md
    match_result.json
    match_result.md
    human_review.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import traceback
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ats_pipeline import parse_jd, parse_resume, run_hybrid_match  # noqa: E402
from services.match_analysis import build_match_dashboard, build_recruiter_summary  # noqa: E402

SUPPORTED_EXTS = {".pdf", ".docx", ".doc", ".txt"}
OUTPUT_FILES = {"codex_prompt.md", "match_result.json", "match_result.md", "human_review.json"}


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml")
        root = ET.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        return "\n".join(node.text for node in root.findall(".//w:t", ns) if node.text)
    except Exception:
        print(f"MATCH DEBUG: DOCX text extraction fallback returned empty for {path.name}.", flush=True)
        return ""


def read_pdf(path: Path) -> str:
    try:
        import pymupdf

        doc = pymupdf.open(str(path))
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text
    except Exception:
        print(f"MATCH DEBUG: PDF text extraction fallback returned empty for {path.name}.", flush=True)
        return ""


def read_doc_with_textutil(path: Path) -> str:
    try:
        completed = subprocess.run(
            ["textutil", "-convert", "txt", "-stdout", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if completed.returncode == 0:
            return completed.stdout
    except Exception:
        print(f"MATCH DEBUG: DOC textutil fallback failed for {path.name}.", flush=True)
        pass
    return ""


def extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".txt":
        return read_text_file(path)
    if ext == ".docx":
        return read_docx(path)
    if ext == ".pdf":
        return read_pdf(path)
    if ext == ".doc":
        return read_doc_with_textutil(path)
    return ""


def clean_name(value: str) -> str:
    value = re.sub(r"[_\-]+", " ", value or "")
    return re.sub(r"\s+", " ", value).strip().lower()


def classify_file(path: Path) -> str:
    name = clean_name(path.stem)
    if re.search(r"\b(jd|job description|requirement|req|job)\b", name):
        return "jd"
    if re.search(r"\b(cv|resume|profile|candidate)\b", name):
        return "resume"
    return ""


def candidate_files(case_dir: Path) -> list[Path]:
    return [
        p for p in case_dir.iterdir()
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_EXTS
        and p.name not in OUTPUT_FILES
        and not p.name.startswith(".")
        and not p.name.startswith("~$")
    ]


def find_case_files(case_dir: Path) -> tuple[Path | None, Path | None]:
    files = candidate_files(case_dir)
    jd_files = [p for p in files if classify_file(p) == "jd"]
    resume_files = [p for p in files if classify_file(p) == "resume"]
    unknown = [p for p in files if classify_file(p) == ""]

    jd = jd_files[0] if jd_files else None
    resume = resume_files[0] if resume_files else None

    if not jd and len(files) == 2:
        jd = unknown[1] if resume and unknown else files[1]
    if not resume and len(files) == 2:
        resume = unknown[0] if jd and unknown else files[0]

    if not jd:
        exact = [p for p in files if p.stem.lower() == "jd"]
        jd = exact[0] if exact else None
    if not resume:
        exact = [p for p in files if p.stem.lower() in {"resume", "cv"}]
        resume = exact[0] if exact else None

    if jd and resume and jd == resume:
        return None, None
    return resume, jd


def discover_cases(root: Path) -> list[Path]:
    cases = []
    if find_case_files(root) != (None, None):
        cases.append(root)
    for child in sorted(root.iterdir()):
        if child.is_dir() and find_case_files(child) != (None, None):
            cases.append(child)
    return cases


def load_metadata(case_dir: Path) -> dict[str, Any]:
    path = case_dir / "metadata.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"metadata_error": "metadata.json is not valid JSON"}


def create_codex_prompt(case_dir: Path, resume: Path, jd: Path, metadata: dict[str, Any]) -> str:
    return f"""# JD/CV Matching Review

Case: `{case_dir.name}`
Resume: `{resume.name}`
JD: `{jd.name}`
Generated: {datetime.now().isoformat(timespec="seconds")}

## Reviewer Task
Compare the candidate CV against the JD and return:
- match score from 0 to 100
- recommendation: Strong Match / Moderate Match / Weak Match / Reject
- matched must-have skills
- missing or weak must-have skills
- role and responsibility alignment
- experience fit
- location, education, certification, notice-period, and salary concerns if visible
- recruiter screening questions
- final short recommendation for recruiter/hiring manager

## Metadata
```json
{json.dumps(metadata, indent=2, ensure_ascii=False)}
```

## Human Feedback To Capture Later
After reviewing the output, update `human_review.json` with:
- reviewer_score
- reviewer_decision
- what the matcher missed
- what the matcher got wrong
- parser gaps found in CV or JD
"""


def compact_list(items: Any, limit: int = 8) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(item) for item in items if item][:limit]


def infer_role_played(candidate: dict[str, Any], jd: dict[str, Any]) -> str:
    jd_role = str(jd.get("role_title") or jd.get("title") or "").strip()
    current_role = str(candidate.get("current_role") or "").strip()
    jd_domains = {d.get("domain") for d in jd.get("domain_taxonomy") or [] if isinstance(d, dict)}
    candidate_domains = {d.get("domain") for d in candidate.get("domain_confidence_scores") or [] if isinstance(d, dict)}
    if jd_role and current_role and jd_domains and candidate_domains and not (jd_domains & candidate_domains):
        return f"{current_role}; not aligned to the JD role of {jd_role}"
    responsibilities = []
    for role in candidate.get("role_history") or []:
        if isinstance(role, dict):
            responsibilities.extend(role.get("responsibilities") or [])
    evidence_text = " ".join(responsibilities + compact_list(candidate.get("normalized_skills"), 20)).lower()
    if jd_role:
        return f"{current_role or jd_role} aligned to the JD role of {jd_role}"
    if current_role:
        return current_role
    if any(term in evidence_text for term in ["microservices", "api", "backend", "kafka", ".net", "c#"]):
        return "Backend / Full Stack Software Engineer"
    if any(term in evidence_text for term in ["angular", "frontend", "ui"]):
        return "Frontend / Full Stack Software Engineer"
    return "Role not clearly inferred"


def create_markdown_report(case_dir: Path, resume: Path, jd: Path, result: dict[str, Any]) -> str:
    dashboard = result.get("dashboard") or {}
    overview = dashboard.get("overview") or {}
    parsed_jd = result.get("parsed_jd") or {}
    parsed_candidate = result.get("parsed_candidate") or {}
    role_played = infer_role_played(parsed_candidate, parsed_jd)
    summary = build_recruiter_summary(result, dashboard)
    matched = compact_list(result.get("matched_must_have_skills"))
    missing = compact_list(result.get("missing_must_have_skills"))
    strengths = compact_list(result.get("strengths"), 6)
    concerns = compact_list(result.get("concerns"), 6)

    def bullets(values: list[str], empty: str) -> str:
        return "\n".join(f"- {v}" for v in values) if values else f"- {empty}"

    return f"""# Match Result

Case: `{case_dir.name}`
Resume: `{resume.name}`
JD: `{jd.name}`
Generated: {datetime.now().isoformat(timespec="seconds")}

## Decision
- Final score: **{overview.get("final_score", result.get("final_score", 0))}**
- Verdict: **{overview.get("verdict", result.get("verdict", "-"))}**
- Recommendation: **{overview.get("recommendation", "-")}**
- Confidence: **{(overview.get("confidence") or {}).get("label", "-")}**

## Recruiter Summary
{summary}

## JD Snapshot
- Role: {parsed_jd.get("role_title") or parsed_jd.get("title") or "-"}
- Experience: {json.dumps(parsed_jd.get("experience_required") or {}, ensure_ascii=False)}
- Location: {parsed_jd.get("location") or "-"}
- Must-have skills: {", ".join(compact_list(parsed_jd.get("must_have_skills"), 20)) or "-"}
- Evidence to validate: {", ".join(compact_list(parsed_jd.get("validation_evidence"), 20)) or "-"}
- Parser confidence: {parsed_jd.get("parser_confidence") or "-"}

## Candidate Snapshot
- Name: {parsed_candidate.get("candidate_name") or parsed_candidate.get("name") or "-"}
- Current role: {parsed_candidate.get("current_role") or "-"}
- Role played for this JD: {role_played}
- Experience: {parsed_candidate.get("total_experience_years") or (parsed_candidate.get("experience_metrics") or {}).get("total_years_experience") or "-"}
- Skills: {", ".join(compact_list(parsed_candidate.get("normalized_skills") or parsed_candidate.get("primary_skills"), 25)) or "-"}

## Matched Must-Have Skills
{bullets(matched, "No must-have skills matched clearly.")}

## Missing / Weak Must-Have Skills
{bullets(missing, "No major missing must-have skills detected.")}

## Strengths
{bullets(strengths, "No strengths generated.")}

## Concerns
{bullets(concerns, "No concerns generated.")}

## Human Review
Update `human_review.json` after review. This file is intentionally created beside the result.
"""


def default_human_review(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "review_status": "pending",
        "reviewed_at": "",
        "reviewer": "",
        "codex_score": result.get("final_score") or result.get("score"),
        "reviewer_score": None,
        "reviewer_decision": "",
        "agree_with_recommendation": None,
        "matcher_missed": [],
        "matcher_got_wrong": [],
        "cv_parser_gaps": [],
        "jd_parser_gaps": [],
        "notes": "",
    }


def process_case(case_dir: Path, force: bool = False) -> dict[str, Any]:
    resume, jd = find_case_files(case_dir)
    if not resume or not jd:
        return {"case": str(case_dir), "status": "skipped", "reason": "resume and jd file not found"}

    result_path = case_dir / "match_result.json"
    if result_path.exists() and not force:
        return {"case": str(case_dir), "status": "skipped", "reason": "already processed"}

    metadata = load_metadata(case_dir)
    prompt = create_codex_prompt(case_dir, resume, jd, metadata)
    (case_dir / "codex_prompt.md").write_text(prompt, encoding="utf-8")

    resume_text = extract_text(resume)
    jd_text = extract_text(jd)
    if not resume_text.strip() or not jd_text.strip():
        error = {
            "case": case_dir.name,
            "resume": resume.name,
            "jd": jd.name,
            "ok": False,
            "error": "Could not extract text from resume or JD.",
            "resume_text_chars": len(resume_text or ""),
            "jd_text_chars": len(jd_text or ""),
        }
        result_path.write_text(json.dumps(error, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"case": str(case_dir), "status": "error", "reason": error["error"]}

    parsed_jd = parse_jd(jd_text)
    parsed_candidate = parse_resume(resume_text, {})
    result = run_hybrid_match(
        jd_text,
        resume_text,
        parsed_jd=parsed_jd,
        parsed_candidate=parsed_candidate,
    )
    result["role_played_for_jd"] = infer_role_played(parsed_candidate, parsed_jd)
    result["dashboard"] = build_match_dashboard(result)
    result["case"] = {
        "case_dir": str(case_dir),
        "resume_file": resume.name,
        "jd_file": jd.name,
        "metadata": metadata,
        "processed_at": datetime.now().isoformat(timespec="seconds"),
        "resume_text_chars": len(resume_text),
        "jd_text_chars": len(jd_text),
    }
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (case_dir / "match_result.md").write_text(create_markdown_report(case_dir, resume, jd, result), encoding="utf-8")

    review_path = case_dir / "human_review.json"
    if not review_path.exists():
        review_path.write_text(json.dumps(default_human_review(result), indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "case": str(case_dir),
        "status": "processed",
        "score": result.get("final_score"),
        "verdict": result.get("verdict"),
    }


def run_once(root: Path, force: bool = False) -> list[dict[str, Any]]:
    root.mkdir(parents=True, exist_ok=True)
    results = []
    for case_dir in discover_cases(root):
        try:
            results.append(process_case(case_dir, force=force))
        except Exception as exc:
            error = {
                "case": str(case_dir),
                "status": "error",
                "reason": str(exc),
                "traceback": traceback.format_exc(),
            }
            (case_dir / "match_error.json").write_text(json.dumps(error, indent=2), encoding="utf-8")
            results.append(error)
    return results


def watch(root: Path, interval: int, force: bool = False) -> None:
    print(f"Watching {root} every {interval}s. Press Ctrl+C to stop.")
    seen: set[str] = set()
    while True:
        results = run_once(root, force=force)
        for item in results:
            key = f"{item.get('case')}::{item.get('status')}::{item.get('reason', '')}"
            if key not in seen:
                print(json.dumps(item, ensure_ascii=False))
                seen.add(key)
        time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run JD/CV matching lab over case folders.")
    parser.add_argument("--folder", default=str(ROOT / "uploads" / "matching_lab"), help="Folder containing case folders.")
    parser.add_argument("--watch", action="store_true", help="Keep watching for new/changed cases.")
    parser.add_argument("--interval", type=int, default=10, help="Watch polling interval in seconds.")
    parser.add_argument("--force", action="store_true", help="Reprocess cases even if match_result.json exists.")
    args = parser.parse_args()

    folder = Path(args.folder).expanduser().resolve()
    if args.watch:
        watch(folder, args.interval, force=args.force)
        return 0

    results = run_once(folder, force=args.force)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
