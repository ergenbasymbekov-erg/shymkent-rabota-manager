"""Global vacancy validation — runs before approval, poster, Telegram, WhatsApp."""

import re
from typing import Optional

from language import (
    DominantLanguage,
    EMOJI_RE,
    detect_dominant_language,
    validate_neutral_style,
    validate_output_language,
)
from phones import _digits, _extract_from_raw, normalize_phone_internal
from policy import unknown_position_flag, vacancy_title_present
from position import (
    INVALID_UNKNOWN_POSITION,
    POSITION_UNKNOWN_WARNING,
    POSTER_BLOCKED_MESSAGE,
    is_unknown_position,
    valid_positions,
)
from schema import StructuredData, ValidationResult

DISCRIMINATION_PATTERNS = [
    (r"тек\s+қыз", "gender restriction"),
    (r"тек\s+ер\b", "gender restriction"),
    (r"тек\s+әйел", "gender restriction"),
    (r"только\s+девуш", "gender restriction"),
    (r"только\s+мужчин", "gender restriction"),
    (r"только\s+женщин", "gender restriction"),
    (r"тек\s+жігіт", "gender restriction"),
    (r"\b18\s*[-–]\s*25\b", "age restriction"),
    (r"от\s+18\s+до\s*25", "age restriction"),
    (r"18\s*[-–]\s*30\s*жас", "age restriction"),
    (r"до\s+30\s+лет", "age restriction"),
    (r"национал", "nationality restriction"),
    (r"этнич", "ethnicity restriction"),
    (r"религ", "religion restriction"),
    (r"мусульман", "religion restriction"),
    (r"христиан", "religion restriction"),
]

SALARY_HINTS = re.compile(
    r"(жалақы|зарплат|оплат|тг\b|тенге|₸|salary|\d+\s*000)",
    re.I,
)
ADDRESS_HINTS = re.compile(
    r"(ул\.|к\.|көше|мкр|микрорайон|ориентир|базар|адрес|мекенжай|пр\.|просп)",
    re.I,
)
INSTAGRAM_HINTS = re.compile(r"(instagram|инстаграм|@\w+)", re.I)


def _collect_text(raw_text: str, after: str, structured: StructuredData) -> str:
    parts = [raw_text, after]
    d = structured.model_dump()
    for val in d.values():
        if isinstance(val, list):
            parts.extend(str(x) for x in val)
        elif isinstance(val, str) and val:
            parts.append(val)
    return "\n".join(parts).lower()


def detect_discrimination(text: str) -> list:
    """Return list of discrimination issue descriptions found in text."""
    found = []
    lower = text.lower()
    for pattern, label in DISCRIMINATION_PATTERNS:
        if re.search(pattern, lower, re.I):
            found.append(f"Discrimination: {label}")
    return found


def check_data_loss(raw_text: str, structured: StructuredData, parsed_phones: list) -> list:
    """Heuristic checks: info in raw must exist in structured JSON."""
    missing = []
    s = structured

    raw_phones = _extract_from_raw(raw_text)
    if raw_phones and not s.phones:
        missing.append("Phones in raw text but missing in structured data")

    for raw_phone in raw_phones:
        raw_d = _digits(raw_phone)
        if not any(_digits(p) == raw_d or _digits(p).endswith(raw_d) for p in s.phones):
            internal, err = normalize_phone_internal(raw_phone)
            if not err and internal not in s.phones:
                missing.append(f"Phone {raw_phone!r} from raw text not in structured data")

    if SALARY_HINTS.search(raw_text) and not (s.salary or "").strip():
        missing.append("Salary mentioned in raw text but missing in structured data")

    if ADDRESS_HINTS.search(raw_text) and not (s.address or "").strip() and not (s.address_notes or "").strip():
        missing.append("Address mentioned in raw text but missing in structured data")

    if INSTAGRAM_HINTS.search(raw_text) and not (s.instagram or "").strip():
        missing.append("Instagram mentioned in raw text but missing in structured data")

    if parsed_phones and not s.phones:
        missing.append("Parser extracted phones but structured data has none")

    return missing


