"""
Meaning-based profession detection — recruiter logic, not hardcoded role lists.

A position is any profession, role, occupation, specialty or work function
the employer is trying to hire. Generic staff phrases are NOT professions.
"""

import re
from typing import Optional

from position import INVALID_JOB_PHRASES, is_unknown_position

# ── Gender words (NOT professions — strip before validation) ────────────────

GENDER_WORDS = frozenset({
    "қыз", "ұл", "әйел", "ер",
    "қыздар", "ұлдар", "девушки", "парни",
    "девушка", "парень", "мужчина", "женщина",
})

# ── Generic staff (NOT professions — only when NO real role remains) ──────────

_GENERIC_STAFF_WORDS = frozenset({
    "қызметкер", "қызметкерлер", "персонал", "staff", "worker", "workers",
    "employee", "employees", "жұмысшы", "жұмысшылар", "сотрудник", "сотрудники",
    "адам", "personnel", "employees", "workers",
})

_GENERIC_STAFF_PHRASES = (
    "қызметкер керек", "қызметкерлер керек", "қызметкер қажет",
    "персонал керек", "жұмысшы керек", "staff needed", "workers needed",
    "адам керек", "employee needed", "сотрудники требуются", "персонал нужен",
    "қызметкерлер қажет", "жұмысшы керек",
)

# ── Generic staff (NOT professions — only these block UNKNOWN fallback) ───────

_HIRING_SUFFIX_RE = re.compile(
    r"\s+(?:қажет|керек|требуется|требуются|нужен|нужна|нужны|ищем|kerек)\.?\s*$",
    re.I,
)
_BULLET_RE = re.compile(r"^[\-\•\*—–]\s*")
_DIGIT_START_RE = re.compile(r"^\d")
_PHONEISH_RE = re.compile(r"^[\+\d][\d\s\-\(\)]{8,}$")
_URL_RE = re.compile(r"https?://|@\w+|instagram|инстаграм|whatsapp", re.I)

# Requirement-only lines — not standalone professions
_REQUIREMENT_LINE_RE = re.compile(
    r"^(?:"
    r"опыт|возраст|график|кесте|зарплат|жалақы|оплат|schedule|salary|"
    r"ответствен|пунктуаль|требован|талап|услов|шарт|обязан|міндет|"
    r"ежеднев|смен|режим|график|стаж|оплата|адрес|мекен|контакт|тел"
    r")\b",
    re.I,
)

# Profession morphology (KZ/RU occupation patterns — not a fixed role list)
_PROFESSION_MORPHOLOGY_RE = re.compile(
    r"(?:"
    r"ер|ор|ёр|щик|щица|ница|ник|чик|ист|ант|ент|град|"
    r"шы|ші|cı|ci|"
    r"driver|operator|manager|stylist|barber|master|developer|"
    r"specialist|consultant|assistant|worker(?!s\b)"
    r")\b",
    re.I,
)

# Compound profession patterns
_COMPOUND_PROFESSION_RE = re.compile(
    r"(?:"
    r"универсал\w*\s+\w+|"
    r"мастер\s+\w+|"
    r"hair[\-\s]?\w+|"
    r"шеф[\-\s]?\w+|"
    r"категор(?:ии|ия)\s+[a-zа-яё0-9]+|"
    r"\w+\s+категор(?:ии|ия)"
    r")",
    re.I,
)

_SALARY_RE = re.compile(
    r"(?:жалақы|зарплат|оплат|salary|тг\b|тенге|₸|\d[\d\s]*(?:000|000)|келісімді)",
    re.I,
)
_DASH_SPLIT_RE = re.compile(r"^(.+?)\s*[—–]\s*(.+)$")  # em/en dash only — not Hair-стилист
_PAREN_QUAL_RE = re.compile(r"^(.+?)\s*(\([^)]+\))\s*$")
_WITH_EXPERIENCE_RE = re.compile(
    r"^(.+?)\s+(?:с\s+)(?:опытом|опыт)\s*(.*)$",
    re.I,
)
_CATEGORY_SUFFIX_RE = re.compile(
    r"^(.+?)\s+(?:категор(?:ии|ия)|category)\s+(.+)$",
    re.I,
)

