"""Dominant language detection and output validation for AI Editor."""

import re
from typing import Literal, Optional

DominantLanguage = Literal["russian", "kazakh"]

KAZAKH_CHAR_RE = re.compile(r"[әғқңөұүі]", re.I)

KAZAKH_MARKERS = [
    "қажет", "керек", "шарттары", "шарт", "жалақы", "мекенжай", "байланыс",
    "талаптар", "міндеттері", "кестесі", "тұрақты", "жұмыс уақыты",
]

RUSSIAN_MARKERS = [
    "требуется", "требуются", "нужен", "нужна", "нужны", "условия", "условие",
    "зарплата", "оплата", "адрес", "контакты", "контакт", "требования",
    "обязанности", "график работы", "график:", "звонки", "звонок",
]

KAZAKH_WORDS_HINT = ["қажет", "керек", "жалақы", "шарт", "мекен", "байланыс", "талап", "міндет", "жұмыс"]
RUSSIAN_WORDS_HINT = [
    "требуется", "нужен", "нужна", "зарплата", "оплата", "адрес", "график",
    "условия", "контакт", "вторые", "завтраки", "номер", "звонок", "ватсап",
]

SECTION_LABELS = {
    "russian": [
        "Компания:", "Должность:", "Требования:", "Обязанности:",
        "Условия:", "Оплата:", "Адрес:", "Контакты:", "Instagram:",
    ],
    "kazakh": [
        "Компания:", "Лауазым:", "Талаптар:", "Міндеттері:",
        "Шарттары:", "Жалақы:", "Мекенжай:", "Байланыс:", "Instagram:",
    ],
}


def detect_dominant_language(text: str) -> DominantLanguage:
    """Detect dominant language before editing."""
    kazakh_chars = len(KAZAKH_CHAR_RE.findall(text))
    lower = text.lower()

    kk_score = kazakh_chars * 3
    ru_score = 0

    for w in KAZAKH_WORDS_HINT:
        if w in lower:
            kk_score += 2
    for w in RUSSIAN_WORDS_HINT:
        if w in lower:
            ru_score += 2

    cyrillic_words = re.findall(r"[а-яёәғқңөұүі]+", lower, re.I)
    for word in cyrillic_words:
        if KAZAKH_CHAR_RE.search(word):
            kk_score += 1
        elif len(word) > 2:
            ru_score += 0.3

    if kk_score > ru_score:
        return "kazakh"
    return "russian"


def _collect_output_text(after: str, fields: dict) -> str:
    parts = [after]
    for key, val in fields.items():
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str) and item:
                    parts.append(item)
                elif isinstance(item, dict):
                    for v in item.values():
                        if isinstance(v, str) and v:
                            parts.append(v)
                        elif isinstance(v, list):
                            parts.extend(str(x) for x in v if x)
        elif isinstance(val, str) and val:
            parts.append(val)
    return "\n".join(parts).lower()


def validate_output_language(
    dominant: DominantLanguage,
    after: str,
    fields: Optional[dict] = None,
) -> tuple[bool, str]:
    """
    Return (ok, error_message).
    LANGUAGE_ERROR if wrong-language markers found.
    """
    blob = _collect_output_text(after, fields or {})
    blob = blob.lower()

    if dominant == "russian":
        for marker in KAZAKH_MARKERS:
            if marker in blob:
                return False, f"LANGUAGE_ERROR: Kazakh marker '{marker}' in Russian output"
        return True, ""

    for marker in RUSSIAN_MARKERS:
        if marker in blob:
            return False, f"LANGUAGE_ERROR: Russian marker '{marker}' in Kazakh output"
    return True, ""


FORBIDDEN_PHRASES = [
    "біз іздейміз", "біздің ұжымға", "бізге қажет", "бізге керек", "біз жұмысқа шақырамыз",
    "сізді күтеміз", "біз сізді күтеміз", "бізге келіңіз", "хабарласыңыз", "қосылыңыз",
    "join our team", "we are looking", "we are waiting", "contact us", "call us", "write to us",
    "мы ищем", "в нашу команду", "нам требуется", "наша команда", "нашу команду",
    "мы ждем вас", "приходите к нам", "ждем вас", "звоните нам", "пишите нам",
    "обращайтесь", "присоединяйтесь", "мы приглашаем",
]

FIRST_PERSON_RE = re.compile(
    r"\b(біз|мы)\s+("
    r"іздейміз|ищем|ждем|кутеміз|шақырамыз|приглашаем|"
    r"сізді|вас|керек|қажет|требуется"
    r")\b|"
    r"біздің\s+ұжымға|"
    r"в\s+нашу\s+команду|"
    r"нам\s+требуется",
    re.I,
)

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0000FE00-\U0000FEFF"
    "❤️🔥⭐✨💼📞✅❌"
    "]+",
    flags=re.UNICODE,
)


def validate_neutral_style(after: str, fields: Optional[dict] = None) -> tuple[bool, str]:
    """Return (ok, error). STYLE_ERROR if marketing/CTA/first-person/emojis found."""
    blob = _collect_output_text(after, fields or {}).lower()

    if EMOJI_RE.search(blob):
        return False, "STYLE_ERROR: emojis or decorative symbols in output"

    for phrase in FORBIDDEN_PHRASES:
        if phrase in blob:
            return False, f"STYLE_ERROR: forbidden phrase '{phrase}'"

    if FIRST_PERSON_RE.search(blob):
        return False, "STYLE_ERROR: third-person violation — employer/first-person voice"

    return True, ""


def language_instruction(dominant: DominantLanguage) -> str:
    labels = SECTION_LABELS[dominant]
    label_list = "\n".join(f"  {v}" for v in labels)
    lang_name = "RUSSIAN" if dominant == "russian" else "KAZAKH"

    return f"""
DETECTED DOMINANT LANGUAGE: {lang_name}
YOU MUST WRITE 100% IN {lang_name}. NO TRANSLATION. NO MIXING.

Use ONLY these section labels (exact spelling):
{label_list}

Do NOT use section labels from any other language.

Write third-person vacancy-board text only. Platform republishes — never employer voice.
No emojis. No CTAs. No first-person. No "our team". Pure facts.
"""
