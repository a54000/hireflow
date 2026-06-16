import re

from skill_aliases import canonical_skill


def clean_value(value, limit=120):
    return re.sub(r"\s+", " ", str(value or "")).strip(" -:|,\t\r\n")[:limit]


def unique_list(values, limit=None):
    seen = []
    for value in values or []:
        if not value:
            continue
        if value not in seen:
            seen.append(value)
        if limit and len(seen) >= limit:
            break
    return seen


def _score_value(value):
    if isinstance(value, dict):
        value = value.get("score", 0)
    try:
        return int(round(float(value or 0)))
    except Exception:
        return 0


def _list(value):
    return value if isinstance(value, list) else []


def _breakdown_item(label, value, weight):
    if isinstance(value, dict):
        score = _score_value(value.get("score", 0))
        reason = value.get("reason", "")
        matched = _list(value.get("matched_items"))
        missing = _list(value.get("missing_items"))
    else:
        score = _score_value(value)
        reason = ""
        matched = []
        missing = []
    return {
        "key": label.lower().replace(" ", "_"),
        "label": label,
        "score": score,
        "weight": weight,
        "weighted_points": round(score * weight, 1),
        "reason": reason,
        "matched_items": matched,
        "missing_items": missing,
    }


def verdict_for(score):
    if score >= 80:
        return "Strong Match"
    if score >= 65:
        return "Moderate Match"
    if score >= 45:
        return "Weak Match"
    return "Reject / Not Recommended"


def recommendation_for(score, missing_must=None):
    missing_must = missing_must or []
    if score >= 85 and len(missing_must) <= 5:
        return "Recommend for hiring manager review"
    if score >= 82 and len(missing_must) <= 3:
        return "Recommend for hiring manager review"
    if score >= 70:
        return "Proceed with recruiter screen"
    if score >= 55:
        return "Hold for calibration or backup pipeline"
    return "Do not proceed for this requirement"


def confidence_for(analysis):
    score = _score_value(analysis.get("final_score") or analysis.get("score"))
    parsed_jd = analysis.get("parsed_jd") or analysis.get("jd_json") or {}
    parsed_candidate = analysis.get("parsed_candidate") or analysis.get("cv_json") or {}
    confidence = 55
    if analysis.get("structured_score") is not None:
        confidence += 10
    if analysis.get("semantic_score") is not None:
        confidence += 8
    if parsed_jd.get("must_have_skills") or parsed_jd.get("must_have_skills_weighted"):
        confidence += 10
    if parsed_candidate.get("experience_metrics") or parsed_candidate.get("total_experience_years"):
        confidence += 8
    if parsed_candidate.get("normalized_skills") or parsed_candidate.get("primary_skills"):
        confidence += 7
    if not score:
        confidence -= 20
    confidence = max(0, min(100, confidence))
    label = "High" if confidence >= 80 else "Medium" if confidence >= 60 else "Low"
    route_label = "Auto trust" if label == "High" and score >= 70 else ("Recruiter review" if label == "Medium" and score >= 55 else "Manual review")
    route_reason = (
        "High confidence and a healthy score; the result can flow through the normal recruiter workflow."
        if route_label == "Auto trust" else
        "Confidence is adequate but the match should be reviewed before submission."
        if route_label == "Recruiter review" else
        "Confidence or match quality is too low for automation; a recruiter should review this case manually."
    )
    return {"score": confidence, "label": label, "route": {"label": route_label, "reason": route_reason}}