# Lines that are clearly NOT professions
_NON_PROFESSION_RE = re.compile(
    r"^(?:"
    r"компания|company|лауазым|должность|вакансия|вакансии|"
    r"открыты|требуют|керек|қажет|условия|шарттар|контакты|адрес"
    r")\b",
    re.I,
)


def _normalize(text: str) -> str:
    t = (text or "").strip()
    t = _BULLET_RE.sub("", t).strip()
    t = _HIRING_SUFFIX_RE.sub("", t).strip()
    return re.sub(r"\s+", " ", t)


def strip_gender_words(text: str) -> str:
    """Remove gender tokens; keep the real profession."""
    words = (text or "").split()
    kept = [w for w in words if w.lower() not in GENDER_WORDS]
    return " ".join(kept).strip()


def _has_profession_signal(text: str) -> bool:
    """Profession hint without calling is_generic_staff (avoids recursion)."""
    t = strip_gender_words(_normalize(text))
    if not t or len(t) < 2:
        return False
    if is_requirement_only_line(t):
        return False
    core = re.sub(r"\([^)]*\)", "", t.lower()).strip()
    core = re.sub(r"\s*[—–]\s*.*$", "", core).strip()
    if _COMPOUND_PROFESSION_RE.search(core) or _PROFESSION_MORPHOLOGY_RE.search(core):
        return True
    words = t.split()
    if 1 <= len(words) <= 4:
        fillers = {"и", "или", "және", "or", "and", "на", "в", "для", "the", "a"}
        content = [w for w in words if w.lower() not in fillers]
        if content and re.search(r"[а-яёәғқңөұүі]{3,}", t, re.I):
            return True
    return False


def is_generic_staff(text: str) -> bool:
    """
    True only when text is generic staff with no real profession left.
    Gender words alone never make a line generic.
    """
    stripped = strip_gender_words(_normalize(text))
    if not stripped:
        return True
    if is_unknown_position(stripped):
        return False

    lower = stripped.lower()
    words = lower.split()

    if _has_profession_signal(stripped):
        non_generic = [w for w in words if w not in _GENERIC_STAFF_WORDS]
        if non_generic:
            return False

    for phrase in _GENERIC_STAFF_PHRASES + tuple(INVALID_JOB_PHRASES):
        if lower == phrase or lower.startswith(phrase + " "):
            return True

    if all(w in _GENERIC_STAFF_WORDS for w in words):
        return True

    if len(words) == 1 and words[0] in _GENERIC_STAFF_WORDS:
        return True

    if re.fullmatch(
        r"(?:сотрудник\w*|работник\w*|жұмысшы\w*|staff|workers?|employees?|қызметкер\w*)",
        lower,
    ):
        return True

    return False


def is_requirement_only_line(text: str) -> bool:
    """True when line is a requirement/condition, not a profession name."""
    t = _normalize(text)
    if not t:
        return True
    if _REQUIREMENT_LINE_RE.match(t):
        return True
    if re.search(r"\(\s*от\s+\d+", t, re.I):
        return False  # may be "Официант (от 18)" — profession + qual
    if _SALARY_RE.search(t) and not _DASH_SPLIT_RE.match(t):
        return True
    return False


