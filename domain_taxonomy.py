from taxonomy_core import DOMAIN_FAMILIES, infer_domain_family


DOMAIN_TAXONOMY = DOMAIN_FAMILIES


def infer_domain_taxonomy(text):
    ranked = infer_domain_family(text)
    return [
        {
            "domain": item["domain"],
            "confidence": item["confidence"],
            "matched_signals": item["matched_signals"],
        }
        for item in ranked
    ]


def primary_domain(text):
    ranked = infer_domain_taxonomy(text)
    return ranked[0]["domain"] if ranked else ""

