import hashlib
import json
import os
import re
import time
from datetime import date

import requests

from domain_taxonomy import infer_domain_taxonomy, primary_domain
from embedding_engine import cosine_similarity, generate_embedding
from explainability import build_explainability
from hard_filters import evaluate_hard_filters
from role_taxonomy import infer_role_taxonomy, infer_seniority, normalize_role_title, primary_role_category
from role_profiles import detect_role_profile
from scoring_engine import deterministic_structured_score
from skill_aliases import canonical_skill, extract_skills, unique_list, weighted_skills
from taxonomy_core import build_taxonomy_bundle


GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or "").strip()
PARSE_LLM_PROVIDER = "gemini" if GEMINI_API_KEY else "deterministic"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")
LLM_API_BASE = os.getenv("LLM_API_BASE", "http://localhost:11434").rstrip("/")
GEMINI_PARSE_MODEL = os.getenv("GEMINI_PARSE_MODEL", "gemini-2.5-flash")
MATCH_PIPELINE_VERSION = "hybrid-v10-gemini-scoring"
GEMINI_PARSE_TIMEOUT = float(os.getenv("GEMINI_PARSE_TIMEOUT", "20"))
GEMINI_PARSE_RETRY_ATTEMPTS = int(os.getenv("GEMINI_PARSE_RETRY_ATTEMPTS", "3") or 3)
LLM_PARSE_TIMEOUT = float(os.getenv("LLM_PARSE_TIMEOUT", "8"))
_LLM_PARSE_AVAILABLE = None
_LLM_PARSE_LAST_FAIL = 0


def debug_match(message):
    if os.getenv("MATCH_DEBUG", "1").strip().lower() not in {"0", "false", "no", "off"}:
        print(f"MATCH DEBUG: {message}", flush=True)


def text_hash(text):
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def versioned_text_hash(text):
    return text_hash(f"{MATCH_PIPELINE_VERSION}:{text or ''}")


def clean_value(value, limit=120):
    return re.sub(r"\s+", " ", str(value or "")).strip(" -:|,\t\r\n")[:limit]


def extract_year_range(text):
    text_l = (text or "").lower()
    collapsed = re.sub(r"\s+", " ", text_l)
    ranges = re.findall(
        r"(?<!\d)(\d{1,2}(?:\.\d)?)\s*(?:-|to)\s*(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\b.{0,45}\bexp(?:erience)?\b",
        collapsed
    )
    if not ranges:
        ranges = re.findall(
            r"\bexp(?:erience)?\b.{0,45}(?<!\d)(\d{1,2}(?:\.\d)?)\s*(?:-|to)\s*(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\b",
            collapsed
        )
    if ranges:
        a, b = ranges[0]
        return {"min_years": float(a), "max_years": float(b)}
    singles = re.findall(
        r"(?<!\d)(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\b.{0,45}\bexp(?:erience)?\b",
        collapsed
    )
    if not singles:
        singles = re.findall(
            r"\bexp(?:erience)?\b.{0,45}(?<!\d)(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\b",
            collapsed
        )
    if singles:
        return {"min_years": float(singles[0]), "max_years": 0}
    return {"min_years": 0, "max_years": 0}


def extract_role_title(text):
    lines = [clean_value(line) for line in (text or "").splitlines() if clean_value(line)]
    patterns = [
        r"(?:job\s*title|role\s*title|position\s*title|position|designation)\s*[:\-]\s*(.+)",
        r"(?:requirement)\s*[:\-]\s*(.+)",
        r"(?:hiring\s+for|opening\s+for)\s*[:\-]?\s*(.+)",
        r"(?:job\s+description\s+(?:for|of)|jd\s+(?:for|of))\s*[:\-]?\s*(.+)",
    ]
    collapsed = re.sub(r"\s+", " ", text or "")
    if re.search(r"\b(senior\s+principal\s+software\s+architect|principal\s+software\s+architect)\b|software\s*architect", collapsed, re.I):
        if re.search(r"\bsenior\s+principal\b", collapsed, re.I):
            return "Senior Principal Software Architect"
        if re.search(r"\bprincipal\b", collapsed, re.I):
            return "Principal Software Architect"
        return "Software Architect"
    multiline_patterns = [
        r"job\s+description\s+of\s+([A-Za-z0-9 .+#/&-]{4,80})",
        r"requirement\s*[-:]\s*([A-Za-z0-9 .+#/&-]{4,80}?)\s+(?:location|interview|working|jd)\b",
        r"\bThe\s+([A-Z][A-Za-z0-9 .+#/&-]{2,50}(?:Developer|Engineer|Manager|Administrator|Analyst|Consultant|Associate|Director|Executive|Specialist))\s+(?:builds|provides|develops|designs|manages|leads|is responsible)\b",
    ]
    for pattern in multiline_patterns:
        match = re.search(pattern, collapsed, re.I)
        title = clean_value(match.group(1) if match else "", 80)
        if match and len(title.split()) <= 6 and not re.search(r"\b(about|team|consists|responsibilit|requirement|skills?|qualification|experience)\b", title, re.I):
            return normalize_jd_role_title(match.group(1))
    bad_title_words = re.compile(r"\b(about\s+us|company|overview|responsibilit|requirement|skills?|qualification|location|experience|salary|ctc|benefits|what\s+you)\b", re.I)
    for line in lines[:40]:
        for pattern in patterns:
            match = re.search(pattern, line, re.I)
            if match and not bad_title_words.search(match.group(1)):
                return normalize_jd_role_title(match.group(1))
    for line in lines[:18]:
        candidate = re.sub(r"^\s*(job\s+description|jd)\s*[:\-]\s*", "", line, flags=re.I)
        if len(candidate) <= 90 and primary_role_category(candidate) and not bad_title_words.search(candidate):
            if re.search(r"\b(manager|developer|engineer|admin|administrator|analyst|consultant|associate|director|executive|lead|architect|specialist|sales|finance|python|java|angular|active directory|business development)\b", candidate, re.I):
                return normalize_jd_role_title(candidate)
    return ""


def normalize_jd_role_title(value):
    text = clean_value(value, 120)
    text = re.sub(r"^role\s*\d+\s*[:\-]\s*", "", text, flags=re.I).strip()
    text = re.sub(r"\(.*?\)", "", text).strip()
    skills = []
    text_l = text.lower()
    if re.search(r"software\s*architect", text_l):
        if "senior" in text_l and "principal" in text_l:
            return "Senior Principal Software Architect"
        if "principal" in text_l:
            return "Principal Software Architect"
        return "Software Architect"
    for label, pattern in [
        ("C#", r"c#|c\s*sharp"),
        (".NET", r"\.net|dotnet"),
        ("Angular", r"angular"),
        ("Java", r"\bjava\b"),
        ("Python", r"\bpython\b"),
        ("Node.js", r"node(?:js|\.js)?"),
    ]:
        if re.search(pattern, text_l):
            skills.append(label)
    if re.search(r"full\s*stack|front\s*end|back\s*end|web", text_l):
        suffix = "Full Stack Developer" if "full" in text_l or ("front" in text_l and "back" in text_l) else "Web Developer"
        return clean_value(" ".join(unique_list(skills + [suffix])), 80)
    if skills:
        return clean_value(" ".join(unique_list(skills + ["Developer"])), 80)
    return text.title()


