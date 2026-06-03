"""Parse rewrite poster_text → clean maket 4 preview JSON (values only, no labels)."""

from __future__ import annotations

import copy
import re
from typing import Optional

from language import detect_dominant_language
from poster_sanitize import (
    clean_company,
    clean_instagram,
    clean_phone,
    clean_position,
    clean_salary,
    is_junk,
    is_section_header,
    preview_debug_summary,
    sanitize_preview,
    strip_inline_label,
)

MAX_LINE_LEN = 200

PHONE_RE = re.compile(r"^[\+\(]?\d[\d\s\-\(\)]{8,}$")
INSTAGRAM_RE = re.compile(r"(^@[\w.]+|instagram\.com|instagr\.am)", re.I)
SALARY_RE = re.compile(
    r"(жалақы|оплат|зарплат|tenge|тенге|тг|₸|\d+\s*000|\d+\s*k\b|\d+\s*к\b|от\s+\d)",
    re.I,
)


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _is_phone(line: str) -> bool:
    d = _digits(line)
    if len(d) < 10:
        return False
    return bool(PHONE_RE.match(line.replace(" ", ""))) or bool(
        re.fullmatch(r"[\d\s\+\-\(\)]+", line.strip())
    )


def _is_instagram(line: str) -> bool:
    s = strip_inline_label(line)
    return bool(INSTAGRAM_RE.search(s)) and not _is_phone(s)


def _is_salary(line: str) -> bool:
    return bool(SALARY_RE.search(strip_inline_label(line)))


def _section_key(header: str) -> Optional[str]:
    h = header.strip().lower().rstrip(":：")
    if h in ("company", "компания"):
        return "company"
    if h in (
        "open positions", "open position", "positions", "position", "vacancy titles",
        "vacancy title", "vacancies", "лауазымдар", "ашық вакансиялар",
        "открытые вакансии", "вакансии",
    ):
        return "positions"
    if h in ("salary", "жалақы", "зарплата", "оплата"):
        return "salary"
    if h in ("contacts", "контакты", "байланыс", "phone", "телефон"):
        return "contacts"
    if h in ("instagram", "insta"):
        return "instagram"
    if h in ("poster text",):
        return "skip"
    return None


def _looks_like_ig_handle(line: str) -> bool:
    s = line.strip().lstrip("@")
    if not s or _is_phone(s) or is_junk(s):
        return False
    if _is_instagram(line):
        return True
    if re.search(r"[\u0400-\u04FF]", s):
        return False
    return bool(re.fullmatch(r"[a-zA-Z0-9._]{3,32}", s))


def _detect_role(line: str) -> str:
    s = strip_inline_label(line)
    if is_section_header(s) or is_section_header(line):
        return "skip"
    if is_junk(s):
        return "skip"
    if _is_phone(s):
        return "phone"
    if _looks_like_ig_handle(s):
        return "instagram"
    if _is_salary(s):
        return "salary"
    return "position"


