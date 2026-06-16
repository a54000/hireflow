from skill_aliases import canonical_skill, extract_skills


def _candidate_skill_set(candidate):
    return {canonical_skill(skill).lower() for skill in candidate.get("normalized_skills", []) or [] if canonical_skill(skill)}


def _custom_filter_checks(custom_text, candidate):
    checks = []
    text = str(custom_text or "").strip()
    if not text:
        return checks
    candidate_skills = _candidate_skill_set(candidate)
    candidate_blob = " ".join([
        candidate.get("current_role", ""),
        candidate.get("current_company", ""),
        " ".join(candidate.get("normalized_skills", []) or []),
        " ".join(candidate.get("domain_experience", []) or []),
        " ".join(candidate.get("ownership_signals", []) or []),
        " ".join(candidate.get("project_complexity_indicators", []) or []),
    ]).lower()
    custom_skills = [canonical_skill(skill) for skill in extract_skills(text)]
    for skill in custom_skills:
        passed = canonical_skill(skill).lower() in candidate_skills
        checks.append({
            "name": f"Custom filter: {skill}",
            "passed": passed,
            "severity": "blocker" if not passed else "pass",
            "reason": f"Custom requirement '{skill}' {'was found' if passed else 'was not found'} in the resume."
        })
    for raw_line in text.splitlines():
        line = raw_line.strip(" -•*\t")
        if len(line) < 5:
            continue
        if any(canonical_skill(skill).lower() in line.lower() for skill in custom_skills):
            continue
        lowered = line.lower()
        if not any(marker in lowered for marker in ["must", "required", "mandatory", "hard filter", "should have"]):
            continue
        important_words = [
            word for word in lowered.replace("/", " ").replace(",", " ").split()
            if len(word) > 3 and word not in {"must", "have", "required", "mandatory", "hard", "filter", "candidate", "experience", "with", "should"}
        ][:5]
        passed = bool(important_words and all(word in candidate_blob for word in important_words[:3]))
        checks.append({
            "name": "Custom filter: " + line[:70],
            "passed": passed,
            "severity": "blocker" if not passed else "pass",
            "reason": f"Custom rule '{line[:120]}' {'appears satisfied' if passed else 'was not clearly found'} in the resume."
        })
    return checks


def _education_matches(required, candidate_education):
    required_text = " ".join(required or []).lower()
    candidate_text = " ".join(candidate_education or []).lower()
    equivalents = [
        {"b.tech", "btech", "b.e", "be", "bachelor", "graduate"},
        {"m.tech", "mtech", "m.sc", "msc", "master", "post graduate", "postgraduate"},
        {"mba"},
        {"mca"},
        {"bca"},
        {"ph.d", "phd"},
    ]
    for group in equivalents:
        if any(term in required_text for term in group):
            return any(term in candidate_text for term in group)
    return bool(required_text and required_text in candidate_text)


def evaluate_hard_filters(jd, candidate, custom_text=""):
    filters = []
    req = jd.get("experience_required") or {}
    min_years = float(req.get("min_years") or 0)
    candidate_years = float((candidate.get("experience_metrics") or {}).get("total_years_experience") or candidate.get("total_experience_years") or 0)
    if min_years:
        shortfall_months = max(0, int(round((min_years - candidate_years) * 12)))
        passed = shortfall_months <= 6
        filters.append({
            "name": "Minimum experience",
            "passed": passed,
            "severity": "blocker" if not passed else "pass",
            "reason": f"Candidate has {candidate_years:g} years; requirement is {min_years:g}+ years. Shortfall up to 6 months is acceptable."
        })
    required_education = jd.get("education_required") or []
    if required_education:
        candidate_education = candidate.get("education") or []
        passed = _education_matches(required_education, candidate_education)
        filters.append({
            "name": "Education requirement",
            "passed": passed,
            "severity": "blocker" if not passed else "pass",
            "reason": (
                "Required education found before skill evaluation."
                if passed else
                "JD education criteria not found in CV: " + ", ".join(required_education[:4])
            )
        })
    required_certs = {str(c).lower() for c in jd.get("certifications_required", []) if c}
    candidate_certs = {str(c).lower() for c in candidate.get("certifications", []) if c}
    if required_certs:
        missing = sorted(required_certs - candidate_certs)
        filters.append({
            "name": "Mandatory certifications",
            "passed": not missing,
            "severity": "blocker" if missing else "pass",
            "reason": "Missing certifications: " + ", ".join(missing) if missing else "Required certifications found."
        })
    jd_location = str(jd.get("location") or "").strip().lower()
    candidate_location = str(candidate.get("location") or "").strip().lower()
    if jd_location and "remote" not in jd_location:
        passed = bool(candidate_location and (candidate_location in jd_location or jd_location in candidate_location))
        filters.append({
            "name": "Location alignment",
            "passed": passed,
            "severity": "warning" if not passed else "pass",
            "reason": f"JD location: {jd.get('location')}; candidate location: {candidate.get('location') or 'not found'}."
        })
    long_gaps = [
        gap for gap in candidate.get("career_gap_periods", [])
        if int(gap.get("duration_months", 0) or 0) >= 6
    ]
    if long_gaps:
        filters.append({
            "name": "Career gaps",
            "passed": False,
            "severity": "warning",
            "reason": f"{len(long_gaps)} career gap(s) of 6+ months detected."
        })
    filters.extend(_custom_filter_checks(custom_text, candidate))
    blocker_failed = any(not f["passed"] and f["severity"] == "blocker" for f in filters)
    warning_failed = any(not f["passed"] and f["severity"] == "warning" for f in filters)
    hard_filter_score = 0 if blocker_failed else 75 if warning_failed else 100
    return {
        "hard_filter_score": hard_filter_score,
        "passed": not blocker_failed,
        "filters": filters
    }
