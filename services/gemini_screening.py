import json
import os
import re
import random
import threading
import time
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Literal, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, ValidationError


GEMINI_CIRCUIT_OPEN_UNTIL = 0.0
GEMINI_CIRCUIT_REASON = ""
GEMINI_SCREENING_ACTIVE_LIMIT = max(1, int(float(os.getenv("GEMINI_SCREENING_ACTIVE_LIMIT", "5") or 5)))
GEMINI_SCREENING_ACTIVE_SEMAPHORE = threading.BoundedSemaphore(GEMINI_SCREENING_ACTIVE_LIMIT)
GEMINI_CIRCUIT_STATE_LOCK = threading.Lock()
GEMINI_CIRCUIT_STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "uploads",
    ".gemini_circuit_state.json",
)
GEMINI_MODEL_PRIMARY = os.getenv("GEMINI_MODEL_PRIMARY", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
GEMINI_MODEL_FALLBACK = os.getenv("GEMINI_MODEL_FALLBACK", "gemini-1.5-flash").strip() or "gemini-1.5-flash"


SYSTEM_INSTRUCTION = """You are an expert Talent Acquisition Coach training a team of recruiters.

Your job is to analyze a Candidate Resume against a Job Description (JD) and produce a simple, jargon-free screening analysis.

Follow these 5 rules:
1. Use simple language. Avoid heavy corporate jargon.
2. Catch claimed-vs-proven skills. If a skill appears in the Skills Summary but has no supporting project, metric, outcome, or role evidence, flag it as unverified.
3. Call out fake-vs-real experience. For AI specifically, distinguish between using tools like ChatGPT/Copilot as helpers versus building or deploying AI/ML systems.
4. Provide an interview cheat sheet. Give recruiters exact questions to ask, along with what a good answer and a bad answer sound like.
5. Check level fit. If the candidate is clearly overqualified or underqualified for the role level, call it out. Being overqualified can be a flight risk; being underqualified is a skills gap.
6. Check chronology carefully. Only call a date future if it is clearly parsed and truly after today's date. If a date format is ambiguous, say so instead of calling it future.

Your output will be structured as JSON and enforced separately by schema. Focus on the quality of your analysis, not on formatting.
Do not add extra sections beyond what the schema supports. If evidence is weak, say so plainly and politely.
"""


class RequirementMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    what_the_job_asks_for: str = Field(min_length=1)
    what_the_candidate_actually_has: str = Field(min_length=1)
    junior_recruiter_verdict: Literal["✅ Match", "❌ Missing", "⚠️ Partial"]


class ScoreBreakdownItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    raw_score: int = Field(ge=0, le=100)
    score: Optional[int] = None
    weight: float = Field(ge=0, le=1)
    weighted_score: float = Field(default=0.0)
    reason: str = Field(default="")


class ScreeningQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    bad_answer: str = Field(min_length=1)
    good_answer: str = Field(min_length=1)


class KeywordStuffingFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill: str = Field(min_length=1)
    claimed_in: str = Field(min_length=1)
    evidence_found: bool
    evidence_note: str = Field(default="")
    verdict: Literal["Verified", "Unverified", "Likely Stuffed"]


class AIExperienceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims_ai_experience: bool
    evidence_type: Literal["None", "Tool User Only", "Applied AI", "Built AI Systems"]
    evidence_summary: str = Field(default="")
    is_inflated: bool


class ScreeningReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_name: str = Field(min_length=1)
    target_job_title: str = Field(min_length=1)
    final_score: int = Field(ge=0, le=100)
    ats_verdict: Literal["Strong Match", "Moderate Match", "Weak Match", "Reject / Not Recommended"]
    call_or_reject: Literal["🟢 Call Immediately", "⚠️ Proceed with Caution", "🔴 Reject"]
    recommendation: str = Field(min_length=1)
    requirement_matches: List[RequirementMatch]
    green_flags: List[str] = Field(min_length=1)
    red_flags: List[str] = Field(min_length=1)
    strengths: List[str] = Field(min_length=1)
    concerns: List[str] = Field(min_length=1)
    score_breakdown: List[ScoreBreakdownItem] = Field(default_factory=list)
    matched_must_have_skills: List[str] = Field(default_factory=list)
    missing_must_have_skills: List[str] = Field(default_factory=list)
    keyword_stuffing_flags: List[KeywordStuffingFlag] = Field(default_factory=list)
    ai_experience: Optional[AIExperienceAssessment] = None
    screening_questions: List[ScreeningQuestion] = Field(min_length=1, max_length=5)
    summary: str = Field(min_length=20)
    scoring_source: Optional[str] = "gemini"


SCORE_WEIGHT_PLAN = [
    {"key": "must_have_skills", "label": "Must-Have Skills", "weight": 0.35},
    {"key": "role_alignment", "label": "Role Alignment", "weight": 0.20},
    {"key": "experience_fit", "label": "Experience Fit", "weight": 0.20},
    {"key": "domain_fit", "label": "Domain Fit", "weight": 0.10},
    {"key": "seniority_fit", "label": "Seniority Fit", "weight": 0.08},
    {"key": "education_fit", "label": "Education Fit", "weight": 0.04},
    {"key": "nice_to_have", "label": "Nice-to-Have", "weight": 0.03},
]

SCORE_WEIGHT_LOOKUP = {
    item["key"]: item for item in SCORE_WEIGHT_PLAN
}

SCORE_WEIGHT_PROMPT_LINES = [
    "Use exactly these weighted scoring categories and do not invent new weights:",
]
for idx, item in enumerate(SCORE_WEIGHT_PLAN, start=1):
    SCORE_WEIGHT_PROMPT_LINES.append(
        f"{idx}. {item['label']} ({item['key']}): {int(round(item['weight'] * 100))}% weight"
    )
SCORE_WEIGHT_PROMPT_LINES.extend(
    [
        "For each category, return a raw_score from 0 to 100 and a short reason tied to JD/CV evidence.",
        "Do not compute the official final_score yourself; the application will compute the official score from the weighted breakdown.",
        "Keep the breakdown focused on these categories only so the report stays stable across runs.",
    ]
)
SCORE_WEIGHT_PROMPT_TEXT = "\n".join(SCORE_WEIGHT_PROMPT_LINES)


def score_to_verdict(score):
    score = int(round(float(score or 0)))
    if score >= 75:
        return "Strong Match"
    if score >= 55:
        return "Moderate Match"
    if score >= 35:
        return "Weak Match"
    return "Reject / Not Recommended"


def score_to_call_or_reject(score):
    verdict = score_to_verdict(score)
    if verdict == "Strong Match":
        return "🟢 Call Immediately"
    if verdict == "Moderate Match":
        return "⚠️ Proceed with Caution"
    return "🔴 Reject"


def _normalize_breakdown_key(item):
    raw_key = str((item or {}).get("key") or "").strip().lower()
    raw_label = re.sub(r"[^a-z]+", "_", str((item or {}).get("label") or "").strip().lower()).strip("_")
    for key, plan in SCORE_WEIGHT_LOOKUP.items():
        if raw_key == key or raw_label == key or raw_key.replace("-", "_") == key:
            return key, plan
    if "must" in raw_key and "skill" in raw_key:
        return "must_have_skills", SCORE_WEIGHT_LOOKUP["must_have_skills"]
    if "role" in raw_key and "align" in raw_key:
        return "role_alignment", SCORE_WEIGHT_LOOKUP["role_alignment"]
    if "experience" in raw_key:
        return "experience_fit", SCORE_WEIGHT_LOOKUP["experience_fit"]
    if "domain" in raw_key:
        return "domain_fit", SCORE_WEIGHT_LOOKUP["domain_fit"]
    if "senior" in raw_key or "level" in raw_key:
        return "seniority_fit", SCORE_WEIGHT_LOOKUP["seniority_fit"]
    if "education" in raw_key or "degree" in raw_key:
        return "education_fit", SCORE_WEIGHT_LOOKUP["education_fit"]
    if "nice" in raw_key or "preferred" in raw_key:
        return "nice_to_have", SCORE_WEIGHT_LOOKUP["nice_to_have"]
    return raw_key or "other", {"key": raw_key or "other", "label": str((item or {}).get("label") or raw_key or "Other").strip() or "Other", "weight": 0.0}


def normalize_score_breakdown(report):
    report = dict(report or {})
    raw_items = report.get("score_breakdown") or []
    item_map = {}
    if isinstance(raw_items, list):
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            key, plan = _normalize_breakdown_key(item)
            raw_score = item.get("raw_score", item.get("score", 0))
            try:
                raw_score = int(round(float(raw_score or 0)))
            except Exception:
                raw_score = 0
            weight = plan.get("weight", item.get("weight", 0.0) or 0.0)
            try:
                weight = float(weight or 0.0)
            except Exception:
                weight = 0.0
            normalized_item = {
                "key": key,
                "label": item.get("label") or plan.get("label") or key.replace("_", " ").title(),
                "raw_score": max(0, min(100, raw_score)),
                "score": max(0, min(100, raw_score)),
                "weight": round(max(0.0, min(1.0, weight)), 4),
                "weighted_score": round(max(0, min(100, raw_score)) * round(max(0.0, min(1.0, weight)), 4), 1),
                "reason": str(item.get("reason") or "").strip(),
            }
            item_map[key] = normalized_item
    for plan in SCORE_WEIGHT_PLAN:
        if plan["key"] not in item_map:
            item_map[plan["key"]] = {
                "key": plan["key"],
                "label": plan["label"],
                "raw_score": 0,
                "score": 0,
                "weight": plan["weight"],
                "weighted_score": 0.0,
                "reason": "Not returned by model.",
            }
    normalized_items = [item_map[plan["key"]] for plan in SCORE_WEIGHT_PLAN]
    final_score = int(round(sum(item["weighted_score"] for item in normalized_items)))
    report["score_breakdown"] = normalized_items
    report["final_score"] = max(0, min(100, final_score))
    report["score"] = report["final_score"]
    report["ats_verdict"] = score_to_verdict(report["final_score"])
    report["call_or_reject"] = score_to_call_or_reject(report["final_score"])
    report["verdict"] = report["ats_verdict"]
    return report


def _safe_text(value, limit=12000):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    half = max(1, limit // 2)
    return text[:half] + " ...[middle section truncated for length]... " + text[-half:]


RESUME_DATE_TOKEN_RE = re.compile(
    r"\b(?:"
    r"\d{1,2}[/-]\d{1,2}[/-](?:19|20)\d{2}"
    r"|(?:19|20)\d{2}[/-]\d{1,2}[/-]\d{1,2}"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+(?:19|20)\d{2}"
    r"|\d{1,2}[/-](?:19|20)\d{2}"
    r")\b",
    re.I,
)


def _parse_resume_date_token(token):
    text = re.sub(r"\s+", " ", str(token or "")).strip(" ,;:-")
    if not text:
        return None
    lower = text.lower()
    if re.search(r"\b(current|present|till\s+date|to\s+date|working)\b", lower):
        return {
            "raw": text,
            "kind": "current_marker",
            "parsed": "",
            "is_future": False,
            "ambiguous": False,
        }
    today = date.today()
    month_lookup = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    }
    numeric = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-]((?:19|20)\d{2})$", text)
    if numeric:
        first = int(numeric.group(1))
        second = int(numeric.group(2))
        year = int(numeric.group(3))
        ambiguous = False
        if first > 12 and second <= 12:
            day, month = first, second
        elif second > 12 and first <= 12:
            month, day = first, second
        elif first <= 12 and second <= 12:
            day, month = first, second
            ambiguous = True
        else:
            return None
        try:
            parsed = date(year, month, day)
        except Exception:
            return None
        return {
            "raw": text,
            "kind": "full_date",
            "parsed": parsed.isoformat(),
            "is_future": parsed > today,
            "ambiguous": ambiguous,
        }
    month_year = re.match(r"^([A-Za-z]{3,9})\s+((?:19|20)\d{2})$", text)
    if month_year:
        month_name = month_year.group(1).lower()
        month = month_lookup.get(month_name[:3]) or month_lookup.get(month_name)
        year = int(month_year.group(2))
        if month:
            try:
                parsed = date(year, month, 1)
            except Exception:
                return None
            return {
                "raw": text,
                "kind": "month_year",
                "parsed": parsed.isoformat(),
                "is_future": parsed > today,
                "ambiguous": True,
            }
    month_year_numeric = re.match(r"^(\d{1,2})[/-]((?:19|20)\d{2})$", text)
    if month_year_numeric:
        month = int(month_year_numeric.group(1))
        year = int(month_year_numeric.group(2))
        if 1 <= month <= 12:
            try:
                parsed = date(year, month, 1)
            except Exception:
                return None
            return {
                "raw": text,
                "kind": "month_year",
                "parsed": parsed.isoformat(),
                "is_future": parsed > today,
                "ambiguous": True,
            }
    year_only = re.match(r"^((?:19|20)\d{2})$", text)
    if year_only:
        parsed = date(int(year_only.group(1)), 1, 1)
        return {
            "raw": text,
            "kind": "year",
            "parsed": parsed.isoformat(),
            "is_future": parsed > today,
            "ambiguous": True,
        }
    return None


