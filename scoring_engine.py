from skill_aliases import canonical_skill
from role_taxonomy import primary_role_category
from knowledge_graph import related_skill_credit, role_relationship_credit
from role_profiles import bucket_matches
from taxonomy_core import family_bucket_score


WEIGHTS = {
    "must_have_skills": 0.40,
    "role_alignment": 0.20,
    "experience_fit": 0.15,
    "domain_fit": 0.10,
    "seniority_fit": 0.10,
    "nice_to_have": 0.05,
}

def _canonical_set(values):
    return {canonical_skill(v).lower() for v in values or [] if canonical_skill(v)}


def _taxonomy_family(record, key, fallback=""):
    taxonomy = record.get("taxonomy") or {}
    if key == "role":
        return record.get("role_family") or taxonomy.get("primary_role_family") or fallback
    if key == "domain":
        return record.get("domain_family") or taxonomy.get("primary_domain_family") or fallback
    if key == "seniority":
        return record.get("seniority_family") or taxonomy.get("seniority") or fallback
    return fallback


def _is_web_fullstack_jd(jd):
    roles = {r.get("role") for r in jd.get("role_taxonomy", []) if r.get("role")}
    skills = _canonical_set(jd.get("must_have_skills", []) + jd.get("nice_to_have_skills", []))
    web_skills = {"c#", ".net", "angular", "javascript", "typescript", "node.js", "html", "css", "rest api"}
    return "Web / Full Stack Engineering" in roles or len(skills & web_skills) >= 3


def _is_embedded_candidate(candidate):
    roles = set(candidate.get("normalized_roles") or [])
    skills = _canonical_set(candidate.get("normalized_skills", []))
    embedded_skills = {"embedded c", "embedded software", "embedded systems", "autosar", "rtos", "qnx", "can", "spi", "i2c", "uart", "pcie", "misra c", "iso 26262", "aspice"}
    domains = {d.get("domain") for d in candidate.get("domain_confidence_scores", []) if d.get("domain")}
    return "Embedded Software Engineering" in roles or len(skills & embedded_skills) >= 4 or "Embedded / Automotive Software" in domains


def _score_item(score, reason, matched=None, missing=None):
    return {
        "score": int(max(0, min(100, round(score)))),
        "reason": reason,
        "matched_items": matched or [],
        "missing_items": missing or []
    }


def score_must_have(jd, candidate):
    required_items = jd.get("must_have_skills_weighted") or []
    candidate_skills = _canonical_set(candidate.get("normalized_skills", []))
    candidate_skill_values = candidate.get("normalized_skills", [])
    matched, missing, adjacent = [], [], []
    total_weight, matched_weight = 0, 0
    for item in required_items:
        skill = canonical_skill(item.get("skill"))
        weight = int(item.get("weight") or 70)
        total_weight += weight
        if skill.lower() in candidate_skills:
            matched.append(skill)
            matched_weight += weight
        else:
            credit, related_matches = related_skill_credit(skill, candidate_skill_values)
            if credit:
                adjacent.append(f"{skill} via {', '.join(related_matches[:3])}")
                matched_weight += weight * credit
            else:
                missing.append(skill)
    score = (matched_weight / total_weight * 100) if total_weight else 0
    if missing:
        observability_missing = {"Prometheus", "Grafana", "OpenTelemetry", "Observability Tooling"}
        if set(missing).issubset(observability_missing):
            score = max(0, score - min(6, len(missing) * 2))
        else:
            score = max(0, score - min(18, len(missing) * 4))
    return _score_item(score, "Weighted must-have skill coverage with related-skill credit", matched + adjacent, missing)


