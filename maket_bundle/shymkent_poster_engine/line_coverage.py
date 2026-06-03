"""Line accountability — verify LLM classified every input line (audit only, not extraction)."""

from __future__ import annotations

import unicodedata


def split_meaningful_lines(raw_text: str) -> list[str]:
    """Split raw text into non-empty lines."""
    lines: list[str] = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped in {"•", "-", "*", "·", "—"}:
            continue
        lines.append(stripped)
    return lines


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.lower().strip()
    if text.startswith("•"):
        text = text[1:].strip()
    return " ".join(text.split())


def _lines_from_map(line_map: object) -> set[str]:
    mapped: set[str] = set()
    if not isinstance(line_map, list):
        return mapped
    for entry in line_map:
        if isinstance(entry, dict):
            line = str(entry.get("line", "")).strip()
            if line:
                mapped.add(_normalize(line))
    return mapped


def collect_field_fragments(preview: dict) -> list[str]:
    """Gather all LLM-extracted text fragments."""
    fragments: list[str] = []

    def add(value: object) -> None:
        if isinstance(value, str) and value.strip():
            fragments.append(value.strip())
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    fragments.append(item.strip())

    for key in (
        "company", "vacancy", "salary", "phone", "address", "address_notes",
        "instagram", "notes",
        "requirements_heading", "responsibilities_heading", "conditions_heading",
    ):
        add(preview.get(key))

    for key in ("phones", "vacancies", "positions", "requirements", "responsibilities", "conditions"):
        add(preview.get(key))

    return fragments


def _fragment_covers_line(line: str, fragment: str) -> bool:
    norm_line = _normalize(line)
    norm_frag = _normalize(fragment)
    if not norm_line or not norm_frag:
        return False
    if norm_line in norm_frag or norm_frag in norm_line:
        return True
    line_parts = norm_line.split()
    if line_parts and all(part in norm_frag for part in line_parts if len(part) >= 2):
        return True
    return False


def is_line_classified(line: str, preview: dict) -> bool:
    """Check if line was accounted for by LLM line_map or extracted fields."""
    norm = _normalize(line)
    if norm in _lines_from_map(preview.get("line_map")):
        return True
    fragments = collect_field_fragments(preview)
    return any(_fragment_covers_line(line, frag) for frag in fragments)


def enforce_line_coverage(raw_text: str, preview: dict) -> dict:
    """
    Audit: every meaningful line must be classified by the LLM.
    Unaccounted lines are appended to unsorted_review — never deleted.
    """
    lines = split_meaningful_lines(raw_text)

    unsorted: list[str] = []
    seen: set[str] = set()

    for item in preview.get("unsorted_review") or []:
        text = str(item).strip()
        if text:
            norm = _normalize(text)
            if norm not in seen:
                unsorted.append(text)
                seen.add(norm)

    unclassified: list[str] = []
    for line in lines:
        if is_line_classified(line, preview):
            continue
        norm = _normalize(line)
        if norm in seen:
            continue
        unclassified.append(line)
        unsorted.append(line)
        seen.add(norm)

    preview["unsorted_review"] = unsorted
    preview["coverage"] = {
        "total_lines": len(lines),
        "classified_lines": len(lines) - len(unclassified),
        "unclassified_lines": len(unclassified),
        "complete": len(unclassified) == 0,
    }
    return preview