def looks_like_profession(text: str) -> bool:
    """
    Meaning-based profession check — no hardcoded role list required.
    A human recruiter would recognize this as a job title / occupation.
    """
    t = _normalize(text)
    if not t or len(t) < 2:
        return False
    if is_generic_staff(t):
        return False
    if re.match(r"^категор(?:ии|ия)\s+[a-zа-яё0-9]", t, re.I):
        return False
    if is_requirement_only_line(t):
        return False
    if _NON_PROFESSION_RE.match(t):
        return False
    if _PHONEISH_RE.match(t.replace(" ", "")) and len(re.sub(r"\D", "", t)) >= 10:
        return False
    if _URL_RE.search(t):
        return False
    if _DIGIT_START_RE.match(t):
        return False

    words = t.split()
    if len(words) > 6:
        return False

    lower = t.lower()

    # Strip parenthetical for morphology check; only em/en dash splits tail
    core = re.sub(r"\([^)]*\)", "", lower).strip()
    core = re.sub(r"\s*[—–]\s*.*$", "", core).strip()

    if _COMPOUND_PROFESSION_RE.search(core):
        return True
    if _PROFESSION_MORPHOLOGY_RE.search(core):
        return True

    # Short standalone noun phrase (1–4 words) — typical position line in vacancy lists
    if 1 <= len(words) <= 4:
        # Reject if every word is a common filler
        fillers = {"и", "или", "және", "or", "and", "на", "в", "для", "the", "a"}
        content_words = [w for w in words if w.lower() not in fillers]
        if content_words and not is_requirement_only_line(core):
            # Latin mixed titles (Hair-стилист, Lashmaker)
            if re.search(r"[a-zA-Z]", t) and re.search(r"[а-яёәғқңөұүі]", t, re.I):
                return True
            if re.search(r"[a-zA-Z]{3,}", t):
                return True
            # Cyrillic occupation-like word(s)
            if re.search(r"[а-яёәғқңөұүі]{3,}", t, re.I):
                return True

    return False


def display_profession(name: str) -> str:
    n = strip_gender_words(_normalize(name))
    n = re.sub(r"\([^)]*\)", "", n).strip()
    n = re.sub(r"\s*[—–]\s*.*$", "", n).strip()
    if not n:
        return ""
    parts = n.split()
    return " ".join(p[0].upper() + p[1:] if len(p) > 1 else p.upper() for p in parts)


def parse_position_line(line: str) -> Optional[dict]:
    """
    Parse one line into position + optional salary + requirements.

    Handles:
      Официант (от 18 лет)
      Няня — 130000 тг
      Барбер — опыт от 1 года
      Повар с опытом работы
      Водитель категории С
      Plain: Повар / Сатушы
    """
    raw = line.strip()
    if not raw:
        return None

    salary = ""
    requirements: list[str] = []
    role_part = _normalize(raw)

    # Em-dash split: salary OR requirement tail
    dash = _DASH_SPLIT_RE.match(role_part)
    if dash:
        role_part = dash.group(1).strip()
        tail = dash.group(2).strip()
        if _SALARY_RE.search(tail):
            salary = tail
        elif tail:
            requirements.append(tail)

    # Parenthetical qualifier
    paren = _PAREN_QUAL_RE.match(role_part)
    if paren:
        role_part = paren.group(1).strip()
        qual = paren.group(2).strip()
        if qual:
            requirements.append(qual)

    # "с опытом"
    exp = _WITH_EXPERIENCE_RE.match(role_part)
    if exp:
        role_part = exp.group(1).strip()
        rest = (exp.group(2) or "").strip()
        requirements.append(f"с опытом {rest}".strip() if rest else "с опытом")

    # "категории С"
    cat = _CATEGORY_SUFFIX_RE.match(role_part)
    if cat:
        role_part = cat.group(1).strip()
        requirements.append(f"категории {cat.group(2).strip()}")

    profession = display_profession(role_part)
    if not profession or is_generic_staff(profession):
        return None
    if not looks_like_profession(profession):
        return None

    return {
        "position": profession,
        "salary": salary,
        "requirements": requirements,
    }


def extract_professions_from_lines(lines: list[str]) -> list[dict]:
    """Scan lines for profession entries (meaning-based)."""
    out: list[dict] = []
    seen: set[str] = set()
    for line in lines:
        parsed = parse_position_line(line)
        if not parsed:
            continue
        key = parsed["position"].lower()
        if key not in seen:
            seen.add(key)
            out.append(parsed)
    return out
