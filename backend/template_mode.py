"""Template mode — classify lines for styling only; format Telegram/WhatsApp."""

from __future__ import annotations

import re
from typing import Literal

LineRole = Literal["hero", "section_header", "phone", "body", "blank"]

SKIP_LINE_RE = re.compile(
    r"^(vacancy titles?|poster text|positions?|position|undefined|null|none)\s*[:：]?\s*$",
    re.I,
)

SECTION_HEADERS = {
    "требования", "талаптар", "обязанности", "міндеттері", "миндеттері",
    "условия", "шарттары", "условия работы", "жұмыс шарттары", "жумыс шарттары",
    "зарплата", "жалақы", "жалакы", "оплата",
    "контакты", "байланыс", "телефон", "phone", "contacts",
    "адрес", "мекенжай", "мекен-жай", "address",
    "открытые вакансии", "ашық вакансиялар", "ашык вакансиялар",
    "instagram", "insta",
}

PHONE_RE = re.compile(r"^[\+\(]?\d[\d\s\-\(\)]{8,}$")


def _norm_header(s: str) -> str:
    return s.strip().rstrip(":：").lower()


def is_section_header(line: str) -> bool:
    key = _norm_header(line)
    return key in SECTION_HEADERS


def is_phone_line(line: str) -> bool:
    s = line.strip()
    digits = re.sub(r"\D", "", s)
    if len(digits) < 10:
        return False
    return bool(PHONE_RE.match(s.replace(" ", ""))) or bool(
        re.fullmatch(r"[\d\s\+\-\(\)]+", s)
    )


def should_skip_line(line: str) -> bool:
    return bool(SKIP_LINE_RE.match(line.strip()))


def first_section_index(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if line.strip() and is_section_header(line):
            return i
    return len(lines)


def classify_lines(text: str) -> list[tuple[str, LineRole]]:
    """Preserve exact line text; assign styling role only."""
    raw_lines = text.splitlines()
    first_hdr = first_section_index(raw_lines)
    out: list[tuple[str, LineRole]] = []

    for i, line in enumerate(raw_lines):
        if not line.strip():
            out.append((line, "blank"))
            continue
        if should_skip_line(line):
            continue
        if is_section_header(line):
            out.append((line, "section_header"))
        elif is_phone_line(line):
            out.append((line, "phone"))
        elif i < first_hdr:
            out.append((line, "hero"))
        else:
            out.append((line, "body"))

    return out