def validate_phones_list(phones: list) -> tuple[bool, list]:
    """Validate stored internal phones. Returns (phone_error, messages)."""
    if not phones:
        return False, []

    errors = []
    for phone in phones:
        internal, err = normalize_phone_internal(phone)
        if err:
            errors.append(f"PHONE_ERROR: {phone!r} — {err}")
        elif internal != _digits(phone):
            errors.append(f"PHONE_ERROR: {phone!r} — must be stored as 11-digit internal format")

    return bool(errors), errors


def run_global_validation(
    raw_text: str,
    after: str,
    structured: StructuredData,
    parsed_phones: Optional[list] = None,
    phone_error: bool = False,
    phone_messages: Optional[list] = None,
    dominant: Optional[DominantLanguage] = None,
) -> ValidationResult:
    """
    Apply all global validation rules before approval.
    Blocks poster generation when critical flags are set.
    """
    dominant = dominant or detect_dominant_language(raw_text)
    fields_dict = structured.model_dump()
    errors = list(phone_messages or [])
    warnings = []

    # Phone validation
    pe = phone_error
    if not pe:
        pe, phone_errs = validate_phones_list(structured.phones)
        errors.extend(phone_errs)

    # Language preservation
    lang_ok, lang_err = validate_output_language(dominant, after, fields_dict)
    language_error = not lang_ok
    if language_error:
        errors.append(lang_err)

    # Editorial — emojis / first-person (deterministic)
    style_ok, style_err = validate_neutral_style(after, fields_dict)
    if not style_ok:
        warnings.append(style_err)

    blob = _collect_text(raw_text, after, structured)
    if EMOJI_RE.search(blob):
        warnings.append("Emojis or decorative symbols detected — remove before publish")

    # Position quality — UNKNOWN only when positions.length == 0
    roles = valid_positions(structured.positions)
    if not roles:
        roles = [
            p.strip() for p in (structured.positions or [])
            if (p or "").strip() and not is_unknown_position(p.strip())
        ]
    if not roles and structured.position_groups:
        roles = valid_positions([
            (g.position or "").strip()
            for g in structured.position_groups
            if (g.position or "").strip()
        ])
    unknown_position = len(roles) == 0

    invalid_unknown = len(roles) > 0 and is_unknown_position(structured.vacancy_title)
    if invalid_unknown:
        errors.append(
            f"{INVALID_UNKNOWN_POSITION} — {len(roles)} position(s) exist but "
            "vacancy_title is UNKNOWN_POSITION (forbidden)"
        )
        warnings.append(
            f"{INVALID_UNKNOWN_POSITION} — vacancy_title must be corrected when positions exist"
        )

    if unknown_position:
        warnings.append(POSITION_UNKNOWN_WARNING)
        warnings.append(POSTER_BLOCKED_MESSAGE)
        errors.append(POSITION_UNKNOWN_WARNING)

    # Discrimination
    disc_issues = detect_discrimination(blob)
    discrimination_flag = bool(disc_issues)
    warnings.extend(disc_issues)

    # Data loss protection
    data_loss = check_data_loss(raw_text, structured, parsed_phones or [])
    critical_data_missing = bool(data_loss)
    warnings.extend(data_loss)

    # Recruiter uncertainty — manager must review before publish
    recruiter_flags = [
        u for u in (structured.unsorted_review or [])
        if (u or "").strip().startswith("RECRUITER:")
    ]
    if recruiter_flags:
        warnings.extend(recruiter_flags)

    review_required = (
        pe
        or unknown_position
        or invalid_unknown
        or language_error
        or critical_data_missing
        or discrimination_flag
        or bool(recruiter_flags)
    )

    can_approve = not review_required

    return ValidationResult(
        phone_error=pe,
        unknown_position=unknown_position,
        language_error=language_error,
        critical_data_missing=critical_data_missing,
        discrimination_flag=discrimination_flag,
        review_required=review_required,
        can_approve=can_approve,
        errors=errors,
        warnings=warnings,
    )


def validation_from_structured(structured: StructuredData) -> ValidationResult:
    """Lightweight validation for poster generation from structured JSON only."""
    pe, phone_errs = validate_phones_list(structured.phones)
    unknown_position = unknown_position_flag(structured.positions, structured.position_groups)
    invalid = (
        not unknown_position
        and is_unknown_position(structured.vacancy_title)
    )
    return ValidationResult(
        phone_error=pe,
        unknown_position=unknown_position,
        can_approve=not pe and not unknown_position and not invalid,
        errors=phone_errs,
    )
