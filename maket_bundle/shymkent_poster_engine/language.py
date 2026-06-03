"""Language detection — no translation, preservation only."""

from __future__ import annotations

import re
from enum import Enum


class Language(str, Enum):
    KAZAKH = "KAZAKH"
    RUSSIAN = "RUSSIAN"
    ENGLISH = "ENGLISH"
    MIXED = "MIXED"


_KAZAKH_CHARS = re.compile(r"[әғқңөұүіһӘҒҚҢӨҰҮІҺ]")
_KAZAKH_WORDS = re.compile(
    r"\b(жалақы|талаптар|міндеттері|қажет|тойхан|қызметкерлер|тәжірибе)\b",
    re.I,
)
_RUSSIAN_WORDS = re.compile(
    r"\b(зарплата|требования|обязанности|требуется|нужен|нужна|нужны|официант|аспaz|аспaz)\b",
    re.I,
)
_ENGLISH_WORDS = re.compile(
    r"\b(salary|requirements|responsibilities|needed|required|waiter|cashier|company)\b",
    re.I,
)
_CYRILLIC = re.compile(r"[\u0400-\u04FF]")
_LATIN = re.compile(r"[A-Za-z]")


SECTION_LABELS = {
    Language.KAZAKH: {
        "requirements": "Талаптар:",
        "responsibilities": "Міндеттері:",
        "conditions": "Шарттар:",
        "multi_title": "ҚЫЗМЕТКЕРЛЕР ҚАЖЕТ",
        "salary_prefix": "Жалақы:",
    },
    Language.RUSSIAN: {
        "requirements": "Требования:",
        "responsibilities": "Обязанности:",
        "conditions": "Условия:",
        "multi_title": "ТРЕБУЮТСЯ СОТРУДНИКИ",
        "salary_prefix": "Зарплата:",
    },
    Language.ENGLISH: {
        "requirements": "Requirements:",
        "responsibilities": "Responsibilities:",
        "conditions": "Conditions:",
        "multi_title": "STAFF NEEDED",
        "salary_prefix": "Salary:",
    },
}


def detect_language(text: str) -> Language:
    """Detect original language from raw text. Never translates."""
    if not text.strip():
        return Language.MIXED

    kazakh_score = 0
    russian_score = 0
    english_score = 0

    if _KAZAKH_CHARS.search(text):
        kazakh_score += 3
    kazakh_score += len(_KAZAKH_WORDS.findall(text))
    russian_score += len(_RUSSIAN_WORDS.findall(text))
    english_score += len(_ENGLISH_WORDS.findall(text))

    cyrillic = len(_CYRILLIC.findall(text))
    latin = len(_LATIN.findall(text))

    if cyrillic and latin:
        if kazakh_score > 0:
            return Language.MIXED
        if russian_score > 0 and english_score > 0:
            return Language.MIXED
        if english_score > russian_score:
            return Language.MIXED

    scores = {
        Language.KAZAKH: kazakh_score + (2 if _KAZAKH_CHARS.search(text) else 0),
        Language.RUSSIAN: russian_score + (1 if cyrillic and not _KAZAKH_CHARS.search(text) else 0),
        Language.ENGLISH: english_score + (2 if latin and not cyrillic else 0),
    }

    top = max(scores, key=scores.get)
    if scores[top] == 0:
        if cyrillic:
            return Language.RUSSIAN
        if latin:
            return Language.ENGLISH
        return Language.MIXED

    second = sorted(scores.values(), reverse=True)[1]
    if second > 0 and scores[top] == second:
        return Language.MIXED

    return top


def section_labels(language: Language) -> dict[str, str]:
    """Default section headings for a language (used only when not parsed from input)."""
    if language == Language.MIXED:
        return SECTION_LABELS[Language.KAZAKH]
    return SECTION_LABELS.get(language, SECTION_LABELS[Language.KAZAKH])