def extract_location(text):
    match = re.search(r"(?:location|job\s+location|work\s+location)\s*[:\-]\s*([A-Za-z0-9, /.-]{2,80})", text or "", re.I)
    if match:
        return clean_value(match.group(1), 80)
    cities = ["Bangalore", "Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Chennai", "Pune", "Noida", "Gurgaon", "Gurugram", "Kolkata", "Ahmedabad", "Remote"]
    text_l = (text or "").lower()
    return ", ".join(unique_list([city for city in cities if city.lower() in text_l]))


def extract_certifications(text):
    patterns = [
        r"\bAWS Certified [A-Za-z ]+",
        r"\bAzure [A-Za-z ]+",
        r"\bPMP\b",
        r"\bCSM\b",
        r"\bCISSP\b",
        r"\bCEH\b",
        r"\bISTQB\b",
        r"\bCCNA\b",
        r"\bITIL\b",
    ]
    certs = []
    for pattern in patterns:
        certs.extend(re.findall(pattern, text or "", re.I))
    return unique_list([c.upper() if len(c) <= 5 else clean_value(c) for c in certs], 10)


def extract_bullets(text):
    lines = [clean_value(line.strip(" -•*\t")) for line in (text or "").splitlines()]
    signals = ["responsible", "develop", "design", "manage", "build", "implement", "lead", "led", "support", "analyze", "maintain", "create", "owned", "delivered"]
    return unique_list([line for line in lines if 20 <= len(line) <= 180 and any(signal in line.lower() for signal in signals)], 10)


def split_must_nice_skills(text):
    text = text or ""
    all_skills = extract_skills(text)
    must, nice = [], []
    must_markers = ["must", "required", "mandatory", "should have", "need", "hands-on", "hands on", "strong experience", "experience in"]
    nice_markers = ["preferred", "nice to have", "good to have", "plus", "advantage", "optional", "added advantage", "desirable"]
    section_lines = important_jd_section_lines(text)
    for sentence in section_lines + re.split(r"[\n.;]", text):
        skills = extract_skills(sentence)
        sentence_l = sentence.lower()
        if any(marker in sentence_l for marker in nice_markers):
            nice.extend(skills)
        elif any(marker in sentence_l for marker in must_markers):
            must.extend(skills)
    for sentence in section_lines[:8]:
        sentence_l = sentence.lower()
        if re.search(r"\b(strong experience|hands[- ]?on experience|experience in|required|mandatory)\b", sentence_l):
            must.extend(extract_skills(sentence))
    if not must:
        must = all_skills[:8]
    if is_architect_jd(text):
        architect_must, architect_validate, architect_nice = architect_requirement_buckets(text)
        must = unique_list(architect_must + [s for s in must if s not in architect_validate], 16)
        nice.extend(architect_nice + architect_validate)
    nice.extend([skill for skill in all_skills if skill not in must])
    return clean_jd_skill_list(must, 12), clean_jd_skill_list(nice, 12)


def is_architect_jd(text):
    text_l = (text or "").lower()
    return bool(re.search(r"\b(software\s*architect|solution architect|principal architect|architect-level|architectural vision|architecture & technical strategy|system design & engineering leadership)\b", text_l))


def architect_requirement_buckets(text):
    skills = extract_skills(text)
    skill_set = set(skills)
    must = []
    for skill in [
        "Software Architecture", "Technical Leadership", "Distributed Systems",
        "System Architecture", "API Design", ".NET Core", ".NET",
        "REST API", "GraphQL", "gRPC", "Docker", "Kubernetes",
        "Cloud Platform", "Security Architecture", "Observability Tooling",
        "Fault Tolerance", "Resilience", "Performance Engineering"
    ]:
        if skill in skill_set:
            must.append(skill)
    if ".NET Core" in skill_set and ".NET" in must:
        must.remove(".NET")
    validate = []
    for skill in [
        "POC", "Architecture Reviews", "Architecture Roadmap",
        "Engineering Leadership", "Control Plane", "Policy Engine",
        "Configuration Management", "Domain Modeling", "Service Decomposition",
        "Operational Excellence"
    ]:
        if skill in skill_set:
            validate.append(skill)
    nice = []
    for skill in ["EDR", "XDR", "SOAR", "Cloud Security", "Secure-by-Design"]:
        if skill in skill_set:
            nice.append(skill)
    if not must:
        must = ["Software Architecture", "Technical Leadership", "Distributed Systems"]
    return clean_jd_skill_list(must, 16), clean_jd_skill_list(validate, 12), clean_jd_skill_list(nice, 12)


def important_jd_section_lines(text, lines_per_section=4):
    lines = [clean_value(line, 220) for line in (text or "").splitlines()]
    headings = re.compile(r"^(jd|job description|experience|requirements?|mandatory|must have|knowledge and skills|technical skills|what you need to bring|responsibilities)\s*:?\s*$", re.I)
    important = []
    for i, line in enumerate(lines):
        if headings.match(line):
            picked = 0
            for next_line in lines[i + 1:]:
                if not next_line:
                    continue
                if headings.match(next_line) and picked:
                    break
                important.append(next_line)
                picked += 1
                if picked >= lines_per_section:
                    break
    return important


def clean_jd_skill_list(skills, limit=12):
    blocked = {
        "Design", "Maintain Custom", "And Maintain Custom", "Develop Internal Tools",
        "Required", "Responsibilities", "Experience", "Knowledge", "Skills"
    }
    output = []
    for skill in skills or []:
        canonical = canonical_skill(skill)
        if not canonical or canonical in blocked:
            continue
        if len(canonical.split()) > 4 and canonical not in {"Software Composition Analysis"}:
            continue
        output.append(canonical)
    return unique_list(output, limit)


def _sleep_llm_backoff(attempt, base_delay=1.5, max_delay=8.0):
    delay = min(max_delay, base_delay * (2 ** max(0, attempt - 1)))
    time.sleep(delay)


def _is_retryable_llm_error(exc):
    message = f"{type(exc).__name__}: {exc}".lower()
    retry_signals = ("503", "429", "unavailable", "resource_exhausted", "deadline_exceeded", "timeout", "connect", "temporarily unavailable", "high demand")
    return any(signal in message for signal in retry_signals)


