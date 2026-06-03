"""Section rendering — remove empty headings; rebuild AFTER from field data."""

import re
from typing import Any, Optional

from editorial import (
    build_public_headline,
    build_public_preamble,
    headline_covers_company,
    normalize_fields_dict,
    normalize_list_lines,
    skip_global_requirements,
)
from language import DominantLanguage
from phones import _digits, format_phone_display
from position import MULTI_POSITION, is_unknown_position, valid_positions

SECTION_LABELS = (
    "Компания", "Лауазым", "Талаптар", "Міндеттері", "Шарттары", "Жалақы",
    "Мекенжай", "Байланыс", "Instagram", "Вакансиялар", "Вакансии",
    "Должность", "Требования", "Обязанности", "Условия", "Оплата", "Зарплата",
    "Адрес", "Контакты",
)

HEADING_RE = re.compile(
    rf"^({'|'.join(SECTION_LABELS)})\s*:\s*(.*)$",
    re.IGNORECASE,
)

KAZAKH_SECTIONS = {
    "company": "Компания:",
    "vacancy_title": "Лауазым:",
    "positions": "Вакансиялар:",
    "requirements": "Талаптар:",
    "responsibilities": "Міндеттері:",
    "conditions": "Шарттары:",
    "salary": "Жалақы:",
    "address": "Мекенжай:",
    "phones": "Байланыс:",
    "instagram": "Instagram:",
}

RUSSIAN_SECTIONS = {
    "company": "Компания:",
    "vacancy_title": "Должность:",
    "positions": "Вакансии:",
    "requirements": "Требования:",
    "responsibilities": "Обязанности:",
    "conditions": "Условия:",
    "salary": "Оплата:",
    "address": "Адрес:",
    "phones": "Контакты:",
    "instagram": "Instagram:",
}

# Labels to strip from raw GPT text when rebuilding
ALL_HEADINGS = set()
for m in KAZAKH_SECTIONS.values():
    ALL_HEADINGS.add(m.lower())
for m in RUSSIAN_SECTIONS.values():
    ALL_HEADINGS.add(m.lower())


def _substantive(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    if re.fullmatch(r"[\s\W_]+", s):
        return False
    return True


def _has_str(value: Any) -> bool:
    return _substantive(str(value)) if value is not None else False


def _has_list(items: Any) -> bool:
    if not items:
        return False
    return any(_substantive(x) for x in items)


def extract_preamble(text: str) -> str:
    """Lines before the first section heading — opening sentence."""
    if not text:
        return ""
    lines = []
    for line in text.splitlines():
        if HEADING_RE.match(line.strip()):
            break
        if _substantive(line):
            lines.append(line.strip())
    return "\n".join(lines).strip()


def _phone_lines(fields: dict) -> list[str]:
    displays = fields.get("phones_display") or []
    if displays:
        return [p.strip() for p in displays if _substantive(p)]
    out = []
    for p in fields.get("phones") or []:
        p = (p or "").strip()
        if not p:
            continue
        d = _digits(p)
        if len(d) == 11 and d.startswith("8"):
            out.append(format_phone_display(d))
        elif _substantive(p):
            out.append(p)
    return out


def _address_lines(fields: dict) -> list[str]:
    lines = []
    if _substantive(fields.get("address")):
        lines.append(fields["address"].strip())
    if _substantive(fields.get("address_notes")):
        note = fields["address_notes"].strip()
        if note not in lines:
            lines.append(note)
    return lines


def rebuild_after_from_fields(
    fields: dict,
    dominant: DominantLanguage,
    preamble: str = "",
) -> str:
    """Rebuild AFTER text from structured fields — no empty sections."""
    labels = KAZAKH_SECTIONS if dominant == "kazakh" else RUSSIAN_SECTIONS
    out: list[str] = []

    if _substantive(preamble):
        out.append(preamble.strip())
        out.append("")

    def add_section(key: str, lines: list[str]) -> None:
        if not lines:
            return
        out.append(labels[key])
        out.extend(lines)
        out.append("")

    if _has_str(fields.get("company")) and not headline_covers_company(fields, preamble):
        add_section("company", [fields["company"].strip()])

    if not skip_global_requirements(fields) and _has_list(fields.get("requirements")):
        reqs = normalize_list_lines(
            [x.strip() for x in fields["requirements"] if _substantive(x)],
            dominant,
        )
        add_section("requirements", reqs)

    if _has_list(fields.get("responsibilities")):
        add_section("responsibilities", [x.strip() for x in fields["responsibilities"] if _substantive(x)])

    if _has_list(fields.get("conditions")):
        conds = normalize_list_lines(
            [x.strip() for x in fields["conditions"] if _substantive(x)],
            dominant,
        )
        add_section("conditions", conds)

    if _has_str(fields.get("salary")):
        add_section("salary", [fields["salary"].strip()])

    addr = _address_lines(fields)
    if addr:
        add_section("address", addr)

    phones = _phone_lines(fields)
    if phones:
        add_section("phones", phones)

    if _has_str(fields.get("instagram")):
        add_section("instagram", [fields["instagram"].strip()])

    result = "\n".join(out).strip()
    return re.sub(r"\n{3,}", "\n\n", result)


def strip_empty_sections(text: str) -> str:
    """Parse and drop sections with no substantive content under heading."""
    if not text or not text.strip():
        return text

    lines = text.splitlines()
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    seen: dict[str, list[str]] = {}

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        m = HEADING_RE.match(stripped)

        if not m:
            if not sections and _substantive(stripped):
                preamble.append(stripped)
            i += 1
            continue

        label = m.group(1)
        heading = f"{label}:"
        inline = m.group(2).strip()
        content: list[str] = []
        if _substantive(inline):
            content.append(inline)

        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if HEADING_RE.match(nxt):
                break
            if _substantive(nxt):
                content.append(nxt)
            i += 1

        if not content:
            continue

        key = heading.lower()
        if key in seen:
            seen[key].extend(content)
        else:
            seen[key] = content
            sections.append((heading, seen[key]))

    out: list[str] = []
    out.extend(preamble)
    if preamble and sections:
        out.append("")
    for heading, content in sections:
        out.append(heading)
        out.extend(content)
        out.append("")

    result = "\n".join(out).strip()
    return re.sub(r"\n{3,}", "\n\n", result)


def clean_after_text(
    raw_after: str,
    fields: dict,
    dominant: DominantLanguage,
) -> str:
    """
    Final AFTER text: rebuild from structured fields so empty sections never appear.
    Uses vacancy headline when position is known; never exposes internal tokens.
    """
    normalized = normalize_fields_dict(fields, dominant)
    preamble = build_public_preamble(normalized, dominant)
    if not preamble:
        preamble = extract_preamble(raw_after)
    rebuilt = rebuild_after_from_fields(normalized, dominant, preamble)
    return strip_empty_sections(rebuilt)