def extract_resume_date_notes(text, max_notes=6):
    notes = []
    seen = set()
    lines = [re.sub(r"\s+", " ", line).strip() for line in str(text or "").splitlines() if line.strip()]
    for line in lines:
        if not re.search(r"\b(experience|employment|work|role|company|current|present|from|since|till|date)\b", line, re.I):
            continue
        for token in RESUME_DATE_TOKEN_RE.findall(line):
            parsed = _parse_resume_date_token(token)
            if not parsed:
                continue
            key = (parsed.get("kind"), parsed.get("raw"), parsed.get("parsed"))
            if key in seen:
                continue
            seen.add(key)
            note = {
                "raw": parsed.get("raw", ""),
                "parsed": parsed.get("parsed", ""),
                "kind": parsed.get("kind", ""),
                "future": bool(parsed.get("is_future")),
                "ambiguous": bool(parsed.get("ambiguous")),
            }
            if parsed.get("kind") == "current_marker":
                note["note"] = "Current marker in chronology"
            elif parsed.get("is_future"):
                note["note"] = "Parsed as future date; verify chronology"
            elif parsed.get("ambiguous"):
                note["note"] = "Ambiguous date format; not treated as future"
            else:
                note["note"] = "Parsed as past date"
            notes.append(note)
            if len(notes) >= max_notes:
                return notes
    return notes