def _gemini_extract(kind, text):
    global _LLM_PARSE_AVAILABLE, _LLM_PARSE_LAST_FAIL
    if not GEMINI_API_KEY:
        debug_match(f"{kind} Gemini extraction skipped because GEMINI_API_KEY is missing; deterministic parser fallback is being used.")
        return {}
    if _LLM_PARSE_AVAILABLE is False and time.time() - _LLM_PARSE_LAST_FAIL > 60:
        _LLM_PARSE_AVAILABLE = None
    if _LLM_PARSE_AVAILABLE is False:
        debug_match(f"{kind} Gemini extraction unavailable from previous failure; deterministic parser fallback is being used.")
        return {}
    schema_hint = "job title, must skills, nice skills, experience range, location, domain" if kind == "jd" else "name, email, phone, links, roles, companies, date ranges, experience years, skills, education"
    prompt = (
        f"Extract only factual {kind} fields as compact JSON. No scoring, no recommendation, no ranking. "
        f"Fields to extract: {schema_hint}. Use empty values when absent.\n\n{text[:7000]}"
    )
    try:
        from google import genai
        from google.genai import types
    except Exception as e:
        debug_match(f"{kind} Gemini import failed ({type(e).__name__}: {e}); deterministic parser fallback is being used.")
        return {}
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        )
        response = None
        last_error = None
        for attempt in range(1, max(1, GEMINI_PARSE_RETRY_ATTEMPTS) + 1):
            try:
                response = client.models.generate_content(
                    model=GEMINI_PARSE_MODEL,
                    contents=prompt,
                    config=config,
                )
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt >= max(1, GEMINI_PARSE_RETRY_ATTEMPTS) or not _is_retryable_llm_error(exc):
                    raise
                debug_match(f"{kind} Gemini extraction retry {attempt}/{GEMINI_PARSE_RETRY_ATTEMPTS} after error: {exc}")
                _sleep_llm_backoff(attempt)
        if last_error is not None and response is None:
            raise last_error
        raw = getattr(response, "text", "") or "{}"
        parsed = json.loads(raw)
        _LLM_PARSE_AVAILABLE = True
        return parsed if isinstance(parsed, dict) else {}
    except Exception as exc:
        debug_match(f"{kind} Gemini extraction failed ({type(exc).__name__}: {exc}); deterministic parser fallback is being used.")
        _LLM_PARSE_AVAILABLE = False
        _LLM_PARSE_LAST_FAIL = time.time()
        return {}


def llm_extract(kind, text):
    global _LLM_PARSE_AVAILABLE, _LLM_PARSE_LAST_FAIL
    provider = (PARSE_LLM_PROVIDER or "").lower()
    if provider == "gemini":
        return _gemini_extract(kind, text)
    if provider not in {"gemini", "openrouter", "local", "api"}:
        debug_match(f"{kind} parser extraction skipped because PARSE_LLM_PROVIDER={PARSE_LLM_PROVIDER}; deterministic parser fallback is being used.")
        return {}
    if _LLM_PARSE_AVAILABLE is False and time.time() - _LLM_PARSE_LAST_FAIL > 60:
        _LLM_PARSE_AVAILABLE = None
    if _LLM_PARSE_AVAILABLE is False:
        debug_match(f"{kind} LLM extraction unavailable from previous failure; deterministic parser fallback is being used.")
        return {}
    schema_hint = "job title, must skills, nice skills, experience range, location, domain" if kind == "jd" else "name, email, phone, links, roles, companies, date ranges, skills, education"
    prompt = (
        f"Extract only factual {kind} fields as compact JSON. No scoring, no recommendation, no ranking. "
        f"Fields to extract: {schema_hint}. Use empty values when absent.\n\n{text[:7000]}"
    )
    try:
        response = requests.post(
            f"{LLM_API_BASE}/api/generate",
            json={"model": LLM_MODEL, "prompt": prompt, "format": "json", "stream": False},
            timeout=LLM_PARSE_TIMEOUT
        )
        response.raise_for_status()
        raw = response.json().get("response") or "{}"
        parsed = json.loads(raw)
        _LLM_PARSE_AVAILABLE = True
        return parsed if isinstance(parsed, dict) else {}
    except Exception as exc:
        debug_match(f"{kind} parser extraction failed ({type(exc).__name__}: {exc}); deterministic parser fallback is being used.")
        _LLM_PARSE_AVAILABLE = False
        _LLM_PARSE_LAST_FAIL = time.time()
        return {}


def parse_jd(jd_text):
    llm = llm_extract("jd", jd_text)
    parser_warnings = []
    parse_source = "llm" if llm else "deterministic"
    if not llm:
        debug_match("JD deterministic parsing fallback is being used.")
        parser_warnings.append("JD parsed with deterministic fallback because LLM extraction was unavailable.")
    role_title = clean_value(llm.get("role_title") or llm.get("job_title") or extract_role_title(jd_text), 80)
    deterministic_must, deterministic_nice = split_must_nice_skills(jd_text)
    llm_must = [canonical_skill(s) for s in llm.get("must_have_skills", []) if canonical_skill(s)]
    llm_nice = [canonical_skill(s) for s in llm.get("nice_to_have_skills", []) if canonical_skill(s)]
    title_skills = extract_skills(role_title)
    must = clean_jd_skill_list(title_skills + llm_must + deterministic_must, 14)
    nice = clean_jd_skill_list(llm_nice + [s for s in deterministic_nice if s not in must], 14)
    validation_evidence = []
    parser_notes = []
    if is_architect_jd(jd_text):
        architect_must, architect_validate, architect_nice = architect_requirement_buckets(jd_text)
        must = clean_jd_skill_list(title_skills + architect_must + [s for s in must if s not in architect_validate and s != "POC"], 16)
        validation_evidence = architect_validate
        nice = clean_jd_skill_list(architect_nice + [s for s in nice if s not in must and s not in validation_evidence], 16)
        if not role_title:
            role_title = "Senior Principal Software Architect" if re.search(r"senior\s+principal", jd_text, re.I) else "Software Architect"
        parser_notes.append("Architect JD detected: POC/roadmap/reviews/mentoring are treated as validation evidence, not hard must-have skills.")
    if not role_title:
        parser_warnings.append("JD role title was not confidently extracted.")
    if len(must) < 3:
        parser_warnings.append("JD has fewer than 3 confident must-have skills; recruiter validation is recommended.")
    if len(re.findall(r"\w+", jd_text or "")) < 70:
        parser_warnings.append("JD text is sparse; role or skill extraction may need manual validation.")
    manual_review_reasons = []
    if parse_source == "deterministic":
        manual_review_reasons.append("JD required deterministic fallback.")
    if not role_title:
        manual_review_reasons.append("JD role title was not confidently extracted.")
    if len(must) < 3:
        manual_review_reasons.append("JD has fewer than 3 confident must-have skills.")
    if len(re.findall(r"\w+", jd_text or "")) < 70:
        manual_review_reasons.append("JD text is sparse and may need manual validation.")
    text_for_taxonomy = "\n".join([role_title, jd_text or ""])
    role_taxonomy = infer_role_taxonomy(text_for_taxonomy)
    domain_taxonomy = infer_domain_taxonomy(jd_text)
    seniority = infer_seniority(text_for_taxonomy, (extract_year_range(jd_text).get("min_years") or 0))
    taxonomy = build_taxonomy_bundle(
        text_for_taxonomy,
        skills=must + nice,
        years=extract_year_range(jd_text).get("min_years") or 0
    )
    parsed = {
        "id": text_hash(jd_text)[:12],
        "role_title": role_title,
        "title": role_title,
        "primary_role": role_taxonomy[0]["role"] if role_taxonomy else "",
        "role_category": role_taxonomy[0]["role"] if role_taxonomy else "",
        "employment_type": infer_employment_type(jd_text),
        "experience_required": extract_year_range(jd_text),
        "must_have_skills": must,
        "nice_to_have_skills": nice,
        "validation_evidence": validation_evidence,
        "parser_notes": parser_notes,
        "parser_confidence": "high" if role_title and len(must) >= 3 else "medium" if role_title or must else "low",
        "parse_source": parse_source,
        "parser_warnings": unique_list(parser_warnings + parser_notes, 10),
        "manual_review_required": bool(manual_review_reasons),
        "manual_review_reasons": unique_list(manual_review_reasons, 8),
        "tools_technologies": unique_list(extract_skills(jd_text), 20),
        "domain": domain_taxonomy[0]["domain"] if domain_taxonomy else "",
        "sub_domain": "",
        "responsibilities": extract_bullets(jd_text),
        "seniority_level": seniority,
        "certifications_required": extract_certifications(jd_text),
        "location": clean_value(llm.get("location") or extract_location(jd_text), 80),
        "keywords_expanded": unique_list(must + nice + [role_taxonomy[0]["role"] if role_taxonomy else ""], 30),
        "must_have_skills_weighted": weighted_skills(jd_text, must, default_weight=80),
        "role_taxonomy": role_taxonomy,
        "domain_taxonomy": domain_taxonomy,
        "taxonomy": taxonomy,
        "role_family": taxonomy.get("primary_role_family", ""),
        "domain_family": taxonomy.get("primary_domain_family", ""),
        "seniority_family": taxonomy.get("seniority", ""),
        "skill_family_match": taxonomy.get("skill_family_match", {}),
        "embedding_keywords": unique_list(must + nice + [role_title, primary_domain(jd_text)], 35),
        "embedding_vector": [],
        "confidence_scores": {
            "skills": 0.88 if must else 0.45,
            "role": role_taxonomy[0]["confidence"] if role_taxonomy else 0.35,
            "domain": domain_taxonomy[0]["confidence"] if domain_taxonomy else 0.3,
            "experience": 0.85 if extract_year_range(jd_text).get("min_years") else 0.35
        }
    }
    role_profile = detect_role_profile(parsed)
    if role_profile:
        parsed["role_profile"] = role_profile
    return parsed


