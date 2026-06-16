import re

from taxonomy_core import infer_role_family, infer_seniority_family, ROLE_FAMILIES


ROLE_TAXONOMY = {name: data.get("signals", []) for name, data in ROLE_FAMILIES.items()}


def infer_role_taxonomy(text):
    ranked = infer_role_family(text)
    return [
        {
            "role": item["family"],
            "confidence": item["confidence"],
            "matched_signals": item["matched_signals"],
        }
        for item in ranked
    ]


def primary_role_category(text):
    ranked = infer_role_taxonomy(text)
    return ranked[0]["role"] if ranked else ""


def normalize_role_title(title):
    value = re.sub(r"\s+", " ", str(title or "")).strip()
    if not value:
        return ""
    category = primary_role_category(value)
    return category or value.title()


def infer_seniority(text, years=0):
    return infer_seniority_family(text, years)
