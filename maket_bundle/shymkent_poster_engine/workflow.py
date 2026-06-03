"""AI recruiter workflow — LLM parse → review → approve → layout engine (approved JSON only)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from .language import Language, section_labels
from .parser import PosterMode, VacancyData
from .semantic_parser import parse_vacancy_semantic


PLACEHOLDERS = frozenset({
    "undefined", "null", "none", "n/a", "na", "—", "-", "...", "placeholder",
    "test", "xxx", "todo", "tbd", "empty",
})


@dataclass
class ParseResult:
    language: Language
    data: VacancyData
    preview: dict[str, object]


@dataclass
class FieldValidation:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_placeholder(value: str) -> bool:
    return value.strip().lower() in PLACEHOLDERS


def _has_vacancy(data: VacancyData) -> bool:
    if data.mode == PosterMode.MULTI:
        return len(data.positions) > 0
    return bool(data.vacancy_title.strip())


def semantic_parse(raw_text: str) -> ParseResult:
    """AI recruiter (LLM) → structured JSON. Raw text never reaches layout engine."""
    preview = parse_vacancy_semantic(raw_text)
    data = vacancy_from_preview(preview)
    return ParseResult(
        language=data.language or Language.MIXED,
        data=data,
        preview=preview,
    )


def _combine_address(preview: dict) -> str:
    """Merge address + address_notes for poster rendering."""
    address = str(preview.get("address", "")).strip()
    notes = str(preview.get("address_notes", "")).strip()
    if address and notes:
        return f"{address}\n{notes}"
    return address or notes


def _resolve_phone(preview: dict) -> str:
    phones = preview.get("phones")
    if isinstance(phones, list):
        for p in phones:
            text = str(p).strip()
            if text:
                return text
    return str(preview.get("phone", "")).strip()


def vacancy_to_preview(data: VacancyData) -> dict[str, object]:
    preview: dict[str, object] = {
        "language": data.language.value if data.language else Language.MIXED.value,
        "mode": data.mode.value,
        "company": data.company,
        "salary": data.salary,
        "requirements_heading": data.requirements_heading,
        "requirements": list(data.requirements),
        "responsibilities_heading": data.responsibilities_heading,
        "responsibilities": list(data.responsibilities),
        "conditions_heading": data.conditions_heading,
        "conditions": list(data.conditions),
        "phones": [data.phone] if data.phone else [],
        "phone": data.phone,
        "address": data.address,
        "address_notes": "",
        "instagram": data.instagram,
        "notes": "",
        "unsorted_review": [],
        "line_map": [],
    }
    if data.mode == PosterMode.MULTI:
        preview["vacancy"] = data.multi_title
        preview["vacancies"] = list(data.positions)
    else:
        preview["vacancy"] = data.vacancy_title
        preview["vacancies"] = []
    return preview


def vacancy_from_preview(preview: dict) -> VacancyData:
    """Rebuild VacancyData from manager-approved JSON."""
    mode_str = str(preview.get("mode", "SINGLE")).upper()
    mode = PosterMode.MULTI if mode_str == "MULTI" else PosterMode.SINGLE

    try:
        language = Language(str(preview.get("language", "MIXED")).upper())
    except ValueError:
        language = Language.MIXED

    vacancies = [
        str(v).strip()
        for v in (preview.get("vacancies") or preview.get("positions") or [])
        if str(v).strip()
    ]
    requirements = [str(r).strip() for r in preview.get("requirements", []) if str(r).strip()]
    responsibilities = [str(r).strip() for r in preview.get("responsibilities", []) if str(r).strip()]
    conditions = [str(c).strip() for c in preview.get("conditions", []) if str(c).strip()]

    vacancy_field = str(preview.get("vacancy", "")).strip()
    labels = section_labels(language)

    data = VacancyData(
        mode=mode,
        language=language,
        company=str(preview.get("company", "")).strip(),
        vacancy_title="" if mode == PosterMode.MULTI else vacancy_field,
        positions=vacancies if mode == PosterMode.MULTI else [],
        salary=str(preview.get("salary", "")).strip(),
        requirements=requirements,
        responsibilities=responsibilities,
        conditions=conditions,
        phone=_resolve_phone(preview),
        address=_combine_address(preview),
        instagram=str(preview.get("instagram", "")).strip(),
        requirements_heading=str(preview.get("requirements_heading", "")).strip() or labels["requirements"],
        responsibilities_heading=str(preview.get("responsibilities_heading", "")).strip() or labels["responsibilities"],
        conditions_heading=str(preview.get("conditions_heading", "")).strip() or labels["conditions"],
        multi_title=vacancy_field if mode == PosterMode.MULTI else "",
    )

    if mode == PosterMode.MULTI and not data.multi_title:
        data.multi_title = labels["multi_title"]

    return data


def validate_preview(preview: dict) -> FieldValidation:
    """Validate manager preview including unsorted_review gate."""
    data = vacancy_from_preview(preview)
    result = validate_vacancy(data)

    unsorted = [
        str(item).strip()
        for item in preview.get("unsorted_review", [])
        if str(item).strip()
    ]
    if unsorted:
        result.errors.append(
            f"Unclassified lines remain ({len(unsorted)}). "
            "Move each item from Unsorted Review into the correct field, then validate again."
        )
        for i, line in enumerate(unsorted, 1):
            result.errors.append(f"  unsorted {i}: {line}")

    result.valid = len(result.errors) == 0
    return result


def validate_vacancy(data: VacancyData) -> FieldValidation:
    result = FieldValidation(valid=True)

    if not data.company.strip():
        result.errors.append("Company is required")
    elif _is_placeholder(data.company):
        result.errors.append("Company must not be a placeholder")

    if not _has_vacancy(data):
        result.errors.append("Vacancy is required")

    if not data.phone.strip():
        result.errors.append("Phone is required")
    else:
        if len(re.sub(r"\D", "", data.phone)) < 10:
            result.errors.append("Phone must contain at least 10 digits")
        if _is_placeholder(data.phone):
            result.errors.append("Phone must not be a placeholder")

    for label, items in (
        ("Requirements", data.requirements),
        ("Responsibilities", data.responsibilities),
        ("Conditions", data.conditions),
    ):
        for i, item in enumerate(items):
            if _is_placeholder(item):
                result.errors.append(f"{label} item {i + 1} is a placeholder")

    if data.salary.strip() and _is_placeholder(data.salary):
        result.errors.append("Salary must not be a placeholder")

    result.valid = len(result.errors) == 0
    return result


def vacancy_to_dict(data: VacancyData) -> dict:
    d = asdict(data)
    d["mode"] = data.mode.value
    d["language"] = data.language.value if data.language else Language.MIXED.value
    return d


def vacancy_from_dict(d: dict) -> VacancyData:
    return vacancy_from_preview({
        "language": d.get("language", "MIXED"),
        "mode": d.get("mode", "SINGLE"),
        "company": d.get("company", ""),
        "vacancy": d.get("vacancy_title") or d.get("multi_title") or d.get("vacancy", ""),
        "vacancies": d.get("positions") or d.get("vacancies", []),
        "salary": d.get("salary", ""),
        "requirements_heading": d.get("requirements_heading", ""),
        "requirements": d.get("requirements", []),
        "responsibilities_heading": d.get("responsibilities_heading", ""),
        "responsibilities": d.get("responsibilities", []),
        "conditions_heading": d.get("conditions_heading", ""),
        "conditions": d.get("conditions", []),
        "phone": d.get("phone", ""),
        "address": d.get("address", ""),
        "instagram": d.get("instagram", ""),
    })