def build_recruiter_summary(analysis, dashboard=None):
    if analysis.get("overall_recruiter_summary"):
        return analysis["overall_recruiter_summary"]
    dashboard = dashboard or {}
    overview = dashboard.get("overview", {})
    final_score = overview.get("final_score", 0)
    strengths = dashboard.get("strengths", [])[:3]
    concerns = dashboard.get("concerns", [])[:3]
    snapshot = dashboard.get("candidate_snapshot") or {}
    subject = snapshot.get("candidate_name") or "The candidate"
    role = snapshot.get("current_role")
    if role:
        summary = f"{subject}, currently {role}, is assessed as {overview.get('verdict', verdict_for(final_score))} with a final score of {final_score}. "
    else:
        summary = f"{subject} is assessed as {overview.get('verdict', verdict_for(final_score))} with a final score of {final_score}. "
    if strengths and final_score >= 45:
        summary += format_strength_sentence(strengths) + " "
    if concerns:
        summary += format_concern_sentence(concerns) + " "
    recommendation = str(overview.get("recommendation", "")).strip()
    if recommendation.lower().startswith("do not"):
        summary += f"The recommended next step is: {recommendation.lower()}."
    else:
        summary += f"The recommended next step is to {recommendation.lower()}."
    manual_review = dashboard.get("manual_review") or {}
    if manual_review.get("required"):
        summary += " Manual recruiter review is recommended because the parser confidence is not strong enough for full automation."
    return summary


def _clean_evidence_item(item):
    item = str(item or "").strip()
    item = item.replace("Matches required skills: ", "")
    item = item.replace("Missing required skills: ", "")
    item = item.replace("Shows ownership signals: ", "ownership signals include ")
    item = item.replace("JD", "job description")
    return item[:260]


def format_strength_sentence(strengths):
    cleaned = [_clean_evidence_item(s) for s in strengths if s]
    skill_evidence = []
    other_evidence = []
    for item in cleaned:
        if "," in item and not item.lower().startswith(("candidate", "experience", "ownership")):
            skill_evidence.append(item)
        else:
            other_evidence.append(item)
    parts = []
    if skill_evidence:
        parts.append("the profile shows relevant skill evidence across " + "; ".join(skill_evidence[:1]))
    if other_evidence:
        parts.append("; ".join(other_evidence[:2]).replace("JD", "job description").lower())
    return "Positive signals include " + ", and ".join(parts) + "."


def format_concern_sentence(concerns):
    cleaned = [_clean_evidence_item(c) for c in concerns if c]
    if not cleaned:
        return ""
    return "The main gaps to validate are " + "; ".join(cleaned[:3]) + "."


def _role_family_label(parsed, fallback=""):
    parsed = parsed or {}
    taxonomy = parsed.get("taxonomy") or {}
    if taxonomy.get("primary_role_family"):
        return taxonomy.get("primary_role_family")
    role_profile = parsed.get("role_profile") or {}
    if isinstance(role_profile, dict) and role_profile.get("name"):
        return role_profile.get("name")
    role_taxonomy = _list(parsed.get("role_taxonomy"))
    if role_taxonomy and role_taxonomy[0].get("role"):
        return role_taxonomy[0].get("role")
    role_title = parsed.get("role_title") or parsed.get("current_role") or fallback or ""
    return role_title


def _normalize_role_bucket(value):
    value = str(value or "").strip()
    if not value:
        return ""
    value = value.replace(" / ", " / ").strip()
    return value


def _build_role_family_comparison(parsed_jd, parsed_candidate, score=None):
    jd_family = _normalize_role_bucket(_role_family_label(parsed_jd, parsed_jd.get("role_title") or parsed_jd.get("title") or ""))
    candidate_roles = _list(parsed_candidate.get("normalized_roles"))
    candidate_primary = _normalize_role_bucket(candidate_roles[0] if candidate_roles else parsed_candidate.get("current_role", ""))
    candidate_taxonomy = parsed_candidate.get("taxonomy") or {}
    if candidate_taxonomy.get("primary_role_family"):
        candidate_primary = _normalize_role_bucket(candidate_taxonomy.get("primary_role_family"))
    candidate_family = candidate_primary or _normalize_role_bucket(parsed_candidate.get("current_role", ""))
    candidate_skills = _list(parsed_candidate.get("normalized_skills") or parsed_candidate.get("primary_skills") or [])
    jd_skills = _list(parsed_jd.get("must_have_skills") or [i.get("skill") for i in _list(parsed_jd.get("must_have_skills_weighted")) if i.get("skill")])
    overlap = [skill for skill in jd_skills if skill in candidate_skills]
    jd_notes = _list(parsed_jd.get("validation_evidence"))
    if jd_family and candidate_family and jd_family.lower() == candidate_family.lower():
        match_line = "The CV and JD point to the same role family."
    elif jd_family and candidate_family:
        match_line = "The CV shows a related but not identical role family."
    else:
        match_line = "Role family could not be determined cleanly from one side of the match."
    return {
        "jd_family": jd_family or "-",
        "candidate_family": candidate_family or "-",
        "jd_skills": jd_skills[:12],
        "candidate_skills": candidate_skills[:12],
        "shared_skills": overlap[:12],
        "validation_evidence": jd_notes[:10],
        "match_summary": match_line,
        "match_score": score if score is not None else None,
    }