def score_role_profile_buckets(jd, candidate):
    profile = jd.get("role_profile") or {}
    jd_family = _taxonomy_family(jd, "role")
    candidate_family = _taxonomy_family(candidate, "role")
    candidate_skills = candidate.get("normalized_skills", [])
    if profile:
        buckets = bucket_matches(profile, candidate_skills)
        if not buckets:
            return _score_item(60, "Role profile has no configured buckets.", [], [])
        passed = [item for item in buckets if item.get("passed")]
        missing = [f"{item['bucket']}: one of {', '.join(item.get('options', [])[:5])}" for item in buckets if not item.get("passed")]
        matched = [f"{item['bucket']}: {', '.join(item.get('matched', []))}" for item in passed]
        score = len(passed) / len(buckets) * 100
        if jd_family and candidate_family and jd_family == candidate_family:
            score = min(100, score + 10)
            matched.insert(0, f"role family: {candidate_family}")
        return _score_item(score, f"Role profile bucket fit for {profile.get('name')}.", matched, missing)
    if jd_family:
        family_fit = family_bucket_score(jd_family, candidate_skills)
        if family_fit["score"] or candidate_family == jd_family:
            matched = [f"role family: {jd_family}"] if candidate_family == jd_family else []
            if family_fit["matched_buckets"]:
                matched.extend([f"{b} skills" for b in family_fit["matched_buckets"][:4]])
            missing = [f"{b} skills" for b in family_fit["missing_buckets"][:4]]
            score = family_fit["score"]
            if candidate_family == jd_family:
                score = min(100, score + 12)
            return _score_item(score, f"Taxonomy bucket fit for {jd_family}.", matched, missing)
        if candidate_family:
            return _score_item(45, "The role family is related, but the candidate does not show enough bucket coverage for this job.", [candidate_family], [jd_family])
    return _score_item(55, "No role profile bucket model was detected for this JD.", [], [])


def score_role_alignment(jd, candidate):
    jd_roles = [r.get("role") for r in jd.get("role_taxonomy", []) if r.get("role")]
    jd_role_family = _taxonomy_family(jd, "role")
    candidate_roles = candidate.get("normalized_roles", [])
    latest_role_title = candidate.get("current_role", "")
    if not latest_role_title and candidate.get("role_history"):
        latest_role_title = (candidate.get("role_history") or [{}])[0].get("title", "")
    current_role_category = primary_role_category(latest_role_title)
    candidate_role_family = _taxonomy_family(candidate, "role", current_role_category)
    if _is_web_fullstack_jd(jd) and _is_embedded_candidate(candidate):
        candidate_skills = _canonical_set(candidate.get("normalized_skills", []))
        web_required = {"c#", ".net", "angular", "javascript", "typescript", "node.js", "html", "css"}
        if len(candidate_skills & web_required) <= 1:
            return _score_item(
                15,
                "The candidate is a software engineer, but the recent work is embedded/automotive rather than web or full-stack application development.",
                [],
                ["Web / Full Stack Engineering"]
            )
    matched = [r for r in jd_roles if r in candidate_roles]
    if jd_role_family and candidate_role_family and jd_role_family == candidate_role_family:
        return _score_item(92, "The candidate's role family matches the role family required by this job.", [candidate_role_family], [])
    if matched and current_role_category in jd_roles:
        return _score_item(95, "The candidate's current job type matches what this job is looking for.", matched, [])
    if "Platform Product Management" in jd_roles and "Product Management" in candidate_roles and current_role_category in {"Product Management", "Platform Product Management"}:
        return _score_item(92, "The latest role is product-focused and closely matches the platform product work in this job.", ["Product Management"], ["Platform Product Management"])
    if matched:
        return _score_item(60, "The resume has some similar job experience, but the current role is not clearly the same as this opening.", matched, jd_roles)
    if "Platform Product Management" in jd_roles and "Product Management" in candidate_roles:
        return _score_item(88, "The candidate has product management experience that is close to the platform product work required.", ["Product Management"], ["Platform Product Management"])
    if "Product Management" in jd_roles and "Platform Product Management" in candidate_roles:
        return _score_item(92, "The candidate has direct platform product management experience.", ["Platform Product Management"], [])
    relationship_credit, relationship_matches = role_relationship_credit(jd_roles, candidate_roles)
    if relationship_credit:
        score = 72 if current_role_category in candidate_roles else 55
        return _score_item(
            score,
            "The resume shows related job experience, but the current role is not an obvious match for this opening.",
            relationship_matches,
            jd_roles
        )
    if jd_roles and candidate_roles:
        return _score_item(35, "The candidate's job background appears different from what this job needs.", [], jd_roles)
    inferred = primary_role_category(candidate.get("current_role", ""))
    if jd_roles and inferred in jd_roles:
        return _score_item(80, "The current job title looks similar to the role required for this opening.", [inferred], [])
    return _score_item(35 if not jd_roles else 10, "The resume does not show enough evidence that the candidate has done this type of job.", [], jd_roles)