def anonymize_resume_text(cv_text):
    text = str(cv_text or "")
    text = re.sub(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.+-])", "[REDACTED_EMAIL]", text)
    text = re.sub(
        r"(?:(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-]?)?\d{3,4}[\s-]?\d{3,4})",
        "[REDACTED_PHONE]",
        text,
    )
    address_label = re.compile(r"^\s*(present\s+address|current\s+address|home\s+address|address)\s*[:\-]\s*(.+)$", re.I)
    address_markers = (
        "street", "st.", "road", "rd.", "lane", "ln.", "sector", "block", "flat", "apartment",
        "apt", "house", "h no", "h.no", "pincode", "pin", "zip", "district", "nagar", "colony",
        "phase", "layout", "plot", "near ", "opp", "opposite", "village", "mandal"
    )
    cleaned_lines = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        label_match = address_label.match(line)
        if label_match:
            cleaned_lines.append(f"{label_match.group(1)}: [REDACTED_ADDRESS]")
            continue
        line_l = line.lower()
        looks_like_address = (
            len(line) < 160
            and any(marker in line_l for marker in address_markers)
            and re.search(r"\d", line)
            and not re.search(r"\b(experience|project|company|education|skills|contact|email|phone)\b", line_l)
        )
        if looks_like_address:
            cleaned_lines.append("[REDACTED_ADDRESS]")
        else:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _build_prompt(jd_text, cv_text, candidate_name="", target_job_title="", parsed_jd=None, parsed_candidate=None):
    explicit_experience_hint = ""
    must_have_skills = []
    must_have_text = ""
    raw_cv_text = str(cv_text or "")
    raw_jd_text = str(jd_text or "")
    cv_truncated = len(raw_cv_text) > 18000
    jd_truncated = len(raw_jd_text) > 15000
    cv_safe_text = _safe_text(raw_cv_text, 18000)
    jd_safe_text = _safe_text(raw_jd_text, 15000)
    resume_date_notes = extract_resume_date_notes(raw_cv_text)
    if isinstance(parsed_candidate, dict):
        explicit_experience_hint = (
            parsed_candidate.get("experience_years")
            or parsed_candidate.get("total_experience_years")
            or parsed_candidate.get("total_experience")
            or parsed_candidate.get("experience")
            or ""
        )
    recruiter_relaxations = {}
    industry_context = {}
    if isinstance(parsed_jd, dict):
        recruiter_relaxations = parsed_jd.get("recruiter_relaxations") or {}
        industry_context = parsed_jd.get("industry_context") or {}
        must_have_skills = parsed_jd.get("must_have_skills") or []
        if isinstance(must_have_skills, str):
            must_have_skills = [item.strip() for item in re.split(r"[,\n;]+", must_have_skills) if item.strip()]
        if isinstance(must_have_skills, list):
            must_have_skills = [str(item).strip() for item in must_have_skills if str(item).strip()]
        if must_have_skills:
            must_have_text = "\n".join(f"- {skill}" for skill in must_have_skills)
    context = {
        "candidate_name_hint": candidate_name or "",
        "target_job_title_hint": target_job_title or "",
        "parsed_jd": parsed_jd or {},
        "parsed_candidate": parsed_candidate or {},
        "explicit_total_experience_hint": explicit_experience_hint,
        "industry_context": industry_context,
        "recruiter_relaxations": recruiter_relaxations,
        "must_have_skills": must_have_skills,
        "screening_context": (parsed_jd or {}).get("screening_context") if isinstance(parsed_jd, dict) else {},
    }
    return (
        "### SCORING RULES\n"
        "Analyze the candidate resume against the job description and produce the screening report using the schema.\n"
        "Score the candidate fairly using the same evidence. The numeric score must be from 0 to 100.\n"
        "Use the ATS verdict bands (Strong Match, Moderate Match, Weak Match, Reject / Not Recommended) only as labels derived from the score.\n"
        "Keep the score breakdown simple and tied to evidence in the JD and CV.\n\n"
        "### EXPERIENCE RULES\n"
        "Prefer the explicit total experience stated in the resume or candidate context if it is available.\n"
        "Do not reduce total experience just because the most recent job is short or the work-history dates are incomplete.\n"
        "If the CV explicitly states total experience, use that as the primary source and use date arithmetic only as a backup.\n"
        "If the resume and candidate context conflict on experience, call it out in red_flags or concerns instead of silently picking the smaller number.\n"
        "If the candidate is clearly overqualified or underqualified for the role level, call that out as a level-fit issue.\n\n"
        "### INDUSTRY & RELAXATION RULES\n"
        "Treat the recruiter-provided industry context and relaxation rules as the final screening frame for this run.\n"
        "Use the industry context to decide whether the candidate is same-industry, adjacent, or unrelated.\n"
        "If the industry rule is Required, prefer same-industry candidates strongly.\n"
        "If it is Preferred, give partial credit to adjacent industries that the recruiter listed as acceptable.\n"
        "If it is Flexible, do not reject the candidate only because the industry is adjacent.\n"
        "Use recruiter relaxations to soften or waive a requirement only when the recruiter explicitly allows it.\n"
        "If a field is marked as relaxed or flexible, do not penalize the candidate for missing that item; mention it only as a note if needed.\n"
        "If the recruiter marks something as a non-negotiable, keep it as a hard filter even if other items are relaxed.\n"
        "If the recruiter relaxed the industry requirement, experience threshold, location, notice period, or one of the listed skills, apply that relaxation in the score and explain it briefly in the report.\n"
        "If the recruiter provided notes or examples in the screening context, use them to make the report more practical.\n\n"
        "### STRUCTURED FINDINGS\n"
        "Populate keyword_stuffing_flags with one entry per suspicious skill claim that is not backed by work-history evidence.\n"
        "For each entry, say where the skill was claimed, whether evidence was found, and whether it is Verified, Unverified, or Likely Stuffed.\n"
        "Populate ai_experience with a structured assessment if the candidate claims AI experience or AI-adjacent experience.\n"
        "Use evidence_type values exactly as: None, Tool User Only, Applied AI, Built AI Systems.\n"
        "If the candidate only used ChatGPT or Copilot to help write code, mark is_inflated true and evidence_type as Tool User Only.\n"
        "green_flags should contain concise positive signals about the candidate's fit.\n"
        "red_flags should contain concise risks, gaps, or uncertainties that matter for the recruiter.\n"
        "strengths should contain verified evidence-backed strengths.\n"
        "concerns should contain the main reasons to be careful.\n"
        "Avoid copying the exact same sentence into all four lists; each list should have a distinct purpose.\n"
        "Generate 1 to 3 screening questions for strong matches and 3 to 5 screening questions when there are more gaps or risks.\n"
        "Every question must map to a specific red flag, uncertainty, or must-have skill gap. Do not add filler questions.\n"
        "Use the following MUST-HAVE SKILLS list from the JD as the authoritative list for matched_must_have_skills and missing_must_have_skills.\n"
        "Only use these exact skill names for that output field. Do not invent new must-have skills.\n"
        "If the recruiter relaxation notes say a must-have is flexible or waived, treat that skill as relaxed and mention it in the report.\n"
        f"MUST-HAVE SKILLS:\n{must_have_text or '- None explicitly provided in parsed JD.'}\n\n"
        "### WEIGHTED SCORE PLAN\n"
        f"{SCORE_WEIGHT_PROMPT_TEXT}\n\n"
        "### INPUT DATA GUIDE\n"
        "Context JSON fields:\n"
        "- candidate_name_hint: candidate name if already known\n"
        "- target_job_title_hint: target job title if already known\n"
        "- parsed_jd: parsed JD structure including must-have skills, industry context, and relaxations\n"
        "- parsed_candidate: parsed candidate structure and experience hints\n"
        "- resume_date_notes: parser notes for any chronology/date ambiguity in the resume\n"
        "- explicit_total_experience_hint: recruiter-visible experience hint if available\n"
        "- industry_context: recruiter-provided industry framing\n"
        "- recruiter_relaxations: recruiter-approved relaxations and non-negotiables\n"
        "- screening_context: additional recruiter notes\n"
        f"Context JSON: {json.dumps(context, ensure_ascii=False)}\n\n"
        "### DATE INTERPRETATION NOTES\n"
        f"{json.dumps(resume_date_notes, ensure_ascii=False)}\n\n"
        "Only call a start date future if the parser notes it as future=True and the parsed date is actually after today's date.\n"
        "If a date format is ambiguous, say 'unverified chronology' instead of future date.\n"
        "For numeric dates like 16-09-2024, interpret them as a real calendar date and do not label them future unless they truly are.\n\n"
        "### JOB DESCRIPTION TEXT\n"
        f"{('[NOTE: JD was truncated to fit context limits.]\\n' if jd_truncated else '')}{jd_safe_text}\n\n"
        "### CANDIDATE RESUME TEXT\n"
        f"{('[NOTE: Resume was truncated to fit context limits.]\\n' if cv_truncated else '')}{cv_safe_text}\n"
    )