def _build_experience_comparison(parsed_jd, parsed_candidate):
    req = parsed_jd.get("experience_required") or {}
    min_years = float(req.get("min_years") or 0)
    max_years = float(req.get("max_years") or 0)
    candidate_years = float((parsed_candidate.get("experience_metrics") or {}).get("total_years_experience") or parsed_candidate.get("total_experience_years") or 0)
    if min_years and max_years:
        required_text = f"{min_years:g}-{max_years:g} years"
    elif min_years:
        required_text = f"{min_years:g}+ years"
    elif max_years:
        required_text = f"Up to {max_years:g} years"
    else:
        required_text = "Not specified"
    if min_years and candidate_years < min_years:
        fit_text = f"Candidate is below the lower end of the range by {max(0, min_years - candidate_years):g} years."
    elif max_years and candidate_years > max_years:
        fit_text = f"Candidate is above the JD range by {max(0, candidate_years - max_years):g} years."
    else:
        fit_text = "Candidate experience fits the JD range."
    return {
        "jd_required": required_text,
        "candidate_years": round(candidate_years, 1),
        "fit_summary": fit_text,
        "difference_years": round(candidate_years - (min_years or max_years or candidate_years), 1) if (min_years or max_years) else 0,
        "is_within_range": bool((not min_years or candidate_years >= min_years) and (not max_years or candidate_years <= max_years)),
    }


def _build_skill_years(parsed_candidate):
    role_history = _list(parsed_candidate.get("role_history"))
    skills = _list(parsed_candidate.get("normalized_skills") or parsed_candidate.get("primary_skills") or parsed_candidate.get("tools_technologies") or [])
    totals = {}
    evidence = {}
    for role in role_history:
        if not isinstance(role, dict):
            continue
        years = float(role.get("duration_years") or 0)
        if not years:
            months = float(role.get("duration_months") or 0)
            years = round(months / 12, 1) if months else 0
        role_skills = {canonical_skill(skill) for skill in _list(role.get("skills_used")) if canonical_skill(skill)}
        role_title = clean_value(role.get("title") or role.get("company") or "", 90)
        role_desc = " ".join(_list(role.get("responsibilities"))[:8]).lower()
        for skill in skills:
            canonical = canonical_skill(skill)
            if not canonical:
                continue
            hit = canonical in role_skills or canonical.lower() in role_desc or canonical.lower() in role_title.lower()
            if hit:
                totals[canonical] = round(float(totals.get(canonical, 0)) + years, 1)
                evidence.setdefault(canonical, [])
                if role_title and role_title not in evidence[canonical]:
                    evidence[canonical].append(role_title)
    rows = []
    for skill in skills[:15]:
        canonical = canonical_skill(skill)
        if not canonical:
            continue
        years = round(float(totals.get(canonical, 0)), 1)
        if years:
            rows.append({
                "skill": canonical,
                "years": years,
                "evidence_roles": evidence.get(canonical, [])[:3],
            })
    rows.sort(key=lambda item: (-item["years"], item["skill"]))
    return rows[:12]


