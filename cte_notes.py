"""Formatting for informative CTE contractual details stored in ``cte_offers.notes``."""


def _clean(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def format_cte_notes(fatturazione: object, recesso_anticipato: object,
                     altre_note: object = None, vincoli_legacy: object = None) -> str:
    """Build the stable, line-oriented notes format without inferring missing facts."""
    lines = [
        f"Fatturazione: {_clean(fatturazione, 'Non indicata')}",
        f"Recesso anticipato: {_clean(recesso_anticipato, 'Non indicato')}",
    ]
    extras: list[str] = []
    for value in (altre_note, vincoli_legacy):
        text = str(value or "").strip()
        if text and text not in extras:
            extras.append(text)
    if extras:
        lines.append(f"Altre note: {'; '.join(extras)}")
    return "\n".join(lines)