def _is_retryable_gemini_error(error):
    message = str(error or "")
    retry_signals = (
        "503",
        "429",
        "UNAVAILABLE",
        "RESOURCE_EXHAUSTED",
        "DEADLINE_EXCEEDED",
        "ReadTimeout",
        "ConnectTimeout",
        "ConnectionError",
        "temporarily unavailable",
        "high demand",
    )
    return any(signal.lower() in message.lower() for signal in retry_signals)


def _backoff_config_for_error(error):
    message = str(error or "")
    if "503" in message or "UNAVAILABLE" in message or "temporarily unavailable" in message or "high demand" in message:
        try:
            base_delay = float(os.getenv("GEMINI_503_BASE_DELAY_SECONDS", "5.0") or 5.0)
        except Exception:
            base_delay = 5.0
        try:
            max_delay = float(os.getenv("GEMINI_503_MAX_DELAY_SECONDS", "60.0") or 60.0)
        except Exception:
            max_delay = 60.0
        return max(1.0, base_delay), max(base_delay, max_delay)
    try:
        base_delay = float(os.getenv("GEMINI_RETRY_BASE_DELAY_SECONDS", "2.0") or 2.0)
    except Exception:
        base_delay = 2.0
    try:
        max_delay = float(os.getenv("GEMINI_RETRY_MAX_DELAY_SECONDS", "30.0") or 30.0)
    except Exception:
        max_delay = 30.0
    return max(1.0, base_delay), max(base_delay, max_delay)