def _build_recent_experience(parsed_candidate):
    role_history = _list(parsed_candidate.get("role_history"))
    if not role_history:
        return {}
    recent = role_history[0] if isinstance(role_history[0], dict) else {}
    responsibilities = _list(recent.get("responsibilities"))
    skills_used = _list(recent.get("skills_used"))
    achievement_verbs = (
        "implemented", "built", "developed", "delivered", "launched", "led", "owned", "architected",
        "designed", "automated", "migrated", "optimized", "improved", "reduced", "increased", "deployed"
    )
    achievements = []
    for item in responsibilities:
        text = clean_value(item, 220)
        if not text:
            continue
        lower = text.lower()
        if any(verb in lower for verb in achievement_verbs) or re.search(r"\b\d+%|\b\d+\s*(?:users?|clients?|transactions?|tickets?|requests?|jobs?|records?)\b", lower):
            achievements.append(text)
    if not achievements:
        achievements = responsibilities[:4]
    if not achievements and _list(parsed_candidate.get("ownership_signals")):
        achievements = [f"Ownership signals: {', '.join(_list(parsed_candidate.get('ownership_signals'))[:4])}"]
    return {
        "title": clean_value(recent.get("title") or "", 90),
        "company": clean_value(recent.get("company") or "", 90),
        "duration_years": round(float(recent.get("duration_years") or 0), 1),
        "responsibilities": responsibilities[:6],
        "achievements": achievements[:5],
        "skills_used": skills_used[:12],
    }


def _build_validation_gaps(analysis, parsed_jd, parsed_candidate, dashboard):
    gaps = []
    jd_conf = str(parsed_jd.get("parser_confidence") or "").lower()
    cv_conf = str(parsed_candidate.get("experience_metrics", {}).get("experience_confidence") or "").lower()
    jd_source = str(parsed_jd.get("parse_source") or "").lower()
    cv_source = str(parsed_candidate.get("parse_source") or "").lower()
    jd_warnings = _list(parsed_jd.get("parser_warnings"))
    cv_warnings = _list(parsed_candidate.get("parser_warnings"))
    score = _score_value(dashboard.get("overview", {}).get("final_score"))
    if jd_source == "deterministic":
        gaps.append({"area": "JD Parsing", "severity": "medium", "message": "JD used deterministic fallback. Validate role title, must-have skills, and validation evidence.", "evidence": jd_warnings[:3] or ["LLM extraction unavailable"]})
    if cv_source == "deterministic":
        gaps.append({"area": "CV Parsing", "severity": "medium", "message": "CV used deterministic fallback. Validate current role, company, and skill extraction.", "evidence": cv_warnings[:3] or ["LLM extraction unavailable"]})
    if jd_conf == "low":
        gaps.append({"area": "JD Confidence", "severity": "high", "message": "JD parser confidence is low. This match should be reviewed before action.", "evidence": jd_warnings[:4] or []})
    if cv_conf == "low":
        gaps.append({"area": "CV Confidence", "severity": "high", "message": "CV chronology or experience confidence is low. Validate recent experience manually.", "evidence": cv_warnings[:4] or []})
    if not parsed_jd.get("role_family"):
        gaps.append({"area": "JD Role Family", "severity": "medium", "message": "Role family could not be mapped cleanly from the JD.", "evidence": parsed_jd.get("role_taxonomy", [])[:3]})
    if not parsed_candidate.get("role_family"):
        gaps.append({"area": "CV Role Family", "severity": "medium", "message": "Role family could not be mapped cleanly from the CV.", "evidence": parsed_candidate.get("normalized_roles", [])[:3]})
    missing = dashboard.get("skill_matrix", {}).get("missing_must_have", [])[:5]
    if missing:
        gaps.append({"area": "Must-Have Skills", "severity": "medium" if len(missing) <= 3 else "high", "message": "Some must-have skills are missing or only partially evidenced.", "evidence": missing})
    exp = dashboard.get("experience_comparison", {})
    if exp.get("fit_summary") and not exp.get("is_within_range"):
        gaps.append({"area": "Experience", "severity": "medium", "message": exp.get("fit_summary"), "evidence": [exp.get("jd_required", "-"), f"{exp.get('candidate_years', 0)} years"]})
    if score and score < 60:
        gaps.append({"area": "Overall Match", "severity": "medium", "message": "This is a lower-confidence match and should be reviewed before submission.", "evidence": [f"Score {score}%"]})
    return gaps[:10]