def infer_employment_type(text):
    text_l = (text or "").lower()
    if "contract" in text_l:
        return "Contract"
    if "part time" in text_l or "part-time" in text_l:
        return "Part-time"
    if "full time" in text_l or "full-time" in text_l or "permanent" in text_l:
        return "Full-time"
    return ""


MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9,
    "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def parse_month_year(value):
    value_l = str(value or "").lower().strip()
    if value_l in {"present", "current", "till date", "now"}:
        today = date.today()
        return today.year, today.month
    month_match = re.search(r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)", value_l)
    year_match = re.search(r"(19|20)\d{2}", value_l)
    if year_match:
        year = int(year_match.group(0))
        month = MONTHS.get(month_match.group(1), 1) if month_match else 1
        return year, month
    return None


def month_index(year_month):
    if not year_month:
        return None
    year, month = year_month
    return year * 12 + month


def month_label(index):
    if not index:
        return ""
    year = (index - 1) // 12
    month = ((index - 1) % 12) + 1
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{names[month - 1]} {year}"


def extract_date_ranges(text):
    patterns = [
        r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(?:19|20)\d{2}|(?:19|20)\d{2})\s*(?:-|to|–|—)\s*((?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(?:19|20)\d{2}|(?:19|20)\d{2}|present|current|till date|now)",
    ]
    ranges = []
    for pattern in patterns:
        for start, end in re.findall(pattern, str(text or ""), re.I):
            start_idx = month_index(parse_month_year(start))
            end_idx = month_index(parse_month_year(end))
            if start_idx and end_idx and end_idx >= start_idx:
                ranges.append((start_idx, end_idx))
    return ranges


def merge_ranges(ranges):
    if not ranges:
        return []
    ranges = sorted(ranges)
    merged = [ranges[0]]
    for start, end in ranges[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def experience_from_chronology(text):
    ranges = merge_ranges(extract_date_ranges(text))
    months = sum(end - start + 1 for start, end in ranges)
    return months, ranges


def career_gap_periods(ranges):
    gaps = []
    merged = merge_ranges(ranges)
    for previous, current in zip(merged, merged[1:]):
        start = previous[1] + 1
        end = current[0] - 1
        duration = end - start + 1
        if duration >= 3:
            gaps.append({
                "start": month_label(start),
                "end": month_label(end),
                "duration_months": duration,
            })
    return gaps


def employment_status_from_ranges(ranges):
    if not ranges:
        return "Unknown", ""
    latest_end = max(end for _, end in ranges)
    today_idx = date.today().year * 12 + date.today().month
    if latest_end >= today_idx - 1:
        return "Currently Employed", month_label(latest_end)
    return "Not Currently Employed", month_label(latest_end)


def fallback_experience_months(text):
    text = str(text or "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", text, re.I)
    if match:
        return int(round(float(match.group(1)) * 12))
    return 0


def explicit_experience_months(text):
    text = str(text or "")
    patterns = [
        r"(?:professional\s+summary|summary|profile)[\s\S]{0,400}?(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience",
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+)?experience",
        r"(?:total\s+experience|experience)\s*[:\-]\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)",
    ]
    matches = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, text, re.I))
    values = []
    for match in matches:
        try:
            values.append(float(match))
        except Exception:
            continue
    return int(round(max(values) * 12)) if values else 0


def capped_chronology_months(text):
    text = str(text or "")
    explicit = explicit_experience_months(text)
    chronology, ranges = experience_from_chronology(text)
    if explicit and chronology > explicit * 1.5:
        return explicit, ranges, True
    return chronology, ranges, False


def extract_contact(text):
    email = ""
    match = re.search(r"(?<![\w.-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])", text or "")
    if match:
        email = match.group(0).lower()
    phone = ""
    phone_patterns = [
        r"(?:\+?91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}",
        r"\+?1[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}",
        r"\+?\d[\d\s\-]{9,}\d",
    ]
    for pattern in phone_patterns:
        match = re.search(pattern, text or "")
        if match:
            phone = re.sub(r"[^\d+]", "", match.group(0))
            break
    linkedin = ""
    github = ""
    linkedin_match = re.search(r"https?://(?:www\.)?linkedin\.com/[^\s)]+", text or "", re.I)
    github_match = re.search(r"https?://(?:www\.)?github\.com/[^\s)]+", text or "", re.I)
    if linkedin_match:
        linkedin = linkedin_match.group(0)
    if github_match:
        github = github_match.group(0)
    return {"email": email, "phone": phone, "linkedin": linkedin, "github": github}


def extract_candidate_name(text, parsed_cv):
    parsed_name = clean_value(parsed_cv.get("candidate_name", ""), 80)
    if looks_like_candidate_name(parsed_name):
        return parsed_name
    lines = [clean_value(l, 100) for l in (text or "").splitlines()[:20]]
    for idx, line in enumerate(lines[:6]):
        if looks_like_single_candidate_name(line):
            surrounding = " ".join(lines[idx + 1: idx + 4]).lower()
            if re.search(r"\b(developer|engineer|analyst|consultant|manager|specialist|email|@|phone|mobile|bangalore|mumbai|delhi|pune|india)\b", surrounding):
                return line.title()
    for line in lines[:6]:
        if looks_like_candidate_name(line):
            return line.title()
    for line in lines:
        if "|" in line:
            for part in [clean_value(p, 80) for p in line.split("|")]:
                if looks_like_candidate_name(part):
                    return part.title()
    for line in lines:
        if looks_like_candidate_name(line):
            return line.title()
    return ""