def _sleep_backoff(attempt, error=None, base_delay=None, max_delay=None):
    if base_delay is None or max_delay is None:
        config_base, config_max = _backoff_config_for_error(error)
        base_delay = config_base if base_delay is None else base_delay
        max_delay = config_max if max_delay is None else max_delay
    delay = min(max_delay, base_delay * (2 ** max(0, attempt - 1)))
    jitter = delay * 0.2
    time.sleep(delay + random.uniform(0, jitter))


def _gemini_circuit_cooldown_seconds():
    try:
        return max(15, int(float(os.getenv("GEMINI_CIRCUIT_COOLDOWN_SECONDS", "120") or 120)))
    except Exception:
        return 120


def _gemini_circuit_state_file_path():
    return GEMINI_CIRCUIT_STATE_PATH


def _read_gemini_circuit_state():
    path = _gemini_circuit_state_file_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle) or {}
    except FileNotFoundError:
        return {"open_until": 0.0, "reason": ""}
    except Exception:
        return {"open_until": 0.0, "reason": ""}
    try:
        open_until = float(payload.get("open_until") or 0.0)
    except Exception:
        open_until = 0.0
    reason = str(payload.get("reason") or "").strip()
    if open_until and time.time() >= open_until:
        return {"open_until": 0.0, "reason": ""}
    return {"open_until": open_until, "reason": reason}


