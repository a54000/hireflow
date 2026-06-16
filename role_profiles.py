from skill_aliases import canonical_skill, unique_list


ROLE_PROFILES = {
    "Full Stack Developer": {
        "signals": ["full stack", "mern", "mean", "frontend", "backend", "web application"],
        "buckets": {
            "frontend": ["React", "Angular", "Vue.js", "JavaScript", "TypeScript", "HTML", "CSS"],
            "backend": ["Node.js", "Java", ".NET", ".NET Core", "Python", "Spring Boot", "REST API"],
            "database": ["MongoDB", "PostgreSQL", "MySQL", "SQL"],
            "api": ["REST API", "GraphQL", "Microservices"],
            "devops": ["Git", "Docker", "CI/CD", "Jenkins"],
        },
        "nice_buckets": {"cloud": ["AWS", "Microsoft Azure", "Google Cloud Platform", "Kubernetes"]},
    },
    "Backend Developer": {
        "signals": ["backend", "api developer", "server side", "microservices", "python developer", "java developer", ".net developer", "c# developer"],
        "buckets": {
            "backend language": ["Python", "Java", ".NET", ".NET Core", "C#", "Node.js"],
            "api": ["REST API", "GraphQL", "gRPC", "Microservices"],
            "database": ["PostgreSQL", "MySQL", "MongoDB", "SQL"],
            "delivery": ["Git", "Docker", "CI/CD"],
        },
        "nice_buckets": {"cloud": ["AWS", "Microsoft Azure", "Google Cloud Platform", "Kubernetes"]},
    },
    "Frontend Developer": {
        "signals": ["frontend", "front end", "ui developer", "react developer", "angular developer"],
        "buckets": {
            "frontend framework": ["React", "Angular", "Vue.js"],
            "web basics": ["JavaScript", "TypeScript", "HTML", "CSS"],
            "api integration": ["REST API", "GraphQL"],
            "delivery": ["Git", "CI/CD"],
        },
        "nice_buckets": {"testing": ["Playwright", "Cypress", "Selenium"]},
    },
    "SDET / QA Automation": {
        "signals": ["sdet", "qa automation", "test automation", "automation testing"],
        "buckets": {
            "automation": ["Selenium", "Playwright", "Cypress"],
            "programming": ["Java", "Python", "JavaScript", "TypeScript", "C#"],
            "api testing": ["REST API", "Postman"],
            "ci cd": ["CI/CD", "Jenkins", "Git"],
            "test strategy": ["Quality Assurance", "Test Automation"],
        },
        "nice_buckets": {"cloud/devops": ["Docker", "Kubernetes", "AWS", "Microsoft Azure"]},
    },
    "Data Scientist": {
        "signals": ["data scientist", "machine learning", "ml engineer", "ai engineer"],
        "buckets": {
            "language": ["Python", "SQL"],
            "ml": ["Machine Learning", "Artificial Intelligence", "TensorFlow", "PyTorch", "Scikit-learn"],
            "data handling": ["Pandas", "NumPy", "SQL"],
            "deployment": ["Docker", "API", "AWS", "Microsoft Azure"],
        },
        "nice_buckets": {"mlops": ["CI/CD", "Kubernetes", "Airflow"]},
    },
    "Data Engineer": {
        "signals": ["data engineer", "etl", "elt", "data pipeline", "lakehouse"],
        "buckets": {
            "language": ["Python", "SQL", "Java"],
            "processing": ["Apache Spark", "Pyspark", "ETL"],
            "warehouse": ["Snowflake", "Databricks", "PostgreSQL", "SQL"],
            "orchestration": ["Apache Airflow", "CI/CD"],
            "cloud": ["AWS", "Microsoft Azure", "Google Cloud Platform"],
        },
        "nice_buckets": {"devops": ["Docker", "Kubernetes", "Terraform"]},
    },
    "DevOps / Cloud Engineer": {
        "signals": ["devops", "cloud engineer", "sre", "site reliability", "platform engineer"],
        "buckets": {
            "cloud": ["AWS", "Microsoft Azure", "Google Cloud Platform", "Cloud Platform"],
            "containers": ["Docker", "Kubernetes"],
            "automation": ["CI/CD", "Jenkins", "Terraform", "Deployment Automation"],
            "observability": ["Observability Tooling", "Prometheus", "Grafana", "OpenTelemetry"],
            "scripting": ["Python", "PowerShell", "Linux"],
        },
        "nice_buckets": {"security": ["Cloud Security", "Security Architecture"]},
    },
    "Software Architect": {
        "signals": ["software architect", "solution architect", "principal architect", "architecture"],
        "buckets": {
            "architecture": ["Software Architecture", "Solution Architecture", "System Architecture", "Architecture Ownership"],
            "systems": ["Distributed Systems", "Large-scale Systems", "Microservices", "Fault Tolerance", "Resilience"],
            "api/platform": ["API Design", "API Ecosystem", "REST API", "GraphQL", "gRPC"],
            "cloud/runtime": [".NET Core", ".NET", "Docker", "Kubernetes", "Cloud Platform"],
            "security/reliability": ["Security Architecture", "Observability Tooling", "Performance Engineering"],
            "leadership": ["Technical Leadership", "Engineering Leadership", "Architecture Reviews"],
        },
        "nice_buckets": {"security products": ["EDR", "XDR", "SOAR", "Cloud Security"]},
    },
    "Engineering Manager / Head": {
        "signals": ["engineering head", "engineering manager", "director engineering", "head of engineering"],
        "buckets": {
            "leadership": ["Technical Leadership", "Engineering Leadership", "People Management", "Team Management"],
            "delivery": ["Roadmap Management", "Stakeholder Management", "Cross-functional Leadership"],
            "architecture": ["Software Architecture", "System Architecture", "Architecture Reviews"],
            "execution": ["CI/CD", "DevOps", "Agile"],
        },
        "nice_buckets": {"hiring": ["Recruitment", "Training"]},
    },
    "Sales / BDE": {
        "signals": ["sales", "business development", "bde", "field sales", "territory sales"],
        "buckets": {
            "sales": ["Sales", "Business Development", "Field Sales"],
            "customer": ["Customer Relationship Management", "Negotiation", "CRM"],
            "pipeline": ["Lead Generation", "Cold Calling", "Reporting"],
        },
        "nice_buckets": {"territory": ["Territory Management", "Channel Sales"]},
    },
    "Manufacturing / Tool Room": {
        "signals": ["tool room", "tool-room", "cnc", "edm", "manufacturing", "production"],
        "buckets": {
            "tool room": ["Tool Room", "Tool Manufacturing", "Tool Maintenance"],
            "machines": ["CNC Operation", "Wire EDM", "Die Sinker EDM", "VMC", "HMC", "EDM"],
            "maintenance": ["Preventive Maintenance", "Breakdown Maintenance", "Maintenance"],
            "quality": ["Inspection", "5S", "Kaizen"],
        },
        "nice_buckets": {"design": ["Tool Design", "Jig / Fixture", "GD&T"]},
    },
}


