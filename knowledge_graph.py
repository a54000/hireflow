from skill_aliases import canonical_skill


RELATED_SKILL_GROUPS = [
    {
        "Cloud Infrastructure", "Cloud Platform", "Multi-cloud Infrastructure", "Kubernetes",
        "Platform Scalability", "Deployment Automation", "Cloud Security",
        "Hyperconverged Infrastructure", "AWS", "AWS EC2", "AWS S3", "AWS RDS", "AWS CloudWatch",
        "Microsoft Azure", "Google Cloud Platform", "Docker"
    },
    {
        "Active Directory", "Azure Active Directory", "Microsoft Entra ID",
        "Identity and Access Management", "Windows Server",
        "System Center Operations Manager", "PKI", "Certificate Management"
    },
    {
        "Technical Product Management", "Product Management", "Platform Product Management",
        "Roadmap Management", "Backlog Prioritization", "Customer-facing Product Management",
        "Customer Requirement Translation", "Engineering Collaboration", "Cross-functional Leadership",
        "Stakeholder Management", "POC", "Technical GTM", "Enterprise SaaS"
    },
    {
        "Internal Tools", "Tool Development", "Automation", "Build Automation",
        "Release Automation", "Deployment Automation", "CI/CD", "DevOps"
    },
    {"Observability Tooling", "Prometheus", "Grafana", "OpenTelemetry"},
    {"Lean Six Sigma", "Manufacturing", "Plant Operations", "Quality Management", "Supply Chain"},
    {"Financial Analysis", "Accounting", "Audit", "Tax", "Banking / Financial Services"},
]


ROLE_RELATIONSHIPS = {
    "Platform Product Management": {"Product Management", "DevOps", "Cloud Infrastructure"},
    "Product Management": {"Platform Product Management", "Business Analysis"},
    "DevOps": {"Cloud Infrastructure", "Software Engineering"},
    "Data Engineering": {"Data Science", "Software Engineering"},
}


def related_skills(skill):
    canonical = canonical_skill(skill)
    for group in RELATED_SKILL_GROUPS:
        if canonical in group:
            return sorted(group - {canonical})
    return []


def related_skill_credit(required_skill, candidate_skills):
    candidate_set = {canonical_skill(s) for s in candidate_skills or []}
    matches = [s for s in related_skills(required_skill) if s in candidate_set]
    if not matches:
        return 0, []
    canonical = canonical_skill(required_skill)
    strict_skills = {"Kubernetes"}
    if canonical in strict_skills and not ({canonical} & candidate_set):
        return 0, []
    if canonical in {"Cloud Platform", "Cloud Infrastructure"}:
        cloud_evidence = {"AWS", "AWS EC2", "AWS S3", "AWS RDS", "AWS CloudWatch", "Microsoft Azure", "Google Cloud Platform", "Docker", "Terraform", "Cloud Security", "Multi-cloud Infrastructure"}
        evidence_matches = sorted(candidate_set & cloud_evidence)
        if evidence_matches:
            return 0.55, evidence_matches
    if canonical in {"Internal Tools", "Tool Development", "Automation"}:
        tool_evidence = {"Internal Tools", "Tool Development", "Automation", "Build Automation", "Release Automation", "Deployment Automation", "CI/CD", "DevOps"}
        evidence_matches = sorted(candidate_set & tool_evidence)
        if evidence_matches:
            return 0.65, evidence_matches
    if canonical == "Observability Tooling" and not (candidate_set & {"Prometheus", "Grafana", "OpenTelemetry", "Observability Tooling", "System Center Operations Manager"}):
        return 0, []
    if canonical in {"Technical Product Management", "Platform Product Management", "Customer-facing Product Management"}:
        return 0.85, matches
    return 0.6, matches


def related_roles(role):
    return sorted(ROLE_RELATIONSHIPS.get(role, set()))


def role_relationship_credit(jd_roles, candidate_roles):
    jd_set = set(jd_roles or [])
    candidate_set = set(candidate_roles or [])
    if jd_set & candidate_set:
        return 1.0, sorted(jd_set & candidate_set)
    for role in jd_set:
        related = set(related_roles(role))
        matches = sorted(related & candidate_set)
        if matches:
            return 0.75, matches
    return 0, []