def _write_gemini_circuit_state(open_until, reason=""):
    path = _gemini_circuit_state_file_path()
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    payload = {
        "open_until": float(open_until or 0.0),
        "reason": str(reason or "").strip(),
        "updated_at": time.time(),
    }
    tmp_path = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _clear_gemini_circuit_state_file():
    path = _gemini_circuit_state_file_path()
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _gemini_circuit_is_open():
    state = _read_gemini_circuit_state()
    return bool(state.get("open_until") and time.time() < float(state.get("open_until") or 0.0))


def _trip_gemini_circuit(reason, retry_after_seconds=None):
    global GEMINI_CIRCUIT_OPEN_UNTIL, GEMINI_CIRCUIT_REASON
    base = _gemini_circuit_cooldown_seconds()
    retry_after_seconds = int(float(retry_after_seconds or 0) or 0) if retry_after_seconds else 0
    cooldown = max(base, retry_after_seconds)
    GEMINI_CIRCUIT_OPEN_UNTIL = time.time() + cooldown
    GEMINI_CIRCUIT_REASON = str(reason or "").strip()
    with GEMINI_CIRCUIT_STATE_LOCK:
        _write_gemini_circuit_state(GEMINI_CIRCUIT_OPEN_UNTIL, GEMINI_CIRCUIT_REASON)
    print(
        f"Gemini screening circuit breaker tripped for {cooldown}s: {GEMINI_CIRCUIT_REASON or 'quota/availability issue'}",
        flush=True,
    )


def _clear_gemini_circuit_if_expired():
    global GEMINI_CIRCUIT_OPEN_UNTIL, GEMINI_CIRCUIT_REASON
    state = _read_gemini_circuit_state()
    open_until = float(state.get("open_until") or 0.0)
    reason = str(state.get("reason") or "").strip()
    if open_until and time.time() >= open_until:
        GEMINI_CIRCUIT_OPEN_UNTIL = 0.0
        GEMINI_CIRCUIT_REASON = ""
        with GEMINI_CIRCUIT_STATE_LOCK:
            _clear_gemini_circuit_state_file()
    else:
        GEMINI_CIRCUIT_OPEN_UNTIL = open_until
        GEMINI_CIRCUIT_REASON = reason


