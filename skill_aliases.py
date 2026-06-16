import re


SKILL_ALIASES = {
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "ai": "Artificial Intelligence",
    "artificial intelligence": "Artificial Intelligence",
    "pyspark": "Apache Spark",
    "spark": "Apache Spark",
    "apache spark": "Apache Spark",
    "js": "JavaScript",
    "javascript": "JavaScript",
    "node": "Node.js",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "typescript": "TypeScript",
    "type script": "TypeScript",
    "react": "React",
    "react.js": "React",
    "angular": "Angular",
    "vue": "Vue.js",
    "python": "Python",
    "powershell": "PowerShell",
    "java": "Java",
    "spring boot": "Spring Boot",
    "spring": "Spring",
    "sql": "SQL",
    ".net": ".NET",
    "dotnet": ".NET",
    "asp.net": "ASP.NET",
    "c#": "C#",
    "c sharp": "C#",
    ".net core": ".NET Core",
    "dotnet core": ".NET Core",
    "software architecture": "Software Architecture",
    "solution architecture": "Solution Architecture",
    "system architecture": "System Architecture",
    "systems architecture": "System Architecture",
    "architecture ownership": "Architecture Ownership",
    "architectural roadmap": "Architecture Roadmap",
    "architecture reviews": "Architecture Reviews",
    "architecture review": "Architecture Reviews",
    "technical leadership": "Technical Leadership",
    "engineering leadership": "Engineering Leadership",
    "distributed systems": "Distributed Systems",
    "distributed platforms": "Distributed Platforms",
    "large-scale systems": "Large-scale Systems",
    "large scale systems": "Large-scale Systems",
    "control plane": "Control Plane",
    "control-plane": "Control Plane",
    "policy engine": "Policy Engine",
    "policy engines": "Policy Engine",
    "configuration management": "Configuration Management",
    "api design": "API Design",
    "api ecosystem": "API Ecosystem",
    "api ecosystems": "API Ecosystem",
    "grpc": "gRPC",
    "g rpc": "gRPC",
    "security architecture": "Security Architecture",
    "secure-by-design": "Secure-by-Design",
    "secure by design": "Secure-by-Design",
    "fault tolerance": "Fault Tolerance",
    "fault tolerant": "Fault Tolerance",
    "resilience": "Resilience",
    "operational excellence": "Operational Excellence",
    "performance engineering": "Performance Engineering",
    "service decomposition": "Service Decomposition",
    "domain modeling": "Domain Modeling",
    "domain modelling": "Domain Modeling",
    "edr": "EDR",
    "xdr": "XDR",
    "soar": "SOAR",
    "tool development": "Tool Development",
    "internal tools": "Internal Tools",
    "automation": "Automation",
    "build automation": "Build Automation",
    "release automation": "Release Automation",
    "deployment process": "Deployment Automation",
    "deployment processes": "Deployment Automation",
    "black duck": "Black Duck",
    "coverity": "Coverity",
    "sonarqube": "SonarQube",
    "code scan": "Code Scanning",
    "software composition": "Software Composition Analysis",
    "kafka": "Kafka",
    "apache kafka": "Kafka",
    "mysql": "MySQL",
    "postgresql": "PostgreSQL",
    "mongodb": "MongoDB",
    "aws": "AWS",
    "amazon web services": "AWS",
    "ec2": "AWS EC2",
    "aws ec2": "AWS EC2",
    "s3": "AWS S3",
    "aws s3": "AWS S3",
    "rds": "AWS RDS",
    "aws rds": "AWS RDS",
    "cloudwatch": "AWS CloudWatch",
    "aws cloudwatch": "AWS CloudWatch",
    "azure": "Microsoft Azure",
    "gcp": "Google Cloud Platform",
    "google cloud": "Google Cloud Platform",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "cloud infrastructure": "Cloud Infrastructure",
    "infrastructure platform": "Cloud Infrastructure",
    "multi-cloud": "Multi-cloud Infrastructure",
    "multicloud": "Multi-cloud Infrastructure",
    "cloud platform": "Cloud Platform",
    "cloud-native": "Cloud Platform",
    "cloud native": "Cloud Platform",
    "cloud services": "Cloud Platform",
    "platform scalability": "Platform Scalability",
    "scalability": "Platform Scalability",
    "deployment automation": "Deployment Automation",
    "cloud security": "Cloud Security",
    "terraform": "Terraform",
    "jenkins": "Jenkins",
    "git": "Git",
    "jira": "Jira",
    "technical product management": "Technical Product Management",
    "product management": "Product Management",
    "platform product management": "Platform Product Management",
    "roadmap management": "Roadmap Management",
    "product roadmap": "Roadmap Management",
    "roadmap ownership": "Roadmap Management",
    "backlog prioritization": "Backlog Prioritization",
    "backlog management": "Backlog Prioritization",
    "engineering collaboration": "Engineering Collaboration",
    "cross-functional engineering collaboration": "Engineering Collaboration",
    "cross functional engineering collaboration": "Engineering Collaboration",
    "cross-functional leadership": "Cross-functional Leadership",
    "cross functional leadership": "Cross-functional Leadership",
    "stakeholder management": "Stakeholder Management",
    "enterprise stakeholder management": "Stakeholder Management",
    "customer-facing product management": "Customer-facing Product Management",
    "customer facing product management": "Customer-facing Product Management",
    "customer-facing product leadership": "Customer-facing Product Management",
    "customer requirement translation": "Customer Requirement Translation",
    "requirements translation": "Customer Requirement Translation",
    "poc": "POC",
    "pocs": "POC",
    "proof of concept": "POC",
    "proofs of concept": "POC",
    "technical gtm": "Technical GTM",
    "gtm enablement": "Technical GTM",
    "enterprise saas": "Enterprise SaaS",
    "selenium": "Selenium",
    "cypress": "Cypress",
    "playwright": "Playwright",
    "rest api": "REST API",
    "rest apis": "REST API",
    "api": "API",
    "apis": "API",
    "restful": "REST API",
    "graphql": "GraphQL",
    "microservices": "Microservices",
    "linux": "Linux",
    "active directory": "Active Directory",
    "azure ad": "Azure Active Directory",
    "entra id": "Microsoft Entra ID",
    "iam": "Identity and Access Management",
    "identity access management": "Identity and Access Management",
    "identity and access management": "Identity and Access Management",
    "windows server": "Windows Server",
    "scom": "System Center Operations Manager",
    "system center operations manager": "System Center Operations Manager",
    "pki": "PKI",
    "certificate management": "Certificate Management",
    "observability": "Observability Tooling",
    "observability tooling": "Observability Tooling",
    "monitoring": "Observability Tooling",
    "telemetry": "Observability Tooling",
    "prometheus": "Prometheus",
    "grafana": "Grafana",
    "opentelemetry": "OpenTelemetry",
    "open telemetry": "OpenTelemetry",
    "hci": "Hyperconverged Infrastructure",
    "hyperconverged infrastructure": "Hyperconverged Infrastructure",
    "hybrid hci": "Hyperconverged Infrastructure",
    "unix": "Unix",
    "tool room": "Tool Room",
    "tool-room": "Tool Room",
    "toolroom": "Tool Room",
    "tool manufacturing": "Tool Manufacturing",
    "tool maintenance": "Tool Maintenance",
    "tool design": "Tool Design",
    "tool maker": "Tool Maker",
    "tool making": "Tool Making",
    "wire edm": "Wire EDM",
    "wire cut edm": "Wire EDM",
    "die sinker edm": "Die Sinker EDM",
    "edm machine": "EDM Machine",
    "edm": "EDM",
    "vmc": "VMC",
    "hmc": "HMC",
    "lathe": "Lathe Machine",
    "milling": "Milling",
    "grinding": "Grinding",
    "drilling": "Drilling",
    "surface grinding": "Surface Grinding",
    "press tool": "Press Tool",
    "injection mould": "Injection Mould",
    "injection mold": "Injection Mould",
    "mould maintenance": "Mould Maintenance",
    "mold maintenance": "Mould Maintenance",
    "jig": "Jig / Fixture",
    "fixture": "Jig / Fixture",
    "jigs and fixtures": "Jig / Fixture",
    "jigs & fixtures": "Jig / Fixture",
    "gdt": "GD&T",
    "gd&t": "GD&T",
    "tpm": "TPM",
    "machine setting": "Machine Setting",
    "machine programming": "Machine Programming",
    "embedded c": "Embedded C",
    "embedded software": "Embedded Software",
    "embedded systems": "Embedded Systems",
    "autosar": "AUTOSAR",
    "autosar classic": "AUTOSAR Classic",
    "qnx": "QNX",
    "rtos": "RTOS",
    "can": "CAN",
    "spi": "SPI",
    "i2c": "I2C",
    "uart": "UART",
    "pcie": "PCIe",
    "bootloader": "Bootloader",
    "bootloaders": "Bootloader",
    "misra c": "MISRA C",
    "iso 26262": "ISO 26262",
    "aspice": "ASPICE",
    "nxp s32k": "NXP S32K",
    "s32k": "NXP S32K",
    "s32g": "NXP S32G",
    "s32g2": "NXP S32G",
    "tableau": "Tableau",
    "power bi": "Power BI",
    "excel": "Microsoft Excel",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "scikit-learn": "Scikit-learn",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "snowflake": "Snowflake",
    "databricks": "Databricks",
    "airflow": "Apache Airflow",
    "apache airflow": "Apache Airflow",
    "etl": "ETL",
    "ci/cd": "CI/CD",
    "devops": "DevOps",
    "html": "HTML",
    "css": "CSS",
    "ms office": "Microsoft Office",
    "microsoft office": "Microsoft Office",
    "word": "Microsoft Word",
    "ms word": "Microsoft Word",
    "powerpoint": "Microsoft PowerPoint",
    "ms powerpoint": "Microsoft PowerPoint",
    "sap": "SAP",
    "erp": "ERP",
    "tally": "Tally",
    "gst": "GST",
    "tds": "TDS",
    "payroll": "Payroll",
    "statutory compliance": "Statutory Compliance",
    "labour law": "Labour Law",
    "labor law": "Labour Law",
    "recruitment": "Recruitment",
    "talent acquisition": "Talent Acquisition",
    "sourcing": "Candidate Sourcing",
    "candidate sourcing": "Candidate Sourcing",
    "screening": "Candidate Screening",
    "onboarding": "Onboarding",
    "employee relations": "Employee Relations",
    "sales": "Sales",
    "business development": "Business Development",
    "bd": "Business Development",
    "lead generation": "Lead Generation",
    "cold calling": "Cold Calling",
    "crm": "CRM",
    "channel sales": "Channel Sales",
    "field sales": "Field Sales",
    "key account management": "Key Account Management",
    "territory management": "Territory Management",
    "negotiation": "Negotiation",
    "customer relationship management": "Customer Relationship Management",
    "customer service": "Customer Service",
    "customer support": "Customer Support",
    "production planning": "Production Planning",
    "production": "Production Operations",
    "manufacturing": "Manufacturing Operations",
    "plant operations": "Plant Operations",
    "shop floor": "Shop Floor Operations",
    "shift operations": "Shift Operations",
    "line supervision": "Line Supervision",
    "machine operation": "Machine Operation",
    "cnc": "CNC Operation",
    "cnc programming": "CNC Programming",
    "cnc programmer": "CNC Programming",
    "cnc operation": "CNC Operation",
    "welding": "Welding",
    "fabrication": "Fabrication",
    "assembly": "Assembly Operations",
    "preventive maintenance": "Preventive Maintenance",
    "breakdown maintenance": "Breakdown Maintenance",
    "maintenance": "Maintenance",
    "electrical maintenance": "Electrical Maintenance",
    "mechanical maintenance": "Mechanical Maintenance",
    "utilities": "Utilities",
    "boiler": "Boiler Operations",
    "compressor": "Compressor Operations",
    "quality control": "Quality Control",
    "quality assurance": "Quality Assurance",
    "inspection": "Inspection",
    "root cause analysis": "Root Cause Analysis",
    "rca": "Root Cause Analysis",
    "5s": "5S",
    "kaizen": "Kaizen",
    "lean manufacturing": "Lean Manufacturing",
    "six sigma": "Six Sigma",
    "iso": "ISO Standards",
    "iso 9001": "ISO 9001",
    "iso 14001": "ISO 14001",
    "iatf": "IATF 16949",
    "iatf 16949": "IATF 16949",
    "safety": "Workplace Safety",
    "ehs": "EHS",
    "hse": "EHS",
    "ppe": "PPE Compliance",
    "fssai": "FSSAI",
    "food safety": "Food Safety",
    "hygiene": "Hygiene Management",
    "menu planning": "Menu Planning",
    "canteen operations": "Canteen Operations",
    "cafeteria operations": "Canteen Operations",
    "catering": "Catering Operations",
    "vendor management": "Vendor Management",
    "procurement": "Procurement",
    "purchase": "Procurement",
    "inventory": "Inventory Management",
    "warehouse": "Warehouse Operations",
    "stores": "Stores Management",
    "dispatch": "Dispatch Operations",
    "logistics": "Logistics",
    "transport": "Transport Coordination",
    "facility management": "Facility Management",
    "facilities": "Facility Management",
    "administration": "Administration",
    "housekeeping": "Housekeeping Management",
    "security management": "Security Management",
    "training": "Training",
    "team handling": "Team Management",
    "team management": "Team Management",
    "people management": "People Management",
    "supervision": "Supervision",
    "reporting": "Reporting",
    "mis": "MIS Reporting",
    "data entry": "Data Entry",
}

