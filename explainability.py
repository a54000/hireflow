def build_explainability(jd, candidate, structured_result, semantic_score):
    breakdown = structured_result.get("score_breakdown", {})
    matched = structured_result.get("matched_must_have_skills", [])
    missing = structured_result.get("missing_must_have_skills", [])
    strengths = []
    concerns = []

    if matched:
        strengths.append("Matches required skills: " + ", ".join(matched[:8]))
    if breakdown.get("role_alignment", {}).get("score", 0) >= 80:
        strengths.append(breakdown["role_alignment"]["reason"])
    if breakdown.get("domain_fit", {}).get("score", 0) >= 75:
        strengths.append(breakdown["domain_fit"]["reason"])
    if breakdown.get("experience_fit", {}).get("score", 0) >= 80:
        strengths.append(breakdown["experience_fit"]["reason"])
    if breakdown.get("education_fit", {}).get("score", 0) >= 80:
        strengths.append(breakdown["education_fit"]["reason"])
    if breakdown.get("stability", {}).get("score", 0) >= 75:
        strengths.append("Career stability: " + breakdown["stability"]["reason"])
    if breakdown.get("location_fit", {}).get("score", 0) >= 80:
        strengths.append(breakdown["location_fit"]["reason"])
    if breakdown.get("cv_structure", {}).get("score", 0) >= 75:
        strengths.append("CV structure looks professional: " + breakdown["cv_structure"]["reason"])
    if candidate.get("ownership_signals"):
        strengths.append("Shows ownership signals: " + ", ".join(candidate["ownership_signals"][:5]))

    if missing:
        concerns.append("Missing required skills: " + ", ".join(missing[:8]))
    if jd.get("mandatory_skills_prompt_required"):
        concerns.append(jd.get("mandatory_skills_prompt") or "Please input mandatory tech skills in custom screening checks.")
    for key in ["experience_fit", "education_fit", "must_have_skills", "role_alignment", "domain_fit", "seniority_fit", "stability", "location_fit", "cv_structure"]:
        item = breakdown.get(key, {})
        if item.get("score", 100) < 60:
            concerns.append(item.get("reason", key.replace("_", " ").title()))

    semantic_insights = []
    if semantic_score >= 75:
        semantic_insights.append("The resume describes similar work to this job, even when the wording is not exactly the same.")
    elif semantic_score >= 50:
        semantic_insights.append("Some parts of the resume are related to this job, but the match is not consistent across the whole profile.")
    else:
        semantic_insights.append("The resume does not describe much work that looks similar to this job.")
    domain_item = breakdown.get("domain_fit", {})
    if domain_item:
        matched_domains = domain_item.get("matched_items") or []
        missing_domains = domain_item.get("missing_items") or []
        if matched_domains and missing_domains:
            semantic_insights.append(
                "Domain fit is partial because the resume shows "
                + ", ".join(matched_domains[:3])
                + " experience, but the job also needs "
                + ", ".join(missing_domains[:3])
                + "."
            )
        elif matched_domains:
            semantic_insights.append("Domain fit is strong because both the job and resume point to " + ", ".join(matched_domains[:3]) + ".")
        elif missing_domains:
            semantic_insights.append("Domain fit is weak because the resume does not clearly show " + ", ".join(missing_domains[:3]) + " experience.")

    return {
        "strengths": strengths[:8],
        "concerns": concerns[:8],
        "penalties_applied": structured_result.get("penalties_applied", []),
        "matched_skills": matched,
        "missing_skills": missing,
        "role_alignment_reasoning": [breakdown.get("role_alignment", {}).get("reason", "")],
        "semantic_match_insights": semantic_insights,
    }