def _extract_retry_after_seconds(error):
    text = str(error or "")
    patterns = [
        r"retry in\s+([0-9]+(?:\.[0-9]+)?)s",
        r"retryDelay['\"]?\s*:\s*['\"]?([0-9]+(?:\.[0-9]+)?)s",
        r"Please retry in\s+([0-9]+(?:\.[0-9]+)?)s",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            try:
                return float(match.group(1))
            except Exception:
                continue
    return 0.0


def _extract_usage_metadata(response):
    usage = getattr(response, "usage_metadata", None)
    if not usage:
        usage = getattr(response, "usageMetadata", None)
    if not usage:
        return {}
    fields = (
        "prompt_token_count",
        "candidates_token_count",
        "total_token_count",
        "cached_content_token_count",
        "thoughts_token_count",
    )
    payload = {}
    for field in fields:
        value = getattr(usage, field, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(field)
        if value is not None:
            try:
                payload[field] = int(value)
            except Exception:
                payload[field] = value
    return payload


def _try_acquire_screening_slot():
    return GEMINI_SCREENING_ACTIVE_SEMAPHORE.acquire(blocking=False)


def _release_screening_slot():
    try:
        GEMINI_SCREENING_ACTIVE_SEMAPHORE.release()
    except Exception:
        pass


def _is_quota_or_rate_limit_error(error):
    text = str(error or "")
    signals = (
        "429",
        "RESOURCE_EXHAUSTED",
        "quota exceeded",
        "rate limit",
        "too many requests",
        "generate_content_free_tier_requests",
    )
    return any(signal.lower() in text.lower() for signal in signals)


def _classify_error(error):
    text = str(error or "")
    lowered = text.lower()
    if "503" in text or "UNAVAILABLE" in text or "temporarily unavailable" in lowered or "high demand" in lowered:
        return "capacity_unavailable"
    if _is_quota_or_rate_limit_error(error):
        return "quota_rate_limit"
    if "401" in text or "api_key" in lowered or "unauthorized" in lowered:
        return "auth_error"
    if "400" in text or "invalid" in lowered or "schema" in lowered:
        return "bad_request"
    return "unknown"


def _get_model_sequence():
    primary = GEMINI_MODEL_PRIMARY
    fallback = GEMINI_MODEL_FALLBACK
    if primary == fallback:
        return [primary]
    return [primary, fallback]


def build_screening_report(
    jd_text,
    cv_text,
    candidate_name="",
    target_job_title="",
    parsed_jd=None,
    parsed_candidate=None,
    api_key=None,
):
    api_key = str(api_key or os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return {"ok": False, "error": "GEMINI_API_KEY is not configured.", "source": "gemini"}
    if not _try_acquire_screening_slot():
        return {
            "ok": False,
            "error": f"Gemini screening is busy. Only {GEMINI_SCREENING_ACTIVE_LIMIT} screening runs can execute at once. Please try again in a moment.",
            "source": "gemini",
            "concurrency_limited": True,
            "active_limit": GEMINI_SCREENING_ACTIVE_LIMIT,
        }
    _clear_gemini_circuit_if_expired()
    if _gemini_circuit_is_open():
        _release_screening_slot()
        circuit_state = _read_gemini_circuit_state()
        wait_seconds = max(0, int(round(float(circuit_state.get("open_until") or 0.0) - time.time())))
        reason = circuit_state.get("reason") or "quota or rate limit"
        return {
            "ok": False,
            "error": f"Gemini screening temporarily paused for {wait_seconds}s after {reason}.",
            "source": "gemini",
            "circuit_breaker": True,
            "retry_after_seconds": wait_seconds,
        }

    try:
        client = genai.Client(api_key=api_key)
        prompt = _build_prompt(
            jd_text,
            anonymize_resume_text(cv_text),
            candidate_name=candidate_name,
            target_job_title=target_job_title,
            parsed_jd=parsed_jd,
            parsed_candidate=parsed_candidate,
        )
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_json_schema=ScreeningReport.model_json_schema(),
            temperature=0.2,
        )
        response = None
        last_error = None
        last_error_type = "unknown"
        models_to_try = _get_model_sequence()
        max_attempts_default = max(1, int(os.getenv("GEMINI_RETRY_ATTEMPTS", "3") or 3))
        max_attempts_503 = max(max_attempts_default, int(os.getenv("GEMINI_RETRY_ATTEMPTS_503", "5") or 5))
        max_attempts_cap = max(max_attempts_default, max_attempts_503)
        used_model_name = models_to_try[0]

        for model_index, model_name in enumerate(models_to_try):
            response = None
            last_error = None
            last_error_type = "unknown"
            for attempt in range(1, max_attempts_cap + 1):
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=config,
                    )
                    last_error = None
                    used_model_name = model_name
                    break
                except Exception as e:
                    last_error = e
                    last_error_type = _classify_error(e)
                    attempt_limit = max_attempts_503 if last_error_type == "capacity_unavailable" else max_attempts_default
                    if attempt >= attempt_limit or not _is_retryable_gemini_error(e):
                        if last_error_type == "capacity_unavailable" and model_index < len(models_to_try) - 1:
                            print(
                                f"Gemini screening model {model_name} hit capacity; switching to fallback model {models_to_try[model_index + 1]}.",
                                flush=True,
                            )
                            response = None
                            break
                        raise
                    print(f"Gemini screening retry {attempt}/{attempt_limit} after error: {e}")
                    _sleep_backoff(attempt, error=e)
            if response is not None:
                break
            if last_error_type != "capacity_unavailable" or model_index >= len(models_to_try) - 1:
                break

        if response is None:
            if last_error is not None:
                error_type = _classify_error(last_error)
                retryable = error_type in ("capacity_unavailable", "quota_rate_limit")
                if error_type == "quota_rate_limit":
                    retry_after_seconds = _extract_retry_after_seconds(last_error)
                    _trip_gemini_circuit(last_error, retry_after_seconds=retry_after_seconds)
                    circuit_state = _read_gemini_circuit_state()
                    wait_seconds = max(0, int(round(float(circuit_state.get("open_until") or 0.0) - time.time())))
                    return {
                        "ok": False,
                        "error": f"Gemini screening temporarily paused for {wait_seconds}s after quota/rate-limit exhaustion.",
                        "source": "gemini",
                        "circuit_breaker": True,
                        "retry_after_seconds": wait_seconds,
                        "error_type": error_type,
                        "retryable": retryable,
                    }
                if error_type == "capacity_unavailable":
                    return {
                        "ok": False,
                        "error": "Gemini is under high load. The screening will be retried automatically.",
                        "source": "gemini",
                        "error_type": error_type,
                        "retryable": True,
                        "model": used_model_name,
                    }
                return {
                    "ok": False,
                    "error": f"Gemini screening request failed: {last_error}",
                    "source": "gemini",
                    "error_type": error_type,
                    "retryable": False,
                    "model": used_model_name,
                }
            raise RuntimeError("Gemini screening returned no response.")
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, ScreeningReport):
            report = parsed.model_dump()
        elif isinstance(parsed, dict):
            report = ScreeningReport.model_validate(parsed).model_dump()
        else:
            raw_text = getattr(response, "text", "") or ""
            report = ScreeningReport.model_validate_json(raw_text).model_dump()
        usage_metadata = _extract_usage_metadata(response)
        report = normalize_score_breakdown(report)
        return {
            "ok": True,
            "source": "gemini",
            "model": used_model_name,
            "report": report,
            "usage_metadata": usage_metadata,
        }
    except ImportError as e:
        return {"ok": False, "error": f"Gemini SDK dependencies are missing: {e}", "source": "gemini", "error_type": "import_error", "retryable": False}
    except ValidationError as e:
        return {"ok": False, "error": f"Gemini response did not match schema: {e}", "source": "gemini", "error_type": "bad_request", "retryable": False}
    except Exception as e:
        error_type = _classify_error(e)
        retryable = error_type in ("capacity_unavailable", "quota_rate_limit")
        if error_type == "quota_rate_limit":
            retry_after_seconds = _extract_retry_after_seconds(e)
            _trip_gemini_circuit(e, retry_after_seconds=retry_after_seconds)
            circuit_state = _read_gemini_circuit_state()
            wait_seconds = max(0, int(round(float(circuit_state.get("open_until") or 0.0) - time.time())))
            return {
                "ok": False,
                "error": f"Gemini screening temporarily paused for {wait_seconds}s after quota/rate-limit exhaustion.",
                "source": "gemini",
                "circuit_breaker": True,
                "retry_after_seconds": wait_seconds,
                "error_type": error_type,
                "retryable": retryable,
            }
        if error_type == "capacity_unavailable":
            return {
                "ok": False,
                "error": "Gemini is under high load. The screening will be retried automatically.",
                "source": "gemini",
                "error_type": error_type,
                "retryable": True,
            }
        return {"ok": False, "error": f"Gemini screening request failed: {e}", "source": "gemini", "error_type": error_type, "retryable": retryable}
    finally:
        _release_screening_slot()


def build_screening_reports_batch(items, delay_seconds=0.0, api_key=None):
    if not items:
        return []

    def _run(index, item):
        result = build_screening_report(
            item.get("jd_text", ""),
            item.get("cv_text", ""),
            candidate_name=item.get("candidate_name", ""),
            target_job_title=item.get("target_job_title", ""),
            parsed_jd=item.get("parsed_jd") or {},
            parsed_candidate=item.get("parsed_candidate") or {},
            api_key=item.get("api_key") or api_key,
        )
        result["index"] = index
        return result

    results = [None] * len(items)
    max_workers = max(1, min(len(items), GEMINI_SCREENING_ACTIVE_LIMIT))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_index = {}
        for index, item in enumerate(items):
            future = executor.submit(_run, index, item)
            future_to_index[future] = index
            if delay_seconds and index < len(items) - 1:
                time.sleep(max(0.0, float(delay_seconds)))
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                results[index] = future.result()
            except Exception as exc:
                results[index] = {
                    "ok": False,
                    "source": "gemini",
                    "error": f"Gemini batch screening failed: {type(exc).__name__}: {exc}",
                    "index": index,
                }
    return results
