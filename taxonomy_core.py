import re


ROLE_FAMILIES = {
    "Software Engineering": {
        "signals": ["software engineer", "developer", "backend", "frontend", "full stack", "web application"],
        "skill_families": ["backend", "frontend", "api", "delivery"],
    },
    "Data Engineering": {
        "signals": ["data engineer", "etl", "elt", "data pipeline", "lakehouse", "warehouse"],
        "skill_families": ["data", "cloud", "delivery"],
    },
    "Data Science": {
        "signals": ["data scientist", "machine learning", "ml engineer", "ai engineer"],
        "skill_families": ["data", "ml", "deployment"],
    },
    "DevOps / Cloud Engineering": {
        "signals": ["devops", "sre", "site reliability", "cloud engineer", "platform engineer"],
        "skill_families": ["cloud", "containers", "automation", "observability", "scripting"],
    },
    "Software Architecture": {
        "signals": ["software architect", "solution architect", "technical architect", "architecture", "architectural roadmap"],
        "skill_families": ["architecture", "systems", "api/platform", "cloud/runtime", "security/reliability", "leadership"],
    },
    "Quality Assurance": {
        "signals": ["qa", "quality", "test engineer", "automation testing", "sdet", "test automation"],
        "skill_families": ["automation", "programming", "api testing", "ci cd", "test strategy"],
    },
    "Manufacturing / Tool Room": {
        "signals": ["tool room", "cnc", "edm", "manufacturing", "production", "shop floor"],
        "skill_families": ["tool room", "machines", "maintenance", "quality"],
    },
    "Sales": {
        "signals": ["sales", "business development", "bde", "territory sales", "field sales"],
        "skill_families": ["sales", "customer", "pipeline"],
    },
    "Finance / Accounts": {
        "signals": ["accountant", "accounts", "finance", "gst", "tds", "taxation", "audit"],
        "skill_families": ["finance", "reporting", "compliance"],
    },
    "Human Resources": {
        "signals": ["hr", "human resources", "recruiter", "talent acquisition", "payroll", "employee relations"],
        "skill_families": ["hr", "payroll", "employee relations"],
    },
    "IT Infrastructure / Systems Administration": {
        "signals": ["active directory", "windows server", "system administrator", "scom", "pki", "azure ad", "entra id", "iam"],
        "skill_families": ["identity", "windows", "infrastructure", "security"],
    },
}

DOMAIN_FAMILIES = {
    "Cloud Infrastructure": ["cloud infrastructure", "cloud platform", "kubernetes", "terraform", "deployment automation"],
    "Platform Architecture": ["software architect", "solution architect", "distributed systems", "control plane", "policy engine", "api ecosystem"],
    "IT Infrastructure / IAM": ["active directory", "azure ad", "entra id", "identity access management", "windows server", "scom", "pki"],
    "Web Application Development": ["web development", "frontend", "backend", "full stack", "angular", "node.js", "typescript", "javascript"],
    "Embedded / Automotive Software": ["embedded software", "embedded c", "autosar", "rtos", "qnx", "iso 26262", "aspice", "misra"],
    "Observability": ["observability", "monitoring", "telemetry", "prometheus", "grafana", "opentelemetry"],
    "Manufacturing": ["manufacturing", "plant", "factory", "shop floor", "assembly line", "machine operation"],
    "Sales / Distribution": ["sales", "business development", "field sales", "territory", "channel"],
    "Finance / Accounting": ["accounts", "accounting", "gst", "tds", "audit", "finance operations"],
}

SENIORITY_PATTERNS = [
    ("Principal/Architect", [r"\b(principal|staff|architect|head|director|vp|vice president|gm|general manager)\b"]),
    ("Lead", [r"\b(lead|manager|supervisor|incharge|in-charge|assistant manager|deputy manager)\b"]),
    ("Senior", [r"\b(senior|sr\.?|executive|engineer|officer)\b"]),
    ("Mid-Level", [r"\b(junior|fresher|entry|trainee|apprentice|associate)\b"]),
]


