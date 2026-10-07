"""Normalization of CTE commercial validity dates."""


def normalize_cte_validity(data: dict) -> dict:
    """Keep an explicit start date only; treat a legacy generic date as expiry."""
    normalized = dict(data)
    legacy_validity = normalized.pop("validita", None)
    normalized["valid_from"] = normalized.get("valid_from") or None
    normalized["valid_until"] = normalized.get("valid_until") or legacy_validity or None
    return normalized