def _text_blob(parsed_jd):
    values = [
        parsed_jd.get("role_title", ""),
        parsed_jd.get("primary_role", ""),
        " ".join(parsed_jd.get("must_have_skills", []) or []),
        " ".join(parsed_jd.get("nice_to_have_skills", []) or []),
        " ".join(parsed_jd.get("responsibilities", []) or []),
    ]
    return " ".join(values).lower()


def detect_role_profile(parsed_jd):
    blob = _text_blob(parsed_jd)
    title = (parsed_jd.get("role_title") or parsed_jd.get("title") or "").lower()
    best_name, best_score = "", 0
    for name, profile in ROLE_PROFILES.items():
        score = sum(1 for signal in profile.get("signals", []) if signal.lower() in blob)
        score += sum(2 for signal in profile.get("signals", []) if signal.lower() in title)
        if name.lower() in blob:
            score += 2
        if score > best_score:
            best_name, best_score = name, score
    if not best_name:
        return {}
    profile = ROLE_PROFILES[best_name]
    return {
        "name": best_name,
        "confidence": min(0.95, 0.55 + best_score * 0.12),
        "buckets": profile.get("buckets", {}),
        "nice_buckets": profile.get("nice_buckets", {}),
    }


def bucket_matches(profile, candidate_skills):
    candidate_set = {canonical_skill(s).lower() for s in candidate_skills or [] if canonical_skill(s)}
    buckets = profile.get("buckets") or {}
    results = []
    for bucket, skills in buckets.items():
        canonical_options = [canonical_skill(s) for s in skills]
        matched = [s for s in canonical_options if s.lower() in candidate_set]
        results.append({
            "bucket": bucket,
            "options": canonical_options,
            "matched": unique_list(matched),
            "passed": bool(matched),
        })
    return results