def _build_manual_review(dashboard, parsed_jd, parsed_candidate):
    reasons = []
    jd_source = str(parsed_jd.get("parse_source") or "").lower()
    cv_source = str(parsed_candidate.get("parse_source") or "").lower()
    jd_conf = str(parsed_jd.get("parser_confidence") or "").lower()
    cv_conf = str(parsed_candidate.get("experience_metrics", {}).get("experience_confidence") or "").lower()
    score = _score_value(dashboard.get("overview", {}).get("final_score"))
    gaps = _list(dashboard.get("validation_gaps"))

    if jd_source == "deterministic":
        reasons.append("JD required deterministic fallback.")
    if cv_source == "deterministic":
        reasons.append("CV required deterministic fallback.")
    if jd_conf == "low":
        reasons.append("JD parser confidence is low.")
    if cv_conf == "low":
        reasons.append("CV experience confidence is low.")
    if not parsed_jd.get("role_family"):
        reasons.append("JD role family is unclear.")
    if not parsed_candidate.get("role_family"):
        reasons.append("CV role family is unclear.")
    if not parsed_jd.get("must_have_skills"):
        reasons.append("JD must-have skills are sparse or unclear.")
    if not parsed_candidate.get("normalized_skills"):
        reasons.append("CV skills are sparse or unclear.")
    if any(str(g.get("severity", "")).lower() == "high" for g in gaps):
        reasons.append("One or more validation gaps are high severity.")
    if score and score < 55:
        reasons.append(f"Score {score}% is below the auto-trust threshold.")
    if parsed_candidate.get("red_flags"):
        flags = [str(flag) for flag in _list(parsed_candidate.get("red_flags"))[:3]]
        reasons.extend(flags)

    reasons = unique_list([clean_value(reason, 180) for reason in reasons if reason], 10)
    required = bool(reasons)
    return {
        "required": required,
        "reasons": reasons,
        "summary": "Manual recruiter review required before action." if required else "Automated review looks usable.",
    }