def _parse_poster_text(poster_text: str) -> dict:
    company = ""
    positions: list[str] = []
    salary = ""
    phone = ""
    instagram = ""
    current: Optional[str] = None

    for raw in poster_text.splitlines():
        line = raw.strip()
        if not line:
            continue

        if is_section_header(line):
            current = _section_key(line)
            continue

        inline = re.match(
            r"^(company|компания|open positions?|vacancy titles?|positions?|salary|жалақы|зарплата|оплата|"
            r"phone|телефон|байланыс|contacts?|контакты|instagram|insta)\s*[:：]\s*(.+)$",
            line,
            re.I,
        )
        if inline:
            key = inline.group(1).lower()
            val = inline.group(2).strip()
            if not val or is_junk(val):
                continue
            if key in ("company", "компания"):
                company = val
            elif key in ("salary", "жалақы", "зарплата", "оплата"):
                salary = val
            elif key in ("phone", "телефон", "байланыс", "contacts", "контакты"):
                phone = val
            elif key in ("instagram", "insta"):
                instagram = val
            elif key in ("open positions", "open position", "vacancy titles", "vacancy title", "positions", "position"):
                positions.append(val.lstrip("-•* "))
            continue

        stripped = strip_inline_label(line)
        if not stripped or is_junk(stripped):
            continue

        role = _detect_role(stripped)
        if role == "skip":
            continue
        if role == "phone":
            phone = stripped
            continue
        if role == "instagram":
            instagram = stripped
            continue
        if role == "salary":
            salary = stripped
            continue

        if current == "skip":
            continue
        if current == "salary":
            salary = stripped if not salary else f"{salary} {stripped}"
        elif current == "contacts":
            r2 = _detect_role(stripped)
            if r2 == "phone":
                phone = stripped
            elif r2 == "instagram":
                instagram = stripped
        elif current == "instagram":
            instagram = stripped
        elif current == "positions":
            positions.append(stripped.lstrip("-•* "))
        elif current == "company":
            if not company:
                company = stripped
            else:
                positions.append(stripped.lstrip("-•* "))
        elif not company:
            company = stripped
        else:
            positions.append(stripped.lstrip("-•* "))

    return {
        "company": company,
        "positions": positions,
        "salary": salary,
        "phone": phone,
        "instagram": instagram,
    }


def poster_text_to_preview(poster_text: str, raw_text: str = "") -> dict:
    """Convert poster_text into sanitized maket 4 preview JSON."""
    if not (poster_text or "").strip():
        return sanitize_preview(_empty_preview())

    lang_blob = (raw_text or poster_text).strip()
    dominant = detect_dominant_language(lang_blob) if lang_blob else "kazakh"
    lang = "KAZAKH" if dominant == "kazakh" else "RUSSIAN"

    fields = _parse_poster_text(poster_text)
    preview = {
        "language": lang,
        "mode": "MULTI" if len(fields["positions"]) > 1 else "SINGLE",
        "company": clean_company(fields["company"]),
        "vacancy": clean_position(fields["positions"][0]) if len(fields["positions"]) == 1 else "",
        "vacancies": [clean_position(p) for p in fields["positions"] if clean_position(p)],
        "salary": clean_salary(fields["salary"]),
        "requirements_heading": "",
        "requirements": [],
        "responsibilities": [],
        "conditions_heading": "",
        "conditions": [],
        "phones": [],
        "phone": clean_phone(fields["phone"]),
        "address": "",
        "address_notes": "",
        "instagram": clean_instagram(fields["instagram"]),
        "notes": "",
        "unsorted_review": [],
    }
    if preview["phone"]:
        preview["phones"] = [preview["phone"]]

    if len(preview["vacancies"]) == 1:
        preview["vacancy"] = preview["vacancies"][0]
        preview["vacancies"] = []
        preview["mode"] = "SINGLE"

    return sanitize_preview(preview)


def poster_text_to_debug(poster_text: str, raw_text: str = "") -> dict:
    preview = poster_text_to_preview(poster_text, raw_text)
    return {
        "raw_poster_text": poster_text,
        "maket_preview": preview,
        "render_summary": preview_debug_summary(preview),
    }


def _empty_preview() -> dict:
    return {
        "language": "MIXED",
        "mode": "SINGLE",
        "company": "",
        "vacancy": "",
        "vacancies": [],
        "salary": "",
        "phone": "",
        "instagram": "",
    }


def trim_preview_for_fit(preview: dict) -> dict:
    """Poster fit — never remove positions; drop instagram then shorten company."""
    p = copy.deepcopy(preview)
    if p.get("instagram"):
        p["instagram"] = ""
        return sanitize_preview(p)
    if p.get("company"):
        c = str(p["company"])
        p["company"] = c[:50].rstrip() if len(c) > 50 else c
        return sanitize_preview(p)
    return p