def looks_like_single_candidate_name(value):
    value = clean_value(value, 60)
    if not value or any(ch in value for ch in "@:/\\|()[]{}0123456789"):
        return False
    lower = value.lower()
    blocked = {
        "resume", "profile", "summary", "education", "skills", "experience", "career",
        "objective", "professional", "developer", "engineer", "manager", "analyst",
        "consultant", "specialist", "india", "available"
    }
    if lower in blocked or len(value) < 3 or len(value) > 28:
        return False
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z'.-]*", value)) and value[:1].isupper()


def looks_like_candidate_name(value):
    if not value or any(ch in value for ch in "@:/\\|()[]{}"):
        return False
    lower = value.lower()
    blocked = [
        "resume", "curriculum", "profile", "summary", "experience", "education", "skills",
        "engineer", "developer", "manager", "analyst", "consultant", "specialist",
        "merchandiser", "administrator", "executive", "associate", "lead", "architect",
        "email", "phone", "mobile", "contact", "linkedin", "github", "market", "hiring",
        "objective", "career", "professional", "india", "available", "certified",
        "certification", "trained", "iiba", "cbap", "psm", "scrum", "agile", "expert",
        "banking", "insurance", "capital", "market", "lending", "domain"
    ]
    if any(word in lower for word in blocked):
        return False
    if lower.startswith(("ing ", "in ", "the ", "and ", "for ", "with ")):
        return False
    if re.search(r"\b(19|20)\d{2}\b|\bpresent\b|\bcurrent\b", lower):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'.-]*", value)
    if len(words) < 2 or len(words) > 4:
        return False
    short_words = {"in", "of", "the", "and", "for"}
    if any(w.lower() in short_words for w in words):
        return False
    return sum(1 for w in words if w[:1].isupper()) >= min(2, len(words))


def looks_like_role_title(value):
    value = clean_value(value, 90)
    if not value:
        return False
    lower = value.lower()
    if re.search(r"\b(b\.?e\.?|b\.?tech|m\.?tech|diploma|degree|mechanical engineering|electrical engineering|engineering\)?$|educational background|qualification)\b", lower):
        return False
    if lower.startswith(("ing ", "in ", "the ", "and ", "for ", "with ")):
        return False
    blocked_fragments = [" in the market", " hiring ", " resume", " curriculum", " email", " phone"]
    if any(fragment in f" {lower} " for fragment in blocked_fragments):
        return False
    role_words = [
        "manager", "engineer", "developer", "analyst", "consultant", "specialist", "lead",
        "architect", "director", "administrator", "designer", "owner", "product", "sales",
        "marketing", "finance", "operations", "support", "executive", "tool room",
        "tool-room", "toolroom", "cnc", "edm", "vmc", "hmc", "technician", "operator"
    ]
    return any(word in lower for word in role_words)


def clean_company_name(value):
    value = clean_value(value, 90)
    value = re.sub(r"^name\s*[-:]\s*", "", value, flags=re.I).strip()
    if not value:
        return ""
    lower = value.lower()
    blocked = ["name", "email", "phone", "resume", "curriculum", "profile", "summary"]
    if lower in blocked or lower.startswith(("name -", "email -", "phone -")):
        return ""
    return value


def skill_confidence_scores(text, parsed_skills):
    found = extract_skills(text)
    output = []
    for skill in unique_list(parsed_skills + found):
        canonical = canonical_skill(skill)
        evidence = 0
        if re.search(r"\b(production|implemented|built|developed|owned|led|deployed|maintained)\b.{0,90}" + re.escape(canonical.split()[0]), text or "", re.I):
            evidence += 1
        mentions = len(re.findall(re.escape(canonical.split()[0]), text or "", re.I))
        confidence = 0.65 + min(0.25, mentions * 0.05) + (0.1 if evidence else 0)
        output.append({"skill": canonical, "confidence": round(min(0.97, confidence), 2)})
    return output


def skill_recency_scores(text, skills):
    text_l = (text or "").lower()
    current_section = text_l[:2500]
    scores = []
    for skill in skills or []:
        canonical = canonical_skill(skill)
        first = canonical.split()[0].lower()
        if re.search(r"\b(present|current|till date|now)\b.{0,900}\b" + re.escape(first) + r"\b", text_l):
            score = 0.95
        elif re.search(r"\b" + re.escape(first) + r"\b", current_section):
            score = 0.8
        elif re.search(r"\b" + re.escape(first) + r"\b", text_l):
            score = 0.55
        else:
            score = 0.25
        scores.append({"skill": canonical, "recency_score": round(score, 2)})
    return scores


def project_evidence_scores(text, skills):
    text_l = (text or "").lower()
    evidence_verbs = r"(built|launched|implemented|owned|led|delivered|deployed|scaled|migrated|optimized|managed)"
    scores = []
    for skill in skills or []:
        canonical = canonical_skill(skill)
        first = canonical.split()[0].lower()
        mentions = len(re.findall(r"\b" + re.escape(first) + r"\b", text_l))
        has_project_evidence = bool(re.search(evidence_verbs + r".{0,140}\b" + re.escape(first) + r"\b", text_l))
        score = 0.35 + min(0.3, mentions * 0.06) + (0.3 if has_project_evidence else 0)
        scores.append({"skill": canonical, "evidence_score": round(min(0.95, score), 2)})
    return scores


def ai_optimization_risk(text):
    text_l = (text or "").lower()
    generic_phrases = [
        "results-driven", "dynamic professional", "proven track record", "cross-functional teams",
        "fast-paced environment", "strong communication skills", "detail-oriented",
        "passionate about", "highly motivated"
    ]
    generic_hits = sum(1 for phrase in generic_phrases if phrase in text_l)
    metrics = len(re.findall(r"\b\d+(?:\.\d+)?\s*(?:%|percent|m|million|k|crore|lakh|x)\b", text_l))
    bullets = len([line for line in (text or "").splitlines() if line.strip().startswith(("-", "•", "*"))])
    risk = 20 + generic_hits * 8 - min(20, metrics * 4) - min(10, bullets)
    return {
        "score": int(max(0, min(100, risk))),
        "label": "High" if risk >= 65 else "Medium" if risk >= 35 else "Low",
        "signals": unique_list([phrase for phrase in generic_phrases if phrase in text_l], 6),
    }