def score_experience_fit(jd, candidate):
    req = jd.get("experience_required") or {}
    min_years = float(req.get("min_years") or 0)
    max_years = float(req.get("max_years") or 0)
    years = float((candidate.get("experience_metrics") or {}).get("total_years_experience") or 0)
    if not min_years and not max_years:
        return _score_item(60, "JD does not specify a firm experience range", [], [])
    if min_years and years < min_years:
        return _score_item((years / min_years) * 65 if min_years else 0, f"Candidate has {years:g} years against {min_years:g}+ required", [f"{years:g} years"], [f"{min_years:g}+ years"])
    if max_years and years > max_years:
        if years <= max_years + 3:
            return _score_item(78, f"Candidate has {years:g} years, slightly above the JD range of {min_years:g}-{max_years:g} years", [f"{years:g} years"], [f"{min_years:g}-{max_years:g} years"])
        return _score_item(60, f"Candidate has {years:g} years, above the JD range of {min_years:g}-{max_years:g} years", [f"{years:g} years"], [f"{min_years:g}-{max_years:g} years"])
    return _score_item(95, "Experience fits the JD range", [f"{years:g} years"], [])


def score_domain_fit(jd, candidate):
    jd_domains = [d.get("domain") for d in jd.get("domain_taxonomy", []) if d.get("domain")]
    candidate_domains = [d.get("domain") for d in candidate.get("domain_confidence_scores", []) if d.get("domain")]
    jd_domain_family = _taxonomy_family(jd, "domain")
    candidate_domain_family = _taxonomy_family(candidate, "domain")
    matched = [d for d in jd_domains if d in candidate_domains]
    if matched:
        return _score_item(
            90,
            "Strong domain fit: the resume shows experience in the same work area as the job.",
            matched,
            sorted(set(jd_domains) - set(candidate_domains))
        )
    if jd_domain_family and candidate_domain_family and jd_domain_family == candidate_domain_family:
        return _score_item(
            88,
            "Strong domain fit from taxonomy mapping: the candidate and job land in the same domain family.",
            [candidate_domain_family],
            []
        )
    infra_domains = {"Cloud Infrastructure", "Hyperconverged Infrastructure", "SaaS"}
    if set(jd_domains) & infra_domains and set(candidate_domains) & infra_domains:
        return _score_item(
            78,
            "Close domain fit: the candidate has related infrastructure or platform experience, but not every job domain is directly shown.",
            sorted(set(candidate_domains) & infra_domains),
            sorted(set(jd_domains) - set(candidate_domains))
        )
    if "Observability" in jd_domains and "Cloud Infrastructure" in candidate_domains:
        return _score_item(
            68,
            "Partial domain fit: cloud infrastructure experience is related to observability work, but direct monitoring or telemetry ownership is not clearly shown.",
            ["Cloud Infrastructure"],
            ["Observability"]
        )
    if not jd_domains:
        return _score_item(60, "The job description does not clearly state an industry or work domain, so domain fit cannot be judged strongly.", [], [])
    if candidate_domains:
        return _score_item(
            10,
            "Not a domain fit: the candidate's experience is from a different work area than this job requires.",
            candidate_domains,
            jd_domains
        )
    return _score_item(0, "Not enough domain evidence: the resume does not clearly show experience in the job's work area.", [], jd_domains)