def normalize_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def pick_best_category(text, mapping):
    text_l = normalize_text(text)
    ranked = []
    for category, hints in mapping.items():
        matched = [
            hint for hint in hints
            if re.search(r"(?<![a-z0-9])" + re.escape(hint.lower()) + r"(?![a-z0-9])", text_l)
        ]
        if matched:
            ranked.append((len(matched), category, matched))
    ranked.sort(reverse=True)
    return ranked[0] if ranked else None


def infer_role_family(text, years=0):
    text_l = normalize_text(text)
    ranked = []
    for family, config in ROLE_FAMILIES.items():
        signals = config.get("signals", [])
        matched = [signal for signal in signals if signal in text_l]
        if matched:
            confidence = round(min(0.98, 0.55 + len(matched) * 0.12 + (0.05 if years and years >= 6 else 0)), 2)
            ranked.append({
                "family": family,
                "confidence": confidence,
                "matched_signals": matched[:8],
                "skill_families": config.get("skill_families", []),
            })
    return sorted(ranked, key=lambda item: item["confidence"], reverse=True)


def infer_domain_family(text):
    text_l = normalize_text(text)
    ranked = []
    for domain, hints in DOMAIN_FAMILIES.items():
        matched = [hint for hint in hints if hint in text_l]
        if matched:
            ranked.append({
                "domain": domain,
                "confidence": round(min(0.95, 0.5 + len(matched) * 0.14), 2),
                "matched_signals": matched[:8],
            })
    return sorted(ranked, key=lambda item: item["confidence"], reverse=True)


def infer_seniority_family(text, years=0):
    text_l = normalize_text(text)
    for label, patterns in SENIORITY_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, text_l):
                return label
    if years >= 6:
        return "Senior"
    if years >= 3:
        return "Mid-Level"
    return ""


def family_bucket_matches(role_family_name, skill_names):
    profile = ROLE_FAMILIES.get(role_family_name or "", {})
    buckets = profile.get("skill_families", []) or []
    skill_blob = normalize_text(" ".join(skill_names or []))
    matched = [bucket for bucket in buckets if bucket and bucket in skill_blob]
    return {
        "role_family": role_family_name or "",
        "skill_families": buckets,
        "matched_skill_families": matched,
    }


def build_taxonomy_bundle(text, skills=None, years=0):
    role_ranked = infer_role_family(text, years)
    domain_ranked = infer_domain_family(text)
    seniority = infer_seniority_family(text, years)
    primary_role = role_ranked[0] if role_ranked else {}
    primary_domain = domain_ranked[0] if domain_ranked else {}
    bucket_map = family_bucket_matches(primary_role.get("family", ""), skills or [])
    return {
        "role_families": role_ranked,
        "domain_families": domain_ranked,
        "seniority": seniority,
        "primary_role_family": primary_role.get("family", ""),
        "primary_role_confidence": primary_role.get("confidence", 0),
        "primary_domain_family": primary_domain.get("domain", ""),
        "primary_domain_confidence": primary_domain.get("confidence", 0),
        "skill_family_match": bucket_map,
    }


def family_bucket_score(role_family_name, skill_names):
    profile = ROLE_FAMILIES.get(role_family_name or "", {})
    buckets = profile.get("skill_families", []) or []
    if not buckets:
        return {
            "score": 0,
            "matched_buckets": [],
            "missing_buckets": [],
        }
    skill_blob = normalize_text(" ".join(skill_names or []))
    matched = [bucket for bucket in buckets if bucket and bucket in skill_blob]
    missing = [bucket for bucket in buckets if bucket not in matched]
    score = round((len(matched) / len(buckets)) * 100) if buckets else 0
    return {
        "score": score,
        "matched_buckets": matched,
        "missing_buckets": missing,
    }