def build_match_dashboard(analysis):
    score_breakdown = analysis.get("score_breakdown") or (analysis.get("score_json") or {}).get("score_breakdown") or {}
    if isinstance(score_breakdown, list):
        mapped_breakdown = {}
        for item in score_breakdown:
            if not isinstance(item, dict):
                continue
            key = item.get("key") or item.get("label") or "item"
            mapped_breakdown[key] = {
                "score": item.get("score", 0),
                "reason": item.get("reason", ""),
                "matched_items": item.get("matched_items", []),
                "missing_items": item.get("missing_items", []),
            }
        score_breakdown = mapped_breakdown
    deterministic_snapshot = analysis.get("deterministic_match_snapshot") or {}
    parsed_jd = analysis.get("parsed_jd") or analysis.get("jd_json") or {}
    parsed_candidate = analysis.get("parsed_candidate") or analysis.get("cv_json") or {}
    explainability = analysis.get("explainability") or {}
    final_score = _score_value(analysis.get("final_score") or (analysis.get("score_json") or {}).get("final_score") or analysis.get("score"))
    structured_score = _score_value(analysis.get("structured_score") or final_score)
    semantic_score = _score_value(analysis.get("semantic_score") or analysis.get("semantic_similarity_score"))
    hard_filter_score = _score_value(analysis.get("hard_filter_score") or (analysis.get("hard_filters") or {}).get("hard_filter_score"))
    matched = _list(analysis.get("matched_must_have_skills") or (analysis.get("score_json") or {}).get("matched_must_have_skills") or explainability.get("matched_skills"))
    missing = _list(analysis.get("missing_must_have_skills") or (analysis.get("score_json") or {}).get("missing_must_have_skills") or explainability.get("missing_skills"))
    strengths = _list(analysis.get("strengths") or (analysis.get("score_json") or {}).get("strengths") or explainability.get("strengths"))
    concerns = _list(analysis.get("concerns") or (analysis.get("score_json") or {}).get("concerns") or explainability.get("concerns"))
    penalties = _list(analysis.get("penalties_applied") or (analysis.get("score_json") or {}).get("penalties_applied") or explainability.get("penalties_applied"))
    semantic_insights = _list(analysis.get("semantic_match_insights") or explainability.get("semantic_match_insights"))
    role_reasoning = _list(analysis.get("role_alignment_reasoning") or explainability.get("role_alignment_reasoning"))
    weights = {
        "must_have_skills": 0.45,
        "role_profile_buckets": 0.15,
        "role_alignment": 0.14,
        "role_relevance": 0.20,
        "experience_fit": 0.15,
        "education_fit": 0.08,
        "domain_fit": 0.06,
        "seniority_fit": 0.04,
        "stability": 0.04,
        "location_fit": 0.02,
        "cv_structure": 0.02,
        "nice_to_have": 0.00,
        "secondary_skills": 0.05,
        "mandatory_skills": 0.30,
        "domain_context": 0.10,
        "risk_stability": 0.08,
    }
    labels = {
        "must_have_skills": "Must-Have Skills",
        "role_profile_buckets": "Role Profile Buckets",
        "role_alignment": "Role Alignment",
        "role_relevance": "Role Relevance",
        "experience_fit": "Experience Fit",
        "education_fit": "Education Fit",
        "domain_fit": "Domain Fit",
        "seniority_fit": "Seniority Fit",
        "stability": "Career Stability",
        "location_fit": "Location Fit",
        "cv_structure": "CV Structure",
        "nice_to_have": "Nice-to-Have",
        "secondary_skills": "Secondary Skills",
        "mandatory_skills": "Mandatory Skills",
        "domain_context": "Domain Context",
        "risk_stability": "Risk & Stability",
    }
    breakdown = []
    if analysis.get("hard_filters"):
        breakdown.append(_breakdown_item("Hard Filters", {
            "score": hard_filter_score,
            "reason": "Mandatory screening gates for experience, certifications, location, and career gaps.",
            "matched_items": [f.get("name") for f in _list((analysis.get("hard_filters") or {}).get("filters")) if f.get("passed")],
            "missing_items": [f.get("name") for f in _list((analysis.get("hard_filters") or {}).get("filters")) if not f.get("passed")],
        }, 0.20))
    for key, value in score_breakdown.items():
        breakdown.append(_breakdown_item(labels.get(key, key.replace("_", " ").title()), value, weights.get(key, 0)))
    candidate_domains = parsed_candidate.get("domain_experience") or [
        d.get("domain") for d in _list(parsed_candidate.get("domain_confidence_scores")) if d.get("domain")
    ]
    if (parsed_candidate.get("taxonomy") or {}).get("primary_domain_family"):
        candidate_domains = unique_list([((parsed_candidate.get("taxonomy") or {}).get("primary_domain_family"))] + candidate_domains, 6)
    top_skills = (
        parsed_candidate.get("normalized_skills") or
        parsed_candidate.get("primary_skills") or
        parsed_candidate.get("tools_technologies") or
        []
    )
    education = parsed_candidate.get("education") or []
    if isinstance(education, str):
        education = [education]
    experience = (parsed_candidate.get("experience_metrics") or {}).get("total_years_experience")
    if experience is None:
        experience = parsed_candidate.get("total_experience_years", 0)
    confidence = confidence_for(analysis)
    overview = {
        "final_score": final_score,
        "structured_score": structured_score,
        "semantic_score": semantic_score,
        "hard_filter_score": hard_filter_score,
        "verdict": analysis.get("verdict") or (analysis.get("score_json") or {}).get("verdict") or verdict_for(final_score),
        "recommendation": analysis.get("recommendation") or (analysis.get("score_json") or {}).get("recommendation") or recommendation_for(final_score, missing),
        "confidence": confidence,
        "routing": confidence.get("route", {}),
        "scoring_source": analysis.get("scoring_source") or analysis.get("score_source") or (analysis.get("score_json") or {}).get("scoring_source") or "deterministic",
        "deterministic_final_score": _score_value(deterministic_snapshot.get("final_score")),
        "deterministic_verdict": deterministic_snapshot.get("verdict", ""),
    }
    snapshot = {
        "candidate_name": parsed_candidate.get("candidate_name", ""),
        "current_role": parsed_candidate.get("current_role", ""),
        "experience_years": experience or 0,
        "education": education,
        "domains": candidate_domains,
        "top_skills": top_skills[:12],
        "location": parsed_candidate.get("location", ""),
        "employment_status": parsed_candidate.get("current_employment_status", ""),
        "last_employed_date": parsed_candidate.get("last_employed_date", ""),
        "career_gap_periods": parsed_candidate.get("career_gap_periods", []),
        "career_stability_detail": parsed_candidate.get("career_stability_detail", {}),
        "cv_structure_quality": parsed_candidate.get("cv_structure_quality", {}),
        "ai_optimization_risk": parsed_candidate.get("ai_optimization_risk", {}),
    }
    role_history = []
    for role in _list(parsed_candidate.get("role_history")):
        if not isinstance(role, dict):
            continue
        role_history.append({
            "title": role.get("title", ""),
            "company": role.get("company", ""),
            "duration_years": role.get("duration_years", 0),
            "duration_months": role.get("duration_months", 0),
            "start": role.get("start", ""),
            "end": role.get("end", ""),
            "responsibilities": _list(role.get("responsibilities"))[:8],
            "skills_used": _list(role.get("skills_used"))[:10],
        })
    dashboard = {
        "overview": overview,
        "score_breakdown": breakdown,
        "strengths": strengths,
        "concerns": concerns,
        "parsed_jd": parsed_jd,
        "parsed_candidate": parsed_candidate,
        "candidate_summary": {
            "score_percent": final_score,
            "verdict": overview["verdict"],
            "recommendation": overview["recommendation"],
            "confidence": confidence,
        },
        "role_family_comparison": _build_role_family_comparison(parsed_jd, parsed_candidate, final_score),
        "experience_comparison": _build_experience_comparison(parsed_jd, parsed_candidate),
        "tech_skills_experience_years": _build_skill_years(parsed_candidate),
        "recent_professional_experience": _build_recent_experience(parsed_candidate),
        "skill_matrix": {
            "matched_must_have": matched,
            "missing_must_have": missing,
            "jd_must_have": parsed_jd.get("must_have_skills") or [
                i.get("skill") for i in _list(parsed_jd.get("must_have_skills_weighted")) if i.get("skill")
            ],
            "candidate_skills": top_skills,
        },
        "candidate_snapshot": snapshot,
        "role_history": role_history,
        "penalties": penalties,
        "semantic_insights": semantic_insights,
        "role_alignment_reasoning": role_reasoning,
        "validation_gaps": _build_validation_gaps(analysis, parsed_jd, parsed_candidate, {
            "overview": overview,
            "skill_matrix": {
                "missing_must_have": missing
            },
            "experience_comparison": _build_experience_comparison(parsed_jd, parsed_candidate)
        }),
        "manual_review": {},
        "hard_filters": analysis.get("hard_filters") or {},
        "recruiter_summary": "",
    }
    dashboard["manual_review"] = _build_manual_review(dashboard, parsed_jd, parsed_candidate)
    dashboard["overview"]["manual_review_required"] = dashboard["manual_review"]["required"]
    confidence = dashboard["overview"].get("confidence") or {}
    route_label = confidence.get("route", {}).get("label", "Recruiter review")
    if dashboard["manual_review"]["required"]:
        route_label = "Manual review"
        route_reason = dashboard["manual_review"].get("summary") or "Manual recruiter review required before action."
    else:
        route_reason = confidence.get("route", {}).get("reason", "Recruiter should review this case.")
    dashboard["overview"]["routing"] = {
        "label": route_label,
        "reason": route_reason,
    }
    dashboard["recruiter_summary"] = build_recruiter_summary(analysis, dashboard)
    return dashboard
