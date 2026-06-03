"""Generate All — poster, Telegram, and WhatsApp text from approved structured JSON."""

import re
from typing import Literal, Optional

from language import DominantLanguage, detect_dominant_language
from phones import _digits, format_phone_display
from position import is_unknown_position
from editorial import (
    build_public_preamble,
    can_publish_public,
    headline_covers_company,
    normalize_fields_dict,
    skip_global_requirements,
)
from schema import GenerateAllResult, StructuredData
from sections import rebuild_after_from_fields

OutputLanguage = Literal["kazakh", "russian"]

# Telegram / WhatsApp section templates (emoji, label key, heading)
MESSAGING_KAZAKH = [
    ("company", "🏢", "Компания:"),
    ("requirements", "📋", "Талаптар:"),
    ("conditions", "⏰", "Шарттары:"),
    ("salary", "💰", "Жалақы:"),
    ("address", "📍", "Мекенжай:"),
    ("phones", "📞", "Байланыс:"),
    ("instagram", "📷", "Instagram:"),
]

MESSAGING_RUSSIAN = [
    ("company", "🏢", "Компания:"),
    ("requirements", "📋", "Требования:"),
    ("conditions", "⏰", "Условия:"),
    ("salary", "💰", "Оплата:"),
    ("address", "📍", "Адрес:"),
    ("phones", "📞", "Контакты:"),
    ("instagram", "📷", "Instagram:"),
]


def _substantive(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    if re.fullmatch(r"[\s\W_]+", s):
        return False
    return True


def detect_structured_language(structured: StructuredData) -> OutputLanguage:
    parts = [
        structured.company,
        structured.vacancy_title,
        structured.salary,
        structured.address,
        structured.address_notes,
        structured.notes,
        " ".join(structured.requirements or []),
        " ".join(structured.conditions or []),
    ]
    blob = "\n".join(p for p in parts if p)
    return detect_dominant_language(blob) if blob.strip() else "kazakh"


def _fields_dict(structured: StructuredData) -> dict:
    return structured.model_dump()


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


def _position_lines(fields: dict, language: OutputLanguage) -> list[str]:
    return []


def _section_content(key: str, fields: dict, language: OutputLanguage) -> list[str]:
    if key == "company":
        v = (fields.get("company") or "").strip()
        return [v] if _substantive(v) else []
    if key == "vacancy_title":
        return []
    if key == "requirements":
        if skip_global_requirements(fields):
            return []
        return [x.strip() for x in (fields.get("requirements") or []) if _substantive(x)]
    if key == "conditions":
        return [x.strip() for x in (fields.get("conditions") or []) if _substantive(x)]
    if key == "salary":
        v = (fields.get("salary") or "").strip()
        return [v] if _substantive(v) else []
    if key == "instagram":
        v = (fields.get("instagram") or "").strip()
        return [v] if _substantive(v) else []
    if key == "address":
        return _address_lines(fields)
    if key == "phones":
        return _phone_lines(fields)
    return []


def generate_poster_text(structured: StructuredData, language: OutputLanguage) -> str:
    """Clean poster format — no emojis, no markdown."""
    fields = normalize_fields_dict(_fields_dict(structured), language)
    preamble = build_public_preamble(fields, language)
    return rebuild_after_from_fields(fields, language, preamble=preamble)


def _append_messaging_block(
    blocks: list[str],
    key: str,
    emoji: str,
    label: str,
    fields: dict,
    language: OutputLanguage,
    headline: str,
) -> None:
    if key == "vacancy_title":
        return
    if key == "company" and headline_covers_company(fields, headline):
        return
    lines = _section_content(key, fields, language)
    if not lines:
        return
    block = [f"{emoji} {label}"] + lines
    blocks.append("\n".join(block))


def generate_telegram_text(structured: StructuredData, language: OutputLanguage) -> str:
    """Telegram-ready copy with emojis; empty sections hidden."""
    fields = normalize_fields_dict(_fields_dict(structured), language)
    template = MESSAGING_KAZAKH if language == "kazakh" else MESSAGING_RUSSIAN
    blocks: list[str] = []

    headline = build_public_preamble(fields, language)
    if headline:
        blocks.append(headline)

    for key, emoji, label in template:
        _append_messaging_block(blocks, key, emoji, label, fields, language, headline)

    return "\n\n".join(blocks).strip()


def generate_whatsapp_text(structured: StructuredData, language: OutputLanguage) -> str:
    """WhatsApp-ready copy with emojis and bold labels; empty sections hidden."""
    fields = normalize_fields_dict(_fields_dict(structured), language)
    template = MESSAGING_KAZAKH if language == "kazakh" else MESSAGING_RUSSIAN
    blocks: list[str] = []

    headline = build_public_preamble(fields, language)
    if headline:
        blocks.append(headline)

    for key, emoji, label in template:
        if key == "company" and headline_covers_company(fields, headline):
            continue
        lines = _section_content(key, fields, language)
        if not lines:
            continue
        heading = label.rstrip(":")
        block = [f"{emoji} *{heading}:*"] + lines
        blocks.append("\n".join(block))

    return "\n\n".join(blocks).strip()


def generate_all(
    structured: StructuredData,
    language: Optional[DominantLanguage] = None,
) -> GenerateAllResult:
    """Generate poster, Telegram, and WhatsApp outputs from approved structured data."""
    lang = language or detect_structured_language(structured)
    fields = normalize_fields_dict(structured.model_dump(), lang)
    if not can_publish_public(fields):
        return GenerateAllResult(poster_text="", telegram_text="", whatsapp_text="", language=lang)
    return GenerateAllResult(
        poster_text=generate_poster_text(structured, lang),
        telegram_text=generate_telegram_text(structured, lang),
        whatsapp_text=generate_whatsapp_text(structured, lang),
        language=lang,
    )
