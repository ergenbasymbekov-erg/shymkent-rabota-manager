"""Vacancy Completeness Checker — score required fields before manager approval."""

import re
from typing import Literal

from position import has_valid_positions, valid_positions
from schema import CompletenessResult, StructuredData, ValidationResult

POSITION_UNKNOWN_WARNING = "Нақты лауазым көрсетілмеген."
POSTER_BLOCKED_MESSAGE = "Poster generation blocked — manager approval required."

CompletenessStatus = Literal["READY", "REVIEW", "INCOMPLETE"]

FIELD_WEIGHTS = {
    "company": 15,
    "position": 25,
    "phone": 25,
    "address": 15,
    "salary": 10,
    "schedule": 10,
}

FIELD_LABELS = {
    "company": "Company",
    "position": "Position",
    "phone": "Phone",
    "address": "Address",
    "salary": "Salary",
    "schedule": "Work Schedule",
}

SCHEDULE_PATTERNS = [
    r"график",
    r"кесте",
    r"schedule",
    r"жұмыс\s+уақыты",
    r"жұмыс\s+кестесі",
    r"\d{1,2}/\d{1,2}",
    r"смен",
    r"shift",
    r"\d{1,2}:\d{2}",
    r"понедельник",
    r"ежеднев",
    r"толық\s+күн",
    r"полный\s+день",
    r"part.?time",
    r"уикенд",
    r"выходн",
    r"будни",
    r"смена",
]


def _has_text(value: str) -> bool:
    return bool((value or "").strip())


def _has_company(structured: StructuredData) -> bool:
    return _has_text(structured.company)


def _has_position(structured: StructuredData) -> bool:
    if valid_positions(structured.positions):
        return True
    for g in structured.position_groups or []:
        if (g.position or "").strip():
            return True
    return has_valid_positions(structured.vacancy_title, structured.positions)


def _has_phone(structured: StructuredData, validation: ValidationResult) -> bool:
    return bool(structured.phones) and not validation.phone_error


def _has_address(structured: StructuredData) -> bool:
    return _has_text(structured.address) or _has_text(structured.address_notes)


def _has_salary(structured: StructuredData) -> bool:
    return _has_text(structured.salary)


def _has_schedule(structured: StructuredData) -> bool:
    parts = list(structured.conditions or [])
    if structured.notes:
        parts.append(structured.notes)
    blob = "\n".join(parts).lower()
    if not blob.strip():
        return False
    return any(re.search(p, blob, re.I) for p in SCHEDULE_PATTERNS)


def _score_from_fields(present: dict) -> int:
    return sum(FIELD_WEIGHTS[k] for k, ok in present.items() if ok)


def _status_from_score(score: int) -> CompletenessStatus:
    if score >= 90:
        return "READY"
    if score >= 70:
        return "REVIEW"
    return "INCOMPLETE"


def _indicator(status: CompletenessStatus) -> str:
    return {"READY": "🟢", "REVIEW": "🟡", "INCOMPLETE": "🔴"}[status]


def run_completeness_check(
    structured: StructuredData,
    validation: ValidationResult,
) -> CompletenessResult:
    """
    Measure vacancy quality and completeness (max 100 points).
    Runs after AI Review and global validation, before manager approval.
    """
    present = {
        "company": _has_company(structured),
        "position": _has_position(structured),
        "phone": _has_phone(structured, validation),
        "address": _has_address(structured),
        "salary": _has_salary(structured),
        "schedule": _has_schedule(structured),
    }

    missing = [FIELD_LABELS[k] for k, ok in present.items() if not ok]
    field_scores = {FIELD_LABELS[k]: FIELD_WEIGHTS[k] if ok else 0 for k, ok in present.items()}
    score = _score_from_fields(present)
    status = _status_from_score(score)
    warnings = []

    if validation.unknown_position:
        warnings.append(POSITION_UNKNOWN_WARNING)
        warnings.append(POSTER_BLOCKED_MESSAGE)
        status = "REVIEW"
    if validation.phone_error:
        warnings.append("PHONE_ERROR — phone number invalid or incomplete")
        if status == "READY":
            status = "REVIEW"
    if validation.language_error:
        warnings.append("LANGUAGE_ERROR — language mismatch detected")
        if status == "READY":
            status = "REVIEW"

    if score < 70:
        status = "INCOMPLETE"
        warnings.append("Completeness below 70 — poster generation blocked")

    can_poster = (
        score >= 70
        and status != "INCOMPLETE"
        and not validation.phone_error
        and not validation.unknown_position
    )

    return CompletenessResult(
        score=score,
        max_score=100,
        status=status,
        indicator=_indicator(status),
        missing=missing,
        warnings=warnings,
        field_scores=field_scores,
        can_poster=can_poster,
    )
