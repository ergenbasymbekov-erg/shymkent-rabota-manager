"""Sanitize poster fields — strip labels, junk, platform footer; never render debug text."""

from __future__ import annotations

import re
from typing import Optional

from phones import format_phone_display, normalize_phone_internal

# Section headers — never render as content
SECTION_HEADER_RE = re.compile(
    r"^(company|компания|open positions?|vacancy titles?|vacancies|positions?|лауазымдар?|"
    r"ашық вакансиялар|открытые вакансии|poster text|requirements?|талаптар|требования|"
    r"conditions?|шарттар|условия|address|мекенжай|мекен-жай|адрес|contacts?|контакты|"
    r"байланыс|instagram|insta|salary|жалақы|зарплата|оплата|phone|телефон)\s*[:：]?\s*$",
    re.I,
)

# Inline "Label: value" — strip label, keep value
INLINE_LABEL_RE = re.compile(
    r"^(company|компания|open positions?|vacancy titles?|vacancies|positions?|лауазым|"
    r"poster text|salary|жалақы|зарплата|оплата|phone|телефон|байланыс|contacts?|контакты|"
    r"address|мекенжай|мекен-жай|адрес|instagram|insta)\s*[:：]\s*(.+)$",
    re.I,
)

JUNK_VALUES = frozenset({
    "undefined", "null", "none", "n/a", "na", "—", "-", "...", "placeholder",
    "unknown", "unknown_position", "poster text", "vacancy titles", "positions",
})

PLATFORM_INSTAGRAM = frozenset({
    "shymkent_rabota_job", "shymkentrabota", "shymkent_rabota", "shymkent.rabota",
})


def is_section_header(line: str) -> bool:
    return bool(SECTION_HEADER_RE.match(line.strip()))


def strip_inline_label(line: str) -> str:
    s = line.strip()
    m = INLINE_LABEL_RE.match(s)
    if m:
        return m.group(2).strip()
    return s


def is_junk(text: str) -> bool:
    s = (text or "").strip().lower()
    if not s:
        return True
    if s in JUNK_VALUES:
        return True
    if s.startswith("@") and len(s) <= 2:
        return True
    if re.fullmatch(r"@+", s):
        return True
    return False


def _fix_all_caps(text: str) -> str:
    """Convert shout-case lines to normal capitalization."""
    s = (text or "").strip()
    if not s or len(s) < 3:
        return s
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return s
    upper = sum(1 for c in letters if c.isupper())
    if upper / len(letters) >= 0.85:
        return s[0].upper() + s[1:].lower()
    return s


def clean_display_text(text: str) -> str:
    s = strip_inline_label(text or "")
    s = s.strip().lstrip("•-*— ").strip()
    s = re.sub(r"\s+", " ", s)
    if is_junk(s):
        return ""
    return _fix_all_caps(s)


def clean_position(text: str) -> str:
    s = clean_display_text(text)
    if not s or is_section_header(s):
        return ""
    if s.lower() in ("vacancy titles", "open positions", "positions", "poster text"):
        return ""
    return s


def clean_company(text: str) -> str:
    s = clean_display_text(text)
    if not s or is_section_header(s):
        return ""
    return s


def clean_salary(text: str) -> str:
    s = clean_display_text(text)
    if not s or is_junk(s):
        return ""
    return s


def clean_phone(text: str) -> str:
    s = strip_inline_label(text or "").strip()
    if is_junk(s):
        return ""
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 10:
        norm, err = normalize_phone_internal(digits)
        if not err:
            return format_phone_display(norm)
    return clean_display_text(s)


def clean_instagram(text: str) -> str:
    s = strip_inline_label(text or "").strip()
    s = s.lstrip("@").strip()
    if is_junk(s):
        return ""
    if s.lower() in PLATFORM_INSTAGRAM:
        return ""
    if not s or s == "...":
        return ""
    return s


def sanitize_preview(preview: dict) -> dict:
    """Final pass before maket engine — values only, no labels or junk."""
    company = clean_company(preview.get("company") or "")
    salary = clean_salary(preview.get("salary") or "")
    phone = clean_phone(preview.get("phone") or "")
    instagram = clean_instagram(preview.get("instagram") or "")

    positions: list[str] = []
    seen: set[str] = set()
    for raw in preview.get("vacancies") or []:
        p = clean_position(str(raw))
        key = p.lower()
        if p and key not in seen:
            seen.add(key)
            positions.append(p)

    vacancy = clean_position(preview.get("vacancy") or "")
    if vacancy and vacancy.lower() not in seen:
        if not positions:
            positions = [vacancy]
        vacancy = positions[0] if len(positions) == 1 else ""

    is_multi = len(positions) > 1
    mode = "MULTI" if is_multi else "SINGLE"
    if not is_multi and len(positions) == 1:
        vacancy = positions[0]
        positions = []

    return {
        "language": preview.get("language") or "MIXED",
        "mode": mode,
        "company": company,
        "vacancy": vacancy,
        "vacancies": positions if is_multi else [],
        "salary": salary,
        "requirements_heading": "",
        "requirements": [],
        "responsibilities": [],
        "conditions_heading": "",
        "conditions": [],
        "phones": [phone] if phone else [],
        "phone": phone,
        "address": "",
        "address_notes": "",
        "instagram": instagram,
        "notes": "",
        "unsorted_review": [],
    }


def preview_debug_summary(preview: dict) -> dict:
    """Human-readable summary for debug panel."""
    positions = list(preview.get("vacancies") or [])
    if preview.get("vacancy") and not positions:
        positions = [preview["vacancy"]]
    return {
        "company": preview.get("company") or "",
        "positions": positions,
        "salary": preview.get("salary") or "",
        "phone": preview.get("phone") or "",
        "instagram": preview.get("instagram") or "",
        "mode": preview.get("mode") or "",
    }
