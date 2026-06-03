"""Recruiter confidence gate — auto-fill only when LLM confidence >= threshold."""

from __future__ import annotations

CONFIDENCE_THRESHOLD = 0.85

SCALAR_FIELDS = (
    "company", "vacancy", "salary", "address", "address_notes",
    "instagram", "notes",
    "requirements_heading", "responsibilities_heading", "conditions_heading",
)

LIST_FIELDS = ("vacancies", "requirements", "responsibilities", "conditions", "phones")


def _parse_confidence(raw: object) -> float:
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def _field_payload(data: dict, key: str) -> tuple[object, float]:
    """Read {value, confidence} object or plain value from LLM output."""
    raw = data.get(key)
    if isinstance(raw, dict) and "value" in raw:
        return raw.get("value"), _parse_confidence(raw.get("confidence"))
    if isinstance(raw, dict) and "confidence" in raw and len(raw) == 1:
        return None, _parse_confidence(raw.get("confidence"))
    return raw, 1.0 if raw not in (None, "", []) else 0.0


def _as_str(value: object) -> str:
    return "" if value is None else str(value).strip()


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_as_str(item) for item in value if _as_str(item)]


def _review_entry(field: str, value: str, confidence: float) -> str:
    pct = int(round(confidence * 100))
    return f"[{field} · {pct}% confidence] {value}"


def apply_confidence_gate(data: dict) -> tuple[dict, dict[str, float], list[str]]:
    """
    Apply confidence threshold to LLM recruiter output.
    Fields with confidence < 0.85 are NOT auto-filled — sent to unsorted_review.
    Returns (fields, confidence_map, low_confidence_unsorted).
    """
    fields: dict[str, object] = {}
    confidence_map: dict[str, float] = {}
    low_conf_unsorted: list[str] = []

    for key in SCALAR_FIELDS:
        value, conf = _field_payload(data, key)
        text = _as_str(value)
        confidence_map[key] = conf
        if text and conf < CONFIDENCE_THRESHOLD:
            low_conf_unsorted.append(_review_entry(key, text, conf))
            fields[key] = ""
        else:
            fields[key] = text

    for key in LIST_FIELDS:
        value, conf = _field_payload(data, key)
        items = _as_str_list(value)
        confidence_map[key] = conf
        if items and conf < CONFIDENCE_THRESHOLD:
            for item in items:
                low_conf_unsorted.append(_review_entry(key, item, conf))
            fields[key] = []
        else:
            fields[key] = items

    lang_value, lang_conf = _field_payload(data, "language")
    language = _as_str(lang_value).upper()
    confidence_map["language"] = lang_conf
    if language and lang_conf >= CONFIDENCE_THRESHOLD:
        fields["language"] = language
    else:
        if language and lang_conf < CONFIDENCE_THRESHOLD:
            low_conf_unsorted.append(_review_entry("language", language, lang_conf))
        fields["language"] = language if language else "MIXED"

    mode_value, mode_conf = _field_payload(data, "mode")
    mode = _as_str(mode_value).upper()
    confidence_map["mode"] = mode_conf
    if mode in ("SINGLE", "MULTI") and mode_conf >= CONFIDENCE_THRESHOLD:
        fields["mode"] = mode
    else:
        vacancies = fields.get("vacancies") or []
        if mode and mode_conf < CONFIDENCE_THRESHOLD:
            low_conf_unsorted.append(_review_entry("mode", mode, mode_conf))
        fields["mode"] = mode if mode in ("SINGLE", "MULTI") else (
            "MULTI" if len(vacancies) >= 2 else "SINGLE"
        )

    return fields, confidence_map, low_conf_unsorted
