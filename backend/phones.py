"""Phone normalization, display formatting, and preservation."""

import re
from typing import Optional, Tuple

_DIGITS = re.compile(r"\D")
_PHONE_CHUNK = re.compile(r"\d{10,12}")
_PHONE_SPACED = re.compile(r"\d{3,4}[\s\-]\d{6,8}")


def _digits(value: str) -> str:
    return _DIGITS.sub("", value or "")


def normalize_phone_internal(raw: str) -> Tuple[str, Optional[str]]:
    """
    Normalize to 11-digit internal storage: 87763837171
    Rules: strip spaces/brackets/dashes; +7 → 8 prefix.
    Returns (internal, error_code). internal empty on error.
    """
    if not raw or not str(raw).strip():
        return "", "PHONE_EMPTY"

    digits = _digits(raw)
    if not digits:
        return "", "PHONE_EMPTY"

    if len(digits) < 10:
        return "", "PHONE_TOO_SHORT"

    if len(digits) == 11 and digits.startswith("7"):
        digits = "8" + digits[1:]

    if len(digits) == 11 and digits.startswith("8"):
        return digits, None

    if len(digits) != 11:
        return "", "PHONE_PARTIAL"

    return "", "PHONE_INVALID"


def format_phone_display(internal: str) -> str:
    """Display format: +7 776 383 71 71 from internal 87763837171."""
    digits = _digits(internal)
    if len(digits) != 11 or not digits.startswith("8"):
        return (internal or "").strip()
    rest = digits[1:]
    return f"+7 {rest[0:3]} {rest[3:6]} {rest[6:8]} {rest[8:10]}"


def _extract_from_raw(raw_text: str) -> list:
    if not raw_text:
        return []

    found = []
    seen = set()

    def add(value: str) -> None:
        d = _digits(value)
        if len(d) < 10 or d in seen:
            return
        seen.add(d)
        found.append(value.strip())

    for match in _PHONE_CHUNK.finditer(raw_text):
        add(match.group())
    for match in _PHONE_SPACED.finditer(raw_text):
        add(match.group())

    return found


def _best_form(digit_key: str, forms: list) -> str:
    best = ""
    best_len = 0
    for form in forms:
        d = _digits(form)
        if len(d) < best_len:
            continue
        if len(d) > best_len or (len(d) == best_len and len(form) > len(best)):
            best = form.strip()
            best_len = len(d)
    return best


def _resolve_truncated(candidate: str, canon: dict) -> str:
    cd = _digits(candidate)
    if not cd:
        return candidate
    if cd in canon:
        return canon[cd]
    for full_digits, original in canon.items():
        if full_digits.endswith(cd) and len(full_digits) > len(cd):
            return original
        if cd.endswith(full_digits) and len(cd) > len(full_digits):
            return candidate
    return candidate


def preserve_phones(editor_phones=None, parsed_phones=None, raw_text: str = "") -> list:
    """Merge phones from raw/parsed/editor; prefer full numbers over truncated."""
    editor_phones = editor_phones or []
    parsed_phones = parsed_phones or []

    forms_by_digits = {}
    for source in (_extract_from_raw(raw_text), parsed_phones, editor_phones):
        for phone in source:
            phone = (phone or "").strip()
            if not phone:
                continue
            d = _digits(phone)
            if len(d) < 7:
                continue
            forms_by_digits.setdefault(d, []).append(phone)

    canon = {d: _best_form(d, forms) for d, forms in forms_by_digits.items()}

    ordered = []
    seen = set()

    def add_phone(phone: str) -> None:
        phone = (phone or "").strip()
        if not phone:
            return
        resolved = _resolve_truncated(phone, canon)
        key = _digits(resolved)
        if not key or key in seen:
            return
        seen.add(key)
        ordered.append(resolved)

    for phone in parsed_phones:
        add_phone(phone)
    for phone in editor_phones:
        add_phone(phone)
    for phone in _extract_from_raw(raw_text):
        add_phone(phone)

    return ordered


def process_phones(editor_phones=None, parsed_phones=None, raw_text: str = "") -> Tuple[list, list, bool, list]:
    """
    Preserve → normalize → format.
    Returns (internal_phones, display_phones, phone_error, error_messages).
    """
    preserved = preserve_phones(editor_phones, parsed_phones, raw_text)
    internals = []
    displays = []
    errors = []
    seen = set()

    for raw in preserved:
        internal, err = normalize_phone_internal(raw)
        if err:
            errors.append(f"PHONE_ERROR: {raw!r} — {err}")
            continue
        if internal in seen:
            continue
        seen.add(internal)
        internals.append(internal)
        displays.append(format_phone_display(internal))

    raw_has_phone = bool(_extract_from_raw(raw_text)) or any(
        len(_digits(p)) >= 10 for p in (parsed_phones or [])
    )
    phone_error = False
    if raw_has_phone and not internals:
        phone_error = True
        if not errors:
            errors.append("PHONE_ERROR: phone found in raw text but could not be normalized")
    elif errors and not internals:
        phone_error = True

    return internals, displays, phone_error, errors