def score_seniority_fit(jd, candidate):
    jd_seniority = _taxonomy_family(jd, "seniority", jd.get("seniority_level") or "")
    candidate_seniority = _taxonomy_family(candidate, "seniority", candidate.get("seniority_level") or "")
    if not jd_seniority:
        return _score_item(60, "JD seniority is not explicit", [], [])
    if jd_seniority == candidate_seniority:
        return _score_item(95, "Seniority aligns", [candidate_seniority], [])
    compatible = {
        "Lead": {"Senior", "Principal/Architect"},
        "Senior": {"Lead", "Mid-Level", "Principal/Architect"},
        "Mid-Level": {"Senior"},
    }
    if candidate_seniority in compatible.get(jd_seniority, set()):
        return _score_item(72, "Seniority is adjacent but not exact", [candidate_seniority], [jd_seniority])
    return _score_item(40, "Seniority mismatch", [candidate_seniority], [jd_seniority])


def score_nice_to_have(jd, candidate):
    nice = [canonical_skill(s) for s in jd.get("nice_to_have_skills", [])]
    candidate_skills = _canonical_set(candidate.get("normalized_skills", []))
    matched = [s for s in nice if s.lower() in candidate_skills]
    missing = [s for s in nice if s.lower() not in candidate_skills]
    if not nice:
        return _score_item(60, "No nice-to-have skills specified", [], [])
    return _score_item(len(matched) / len(nice) * 100, "Nice-to-have skill coverage", matched, missing)


def deterministic_structured_score(jd, candidate):
    breakdown = {
        "must_have_skills": score_must_have(jd, candidate),
        "role_profile_buckets": score_role_profile_buckets(jd, candidate),
        "role_alignment": score_role_alignment(jd, candidate),
        "experience_fit": score_experience_fit(jd, candidate),
        "domain_fit": score_domain_fit(jd, candidate),
        "seniority_fit": score_seniority_fit(jd, candidate),
        "nice_to_have": score_nice_to_have(jd, candidate),
    }
    if jd.get("role_profile"):
        weights = dict(WEIGHTS)
        weights["must_have_skills"] = 0.30
        weights["role_profile_buckets"] = 0.15
    else:
        weights = dict(WEIGHTS)
        weights["role_profile_buckets"] = 0
    structured = sum(breakdown[k]["score"] * weights.get(k, 0) for k in breakdown)
    penalties = []
    if breakdown["must_have_skills"]["missing_items"]:
        missing = breakdown["must_have_skills"]["missing_items"]
        observability_missing = {"Prometheus", "Grafana", "OpenTelemetry", "Observability Tooling"}
        if set(missing).issubset(observability_missing):
            penalties.append({"reason": "Missing explicit observability tooling", "impact": min(14, len(missing) * 4)})
        else:
            penalties.append({"reason": "Missing must-have skills", "impact": min(28, len(missing) * 8)})
    if breakdown["role_alignment"]["score"] < 45:
        penalties.append({"reason": "Role mismatch", "impact": 25})
    if breakdown["role_profile_buckets"]["score"] < 45:
        penalties.append({"reason": "Role family / bucket mismatch", "impact": 10})
    if breakdown["domain_fit"]["score"] < 45:
        penalties.append({"reason": "Domain mismatch", "impact": 12})
    if breakdown["seniority_fit"]["score"] < 50:
        penalties.append({"reason": "Seniority mismatch", "impact": 12})
    if breakdown["experience_fit"]["score"] < 55:
        penalties.append({"reason": "Experience below requirement", "impact": 18})
    if candidate.get("career_stability_score", 100) < 55:
        penalties.append({"reason": "Career stability is weak or unclear", "impact": 6})
    if _is_web_fullstack_jd(jd) and _is_embedded_candidate(candidate):
        web_required = {"c#", ".net", "angular", "javascript", "typescript", "node.js", "html", "css"}
        candidate_skills = _canonical_set(candidate.get("normalized_skills", []))
        if len(candidate_skills & web_required) <= 1:
            penalties.append({"reason": "Web/full-stack JD vs embedded software background mismatch", "impact": 35})
    structured = max(0, min(100, structured - sum(p["impact"] for p in penalties) * 0.35))
    return {
        "structured_score": int(round(structured)),
        "score_breakdown": breakdown,
        "penalties_applied": penalties,
        "matched_must_have_skills": breakdown["must_have_skills"]["matched_items"],
        "missing_must_have_skills": breakdown["must_have_skills"]["missing_items"],
    }