SPECIALIZED_TOOL_WEIGHT_CAPS = {
    "Observability Tooling": 65,
    "Prometheus": 55,
    "Grafana": 55,
    "OpenTelemetry": 55,
    "Hyperconverged Infrastructure": 60,
}


def canonical_skill(raw_value):
    value = re.sub(r"\s+", " ", str(raw_value or "").strip(" ,.;:|/\\")).lower()
    if not value:
        return ""
    if value in {"net core"}:
        return ".NET Core"
    if value in {"net"}:
        return ".NET"
    if re.fullmatch(r"(?:rest\s+)?apis?", value):
        return "REST API"
    return SKILL_ALIASES.get(value, value.title())


def skill_aliases_for(canonical):
    canonical_l = canonical_skill(canonical).lower()
    aliases = [raw for raw, value in SKILL_ALIASES.items() if value.lower() == canonical_l]
    return sorted(set(aliases + [canonical_l]))


def unique_list(items, limit=None):
    seen, output = set(), []
    for item in items or []:
        value = str(item or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output[:limit] if limit else output


def extract_skills(text):
    text_l = (text or "").lower()
    found = []
    it_context = bool(re.search(r"\b(pyspark|hadoop|scala|dataframe|big data|etl|data engineer|data pipeline|databricks|snowflake|python|sql)\b", text_l))
    manufacturing_context = bool(re.search(r"\b(cnc|edm|vmc|hmc|tool\s*room|tool-room|machine|mould|mold|fixture|press tool|maintenance|manufacturing|shop floor)\b", text_l))
    hr_context = bool(re.search(r"\b(recruitment|recruiter|hr|talent acquisition|screening candidates?|sourcing)\b", text_l))
    for raw, canonical in sorted(SKILL_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if raw == "can":
            continue
        if raw == "screening" and not hr_context:
            continue
        if raw in {"production", "production planning"} and not manufacturing_context:
            continue
        if raw == "inventory" and not re.search(r"\b(procurement|warehouse|stores|stock|supply chain|materials|manufacturing|production planning|inventory management)\b", text_l):
            continue
        if raw == "spark" and not it_context:
            continue
        if canonical in {"Artificial Intelligence", "Machine Learning"} and manufacturing_context and not it_context:
            continue
        if raw == "monitoring" and not re.search(r"\b(observability|telemetry|prometheus|grafana|opentelemetry|cloud|server|system|infrastructure|application|service)\b", text_l):
            continue
        pattern = r"(?<![a-z0-9])" + re.escape(raw.lower()) + r"(?![a-z0-9])"
        if re.search(pattern, text_l):
            found.append(canonical)
    if re.search(r"(?<![A-Za-z0-9])CAN(?![A-Za-z0-9])", text or ""):
        found.append("CAN")
    noisy_fragments = {
        "identify", "develop", "manage", "support", "ensure", "responsible", "responsibilities",
        "requirement", "requirements", "good", "excellent", "strong", "skills", "skill",
        "knowledge", "ability", "candidate", "profile", "role", "job", "working"
    }
    known_canonical_values = {v.lower() for v in SKILL_ALIASES.values()}
    for marker in ["skills", "skill set", "key skills", "requirements", "must have", "mandatory", "responsibilities"]:
        pattern = marker + r"\s*[:\-]\s*([^\n]{5,260})"
        for match in re.findall(pattern, text_l, re.I):
            for part in re.split(r"[,;/|•]", match):
                value = re.sub(r"^[\W\d_]+", "", re.sub(r"\s+", " ", part)).strip(" .:-")
                words = re.findall(r"[a-z0-9+#.]+", value.lower())
                known_skill = canonical_skill(value).lower() in known_canonical_values
                if (
                    2 <= len(value) <= 45
                    and not re.search(r"\b(years?|yrs?|experience|required|preferred|responsible|candidate|should|must|will|able)\b", value)
                    and not (len(words) == 1 and words[0] in noisy_fragments)
                    and not (len(words) > 4 and not known_skill)
                ):
                    found.append(canonical_skill(value))
    return unique_list(found)


def weighted_skills(text, skills, default_weight=70):
    must_markers = ["must", "required", "mandatory", "hands-on", "strong", "expert"]
    nice_markers = ["preferred", "nice to have", "good to have", "plus", "advantage", "optional"]
    sentences = re.split(r"[\n.;]", text or "")
    output = []
    for skill in skills:
        canonical = canonical_skill(skill)
        confidence = 0.72
        weight = default_weight
        for sentence in sentences:
            sentence_l = sentence.lower()
            if canonical.lower() in [canonical_skill(s).lower() for s in extract_skills(sentence)]:
                if any(marker in sentence_l for marker in must_markers):
                    weight = max(weight, 95)
                    confidence = max(confidence, 0.9)
                if any(marker in sentence_l for marker in nice_markers):
                    weight = min(weight, 45)
                    confidence = max(confidence, 0.82)
        if canonical in SPECIALIZED_TOOL_WEIGHT_CAPS:
            weight = min(weight, SPECIALIZED_TOOL_WEIGHT_CAPS[canonical])
        output.append({
            "skill": canonical,
            "weight": int(max(0, min(100, weight))),
            "aliases": skill_aliases_for(canonical),
            "confidence": round(confidence, 2)
        })
    return output