def production_beginner_split(text, skills):
    production, beginner = [], []
    text_l = (text or "").lower()
    for skill in skills:
        canonical = canonical_skill(skill)
        aliases = [canonical.lower()]
        if canonical == "REST API":
            aliases.extend(["rest api", "rest apis", "apis", "api"])
        if canonical == ".NET":
            aliases.extend([".net", "dotnet"])
        if canonical == "C#":
            aliases.extend(["c#", "c sharp"])
        if canonical == "Embedded C":
            aliases.extend(["embedded c"])
        matched_alias = any(re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", text_l) for alias in aliases)
        first = canonical.split()[0].lower().strip(".")
        production_pattern = r"\b(implemented|built|developed|owned|led|deployed|maintained|optimized|migrated|architected|designed|debugged|diagnosed)\b.{0,160}\b" + re.escape(first) + r"\b"
        if matched_alias and re.search(production_pattern, text_l):
            production.append(canonical_skill(skill))
        else:
            beginner.append(canonical_skill(skill))
    return unique_list(production), unique_list(beginner)


def extract_role_history(text, parsed_cv, normalized_skills, current_role="", current_company=""):
    ranges = extract_date_ranges(text)
    role_history = []
    inferred_title, inferred_company = infer_latest_role_from_lines(text)
    title = current_role or inferred_title
    company = current_company or inferred_company
    if title or company:
        duration_months = fallback_experience_months(parsed_cv.get("experience_years", ""))
        if ranges:
            duration_months = max(0, ranges[-1][1] - ranges[-1][0] + 1)
        role_history.append({
            "title": title,
            "company": company,
            "duration_years": round(duration_months / 12, 1) if duration_months else 0,
            "responsibilities": extract_role_responsibilities(text)[:5],
            "skills_used": normalized_skills[:12]
        })
    return role_history


def infer_latest_role_from_lines(text):
    lines = [clean_value(line, 140) for line in (text or "").splitlines() if clean_value(line, 140)]
    title, company = "", ""
    for i, line in enumerate(lines[:80]):
        if looks_like_role_title(line):
            title = strip_date_noise(line)
            if "," in title:
                title = title.split(",", 1)[0].strip()
            for nearby in lines[max(0, i - 2): i + 3]:
                candidate_company = extract_company_from_line(nearby)
                if candidate_company and candidate_company.lower() not in title.lower() and not looks_like_candidate_name(candidate_company):
                    company = candidate_company
                    break
            break
    return title, company


def strip_date_noise(value):
    value = re.sub(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(?:19|20)\d{2}\b.*$", "", value, flags=re.I)
    value = re.sub(r"\b(?:19|20)\d{2}\s*(?:-|to|–|—).*$", "", value, flags=re.I)
    return clean_value(value, 90)


def extract_company_from_line(line):
    cleaned = clean_value(line, 90)
    match = re.search(r"(?:company(?:\s+name)?|employer|organization|organisation)\s*[:\\-]\s*(.+)", cleaned, re.I)
    if match:
        return clean_company_name(match.group(1))
    match = re.search(r"\b(?:at|@)\s+([A-Z][A-Za-z0-9&., ]{2,60})", cleaned)
    if match:
        return clean_company_name(match.group(1))
    if re.fullmatch(r"[A-Z][A-Za-z0-9&., ]{2,40}", cleaned) and not looks_like_role_title(cleaned):
        return clean_company_name(cleaned)
    return ""


def extract_role_responsibilities(text):
    bullets = extract_bullets(text)
    blocked_prefixes = ("with over", "summary", "profile", "objective")
    return [
        b for b in bullets
        if not b.lower().startswith(blocked_prefixes)
        and not looks_like_role_title(b)
        and len(b.split()) >= 6
    ]


def infer_role_from_recent_work(text, parsed_jd=None):
    text_l = (text or "").lower()
    jd_title = clean_value((parsed_jd or {}).get("role_title") or (parsed_jd or {}).get("title") or "", 80)
    summary_match = re.search(r"(?:summary|profile)\s+([^\n]{0,160}?(?:engineer|developer|architect|analyst|consultant|manager|specialist)[^\n]{0,80})", text or "", re.I)
    if summary_match:
        role_phrase = clean_value(summary_match.group(1), 90)
        role_phrase = re.sub(r"\bwith\b.*$", "", role_phrase, flags=re.I).strip()
        if looks_like_role_title(role_phrase):
            return role_phrase.title()
    collapsed_text = re.sub(r"\s+", " ", text or "")
    for match in re.finditer(r"\bas\s+a[n]?\s+([A-Za-z0-9 ./&-]{3,100})", collapsed_text, re.I):
        role_phrase = strip_date_noise(match.group(1))
        role_phrase = re.split(r"\b(?:in|at)\s+(?:tool\s*room|toolroom|department|connectwell|flu-con|anil|kashinath)\b", role_phrase, flags=re.I)[0]
        role_phrase = clean_value(role_phrase, 80)
        if looks_like_role_title(role_phrase):
            return role_phrase.title()
    for line in [clean_value(line, 120) for line in (text or "").splitlines()[:40] if clean_value(line, 120)]:
        if looks_like_role_title(line) and not line.lower().startswith(("professional", "summary", "core skills")):
            return strip_date_noise(line).title()
    role_signals = [
        ("Tool Room / Die Maintenance Engineer", ["tool room", "tool-room", "toolroom", "tool manufacturing", "tool maintenance", "wire edm", "die sinker edm", "edm", "vmc", "hmc", "cnc", "press tool", "fixture"]),
        ("CNC / EDM Operator", ["cnc", "edm", "wire edm", "die sinker edm", "vmc", "hmc", "machine programming"]),
        ("Manufacturing Maintenance Engineer", ["preventive maintenance", "breakdown maintenance", "machine maintenance", "mechanical maintenance"]),
        ("Full Stack Software Engineer", ["angular", "frontend", "backend", "api", ".net", "c#", "microservices"]),
        ("Backend Software Engineer", ["backend", "api", "microservices", ".net", "c#", "java", "spring", "kafka"]),
        ("Data Migration Engineer", ["database migration", "mysql", "postgresql", "npgsql", "migration tool"]),
        ("Frontend Engineer", ["angular", "react", "frontend", "ui"]),
        ("DevOps / Cloud Engineer", ["aws", "s3", "docker", "kubernetes", "ci/cd"]),
    ]
    scored = []
    for role, signals in role_signals:
        score = sum(1 for signal in signals if signal in text_l)
        if score:
            scored.append((score, role))
    if scored:
        return sorted(scored, reverse=True)[0][1]
    inferred_title, _ = infer_latest_role_from_lines(text)
    return inferred_title


def parse_resume(cv_text, parsed_cv=None):
    parsed_cv = parsed_cv or {}
    llm = llm_extract("resume", cv_text)
    parser_warnings = []
    parse_source = "llm" if llm else "deterministic"
    if not llm:
        debug_match("Resume deterministic parsing fallback is being used.")
        parser_warnings.append("Resume parsed with deterministic fallback because LLM extraction was unavailable.")
    parsed_skill_values = []
    if parsed_cv.get("key_skills"):
        parsed_skill_values.extend([s for s in re.split(r"[,;/|]", parsed_cv["key_skills"]) if s.strip()])
    parsed_skill_values.extend(llm.get("skills", []) if isinstance(llm.get("skills"), list) else [])
    normalized_skills = unique_list([canonical_skill(s) for s in parsed_skill_values + extract_skills(cv_text)], 25)
    if re.search(r"\b(cnc|edm|vmc|hmc|tool\s*room|tool-room|machine|mould|mold|fixture|press tool|maintenance|manufacturing|production|shop floor)\b", cv_text or "", re.I):
        normalized_skills = [s for s in normalized_skills if s not in {"Apache Spark", "Artificial Intelligence", "Machine Learning"}]
    production_skills, beginner_skills = production_beginner_split(cv_text, normalized_skills)
    chronology_months, ranges, chronology_capped = capped_chronology_months(cv_text)
    gaps = career_gap_periods(ranges)
    employment_status, last_employed_date = employment_status_from_ranges(ranges)
    llm_experience_value = llm.get("experience_years") or llm.get("total_experience_years") or llm.get("total_experience") or ""
    experience_hint = str(llm_experience_value or parsed_cv.get("experience_years", "") or cv_text or "")
    explicit_months = explicit_experience_months(experience_hint)
    fallback_months = fallback_experience_months(experience_hint)
    if fallback_months and not explicit_months and not chronology_months:
        debug_match("Resume experience fallback parser is being used.")
    total_months = max(chronology_months, explicit_months, fallback_months)
    confidence = "high" if explicit_months else "high" if chronology_months else "medium" if fallback_months else "low"
    current_role = clean_value(parsed_cv.get("current_role") or llm.get("current_role") or "", 80)
    if not looks_like_role_title(current_role):
        current_role = ""
    if not current_role:
        current_role = infer_role_from_recent_work(cv_text)
    if not looks_like_role_title(current_role):
        current_role = ""
    if not current_role:
        parser_warnings.append("Candidate current role was not confidently extracted.")
    current_company = clean_company_name(parsed_cv.get("current_company") or llm.get("current_company") or "")
    role_history_text = " ".join(
        str(item.get("title", "")) for item in llm.get("role_history", []) if isinstance(item, dict)
    )
    role_text = "\n".join([current_role, role_history_text, " ".join(normalized_skills[:10])])
    normalized_roles = unique_list([item["role"] for item in infer_role_taxonomy(role_text)], 6)
    domain_scores = infer_domain_taxonomy(cv_text)
    seniority = infer_seniority(role_text, round(total_months / 12, 1) if total_months else 0)
    role_history = extract_role_history(cv_text, parsed_cv, normalized_skills, current_role, current_company)
    taxonomy = build_taxonomy_bundle(
        role_text or cv_text,
        skills=normalized_skills,
        years=round(total_months / 12, 1) if total_months else 0
    )
    stability = 70 if role_history else 45
    if ranges and len(ranges) >= 5:
        stability = 55
    if any(int(gap.get("duration_months", 0) or 0) >= 12 for gap in gaps):
        stability = min(stability, 50)
    red_flags = resume_red_flags(current_role, total_months, normalized_skills)
    if gaps:
        red_flags.extend([f"Career gap detected: {gap['start']} to {gap['end']} ({gap['duration_months']} months)" for gap in gaps[:3]])
        parser_warnings.append("Career gaps were detected and may need recruiter validation.")
    if confidence == "low":
        parser_warnings.append("Experience confidence is low because no clear date chronology or explicit experience was found.")
    if len(re.findall(r"\w+", cv_text or "")) < 80:
        parser_warnings.append("Resume text is very sparse; scanned/image PDFs may need OCR or manual review.")
    manual_review_reasons = []
    if parse_source == "deterministic":
        manual_review_reasons.append("Resume required deterministic fallback.")
    if not current_role:
        manual_review_reasons.append("Candidate current role was not confidently extracted.")
    if confidence == "low":
        manual_review_reasons.append("Resume experience confidence is low.")
    if not normalized_skills:
        manual_review_reasons.append("No recognizable skills were extracted from the resume.")
    if len(re.findall(r"\w+", cv_text or "")) < 80:
        manual_review_reasons.append("Resume text is sparse and may be a scanned/image file requiring OCR.")
    return {
        "id": text_hash(cv_text)[:12],
        "candidate_name": extract_candidate_name(cv_text, parsed_cv),
        "total_experience_years": round(total_months / 12, 1) if total_months else 0,
        "current_role": current_role,
        "current_company": current_company,
        "current_employment_status": employment_status,
        "last_employed_date": last_employed_date,
        "career_gap_periods": gaps,
        "role_history": role_history,
        "primary_skills": production_skills or normalized_skills[:10],
        "secondary_skills": beginner_skills[:12],
        "tools_technologies": normalized_skills[:20],
        "domain_experience": unique_list([item["domain"] for item in domain_scores], 6),
        "certifications": extract_certifications(cv_text),
        "education": extract_education(cv_text, parsed_cv),
        "location": clean_value(parsed_cv.get("current_location") or extract_location(cv_text), 80),
        "career_stability_score": stability,
        "red_flags": unique_list(red_flags, 10),
        "project_complexity_indicators": extract_complexity(cv_text),
        "ownership_signals": extract_ownership(cv_text),
        "contact": extract_contact(cv_text),
        "experience_metrics": {
            "total_years_experience": round(total_months / 12, 1) if total_months else 0,
            "total_months_experience": int(total_months),
            "explicit_years_experience": round(explicit_months / 12, 1) if explicit_months else 0,
            "chronology_years_experience": round(chronology_months / 12, 1) if chronology_months else 0,
            "chronology_capped_by_explicit_summary": chronology_capped,
            "experience_confidence": confidence,
        },
        "normalized_roles": normalized_roles,
        "normalized_skills": normalized_skills,
        "taxonomy": taxonomy,
        "role_family": taxonomy.get("primary_role_family", ""),
        "domain_family": taxonomy.get("primary_domain_family", ""),
        "seniority_family": taxonomy.get("seniority", ""),
        "skill_family_match": taxonomy.get("skill_family_match", {}),
        "parse_source": parse_source,
        "parser_warnings": unique_list(parser_warnings, 10),
        "manual_review_required": bool(manual_review_reasons),
        "manual_review_reasons": unique_list(manual_review_reasons, 8),
        "production_skills": production_skills,
        "beginner_or_exposure_skills": beginner_skills,
        "skill_confidence_scores": skill_confidence_scores(cv_text, normalized_skills),
        "skill_recency_scores": skill_recency_scores(cv_text, normalized_skills),
        "project_evidence_scores": project_evidence_scores(cv_text, normalized_skills),
        "ai_optimization_risk": ai_optimization_risk(cv_text),
        "domain_confidence_scores": domain_scores,
        "seniority_level": seniority,
        "role_normalized": normalize_role_title(current_role),
        "chronology_ranges": [{"start_month": s, "end_month": e} for s, e in ranges],
        "embedding_vector": [],
    }


def extract_education(text, parsed_cv):
    items = []
    if parsed_cv.get("education"):
        items.append(parsed_cv["education"])
    items.extend(re.findall(r"\b(?:B\.?Tech|B\.?E\.?|B\.?Sc|M\.?Tech|M\.?Sc|MBA|MCA|BCA|Ph\.?D|Bachelor(?:'s)?|Master(?:'s)?)\b", text or "", re.I))
    return unique_list([clean_value(i.upper()) for i in items], 8)


def resume_red_flags(current_role, total_months, skills):
    flags = []
    if not current_role:
        flags.append("Current role not clearly stated")
    if not total_months:
        flags.append("Experience duration not clearly stated")
    if not skills:
        flags.append("No recognizable skills extracted")
    return flags


def extract_complexity(text):
    hints = ["microservices", "distributed", "large scale", "high availability", "migration", "architecture", "pipeline", "automation", "performance", "cloud", "production"]
    return unique_list([hint.title() for hint in hints if hint in (text or "").lower()], 8)


def extract_ownership(text):
    signals = []
    for phrase in ["led", "owned", "managed", "designed", "architected", "delivered", "mentored", "implemented", "deployed", "optimized"]:
        if re.search(r"\b" + re.escape(phrase) + r"\b", text or "", re.I):
            signals.append(phrase.title())
    return unique_list(signals, 8)


def semantic_score(jd_text, cv_text, jd, candidate, cache_get=None, cache_set=None):
    jd_embedding = generate_embedding(
        "\n".join([jd_text or "", " ".join(jd.get("embedding_keywords", []))]),
        cache_get=cache_get,
        cache_set=cache_set
    )
    summary_text = "\n".join([
        candidate.get("current_role", ""),
        str((candidate.get("experience_metrics") or {}).get("total_years_experience", "")),
        " ".join(candidate.get("domain_experience", [])),
    ])
    experience_bullets = []
    for role in candidate.get("role_history", []) or []:
        experience_bullets.extend(role.get("responsibilities", []) or [])
    skill_text = " ".join(candidate.get("normalized_skills", []))
    component_texts = {
        "resume_summary": summary_text or cv_text[:1000],
        "experience_bullets": "\n".join(experience_bullets) or cv_text[:1600],
        "skills": skill_text,
    }
    component_weights = {
        "resume_summary": 0.25,
        "experience_bullets": 0.45,
        "skills": 0.30,
    }
    weighted_similarity = 0
    total_weight = 0
    for key, text in component_texts.items():
        if not str(text or "").strip():
            continue
        embedding = generate_embedding(text, cache_get=cache_get, cache_set=cache_set)
        weight = component_weights[key]
        weighted_similarity += cosine_similarity(jd_embedding, embedding) * weight
        total_weight += weight
    if not total_weight:
        return 0
    embedding_score = int(round((weighted_similarity / total_weight) * 100))
    return max(embedding_score, lexical_semantic_floor(jd, candidate))


def lexical_semantic_floor(jd, candidate):
    required = [item.get("skill") for item in jd.get("must_have_skills_weighted", []) if item.get("skill")]
    candidate_skills = {canonical_skill(skill).lower() for skill in candidate.get("normalized_skills", [])}
    if required:
        exact = sum(1 for skill in required if canonical_skill(skill).lower() in candidate_skills)
        skill_score = exact / len(required)
    else:
        skill_score = 0
    jd_roles = {item.get("role") for item in jd.get("role_taxonomy", []) if item.get("role")}
    candidate_roles = set(candidate.get("normalized_roles", []))
    role_score = 1 if jd_roles & candidate_roles else 0
    if not role_score and {"Product Management", "Platform Product Management"} & jd_roles and {"Product Management", "Platform Product Management"} & candidate_roles:
        role_score = 0.85
    jd_domains = {item.get("domain") for item in jd.get("domain_taxonomy", []) if item.get("domain")}
    candidate_domains = {item.get("domain") for item in candidate.get("domain_confidence_scores", []) if item.get("domain")}
    domain_score = 1 if jd_domains & candidate_domains else 0
    infra = {"Cloud Infrastructure", "Hyperconverged Infrastructure", "SaaS", "Observability"}
    if not domain_score and jd_domains & infra and candidate_domains & infra:
        domain_score = 0.72
    ownership_score = 1 if candidate.get("ownership_signals") else 0
    complexity_score = 1 if candidate.get("project_complexity_indicators") else 0
    floor = (
        42 +
        skill_score * 26 +
        role_score * 14 +
        domain_score * 9 +
        ownership_score * 5 +
        complexity_score * 4
    )
    return int(max(0, min(88, round(floor))))


def run_hybrid_match(
    jd_text,
    cv_text,
    parsed_cv=None,
    cache_get=None,
    cache_set=None,
    custom_hard_filters="",
    parsed_jd=None,
    parsed_candidate=None,
):
    parsed_jd = parsed_jd or parse_jd(jd_text)
    parsed_candidate = parsed_candidate or parse_resume(cv_text, parsed_cv)
    structured_result = deterministic_structured_score(parsed_jd, parsed_candidate)
    hard_filter_result = evaluate_hard_filters(parsed_jd, parsed_candidate, custom_hard_filters)
    semantic = semantic_score(jd_text, cv_text, parsed_jd, parsed_candidate, cache_get=cache_get, cache_set=cache_set)
    structured_score = structured_result["structured_score"]
    hard_filter_score = hard_filter_result["hard_filter_score"]
    final_score = int(round(0.50 * structured_score + 0.30 * semantic + 0.20 * hard_filter_score))
    if not hard_filter_result["passed"]:
        final_score = min(final_score, 40)
    breakdown = structured_result.get("score_breakdown") or {}
    if (
        (breakdown.get("must_have_skills") or {}).get("score", 0) == 0
        and (breakdown.get("role_alignment") or {}).get("score", 100) < 45
        and (breakdown.get("domain_fit") or {}).get("score", 100) < 45
    ):
        final_score = min(final_score, 30)
    explainability = build_explainability(parsed_jd, parsed_candidate, structured_result, semantic)
    for item in hard_filter_result.get("filters", []):
        if not item.get("passed"):
            impact = 25 if item.get("severity") == "blocker" else 6
            explainability["penalties_applied"].append({"reason": item.get("reason", item.get("name", "Hard filter failed")), "impact": impact})
    verdict = "Strong Match" if final_score >= 80 else "Moderate Match" if final_score >= 65 else "Weak Match" if final_score >= 45 else "Reject / Not Recommended"
    response = {
        "final_score": final_score,
        "structured_score": structured_score,
        "semantic_score": semantic,
        "hard_filter_score": hard_filter_score,
        "hard_filters": hard_filter_result,
        "custom_hard_filters": custom_hard_filters,
        "semantic_similarity_score": semantic,
        "score_breakdown": structured_result["score_breakdown"],
        "strengths": explainability["strengths"],
        "concerns": explainability["concerns"],
        "penalties_applied": explainability["penalties_applied"],
        "matched_must_have_skills": structured_result["matched_must_have_skills"],
        "missing_must_have_skills": structured_result["missing_must_have_skills"],
        "parsed_jd": parsed_jd,
        "parsed_candidate": parsed_candidate,
        "explainability": explainability,
        "semantic_match_insights": explainability.get("semantic_match_insights", []),
        "role_alignment_reasoning": explainability.get("role_alignment_reasoning", []),
        "verdict": verdict,
    }
    # Backward-compatible fields used by the existing screen.
    response.update({
        "score": final_score,
        "summary": "; ".join(explainability["concerns"][:2]) if explainability["concerns"] else "Core hiring signals are aligned.",
        "gaps": explainability["concerns"],
        "jd_json": parsed_jd,
        "cv_json": parsed_candidate,
        "score_json": {
            "final_score": final_score,
            "verdict": verdict,
            "structured_score": structured_score,
            "semantic_score": semantic,
            "hard_filter_score": hard_filter_score,
            "score_breakdown": {k: v["score"] for k, v in structured_result["score_breakdown"].items()},
            "matched_must_have_skills": structured_result["matched_must_have_skills"],
            "missing_must_have_skills": structured_result["missing_must_have_skills"],
            "strengths": explainability["strengths"],
            "concerns": explainability["concerns"],
            "red_flags": parsed_candidate.get("red_flags", []),
            "penalties_applied": explainability["penalties_applied"],
            "explanation_summary": "; ".join(explainability["concerns"][:2]) if explainability["concerns"] else "Core hiring signals are aligned.",
        },
        "mode": "hybrid_deterministic",
    })
    return response
