"""Position quality control — critical invalid tokens → UNKNOWN_POSITION, poster blocked."""

import re
from typing import Optional

SINGLE_POSITION = "SINGLE_POSITION"
MULTI_POSITION = "MULTI_POSITION"

MULTI_TITLE_KZ = "Ашық вакансиялар"
MULTI_TITLE_RU = "Открытые вакансии"

MULTI_HEADLINE_KZ = "Бірнеше вакансия ашық"
MULTI_HEADLINE_RU = "Открыты вакансии"

POSITIONS_LABEL_KZ = "Вакансиялар:"
POSITIONS_LABEL_RU = "Вакансии:"

UNKNOWN_POSITION = "UNKNOWN_POSITION"
CONFIDENCE_PENALTY = 30

POSITION_UNKNOWN_WARNING = "Нақты лауазым көрсетілмеген."
POSITION_UNKNOWN_WARNING_RU = "Должность не указана точно."
POSITION_INVENTED_WARNING = "Лауазым/должность не найдена в исходном тексте — возможно выдумана."
POSTER_BLOCKED_MESSAGE = "Poster generation blocked — manager approval required."

# If vacancy title CONTAINS any of these → UNKNOWN_POSITION
CRITICAL_INVALID_TOKENS = [
    "қызметкерлер",
    "қыз қызметкер",
    "ер қызметкер",
    "қызметкер",
    "персонал",
    "staff",
    "workers",
    "worker",
    "employee",
    "employees",
    "жұмысшы",
    "сотрудник",
    "сотрудники",
    "адам",
]

INVALID_JOB_PHRASES = [
    "қызметкер керек",
    "қызметкерлер керек",
    "қызметкер қажет",
    "персонал керек",
    "жұмысшы керек",
    "staff needed",
    "workers needed",
    "адам керек",
    "employee needed",
]

KNOWN_ROLES = [
    "жүк тасушы", "продавец-консультант", "middle python developer",
    "кассир", "сатушы", "бариста", "тәрбиеші", "аспаз", "аспазшы", "даяшы",
    "официант", "курьер", "повар", "шеф", "администратор", "оператор",
    "фармацевт", "фarmacевт", "жүргізуші", "консультант", "мойщик", "грузчик",
    "секретарь", "менеджер", "инженер", "программист", "оптик", "қоймашы",
    "оптометрист", "әкімші", "кассирші", "дворник", "охранник",
    "горничная", "разнорабочий", "разнорабочие", "мойщик автомобилей",
    "станок операторы", "жеке дене шынықтырушы", "шеф-повар",
    "салатница", "посудница", "посудомойщица", "посудомойщик",
    "воспитатель", "продавец", "шеф-повар", "водитель", "няня",
    "ассистент тәрбиеші", "ассистент воспитателя",
    "барбер", "barber", "стилист", "stylist", "мастер шугаринга",
    "hair стилист", "шugarинг", "шугаринг",
    "универсальный повар", "чистильщик рыбы", "чистильщик",
    "лeshмейкер", "lashmaker", "лashмейкер", "лешмейкер",
]

KNOWN_ROLES_SORTED = sorted(set(KNOWN_ROLES), key=len, reverse=True)

MANAGER_REVIEW_REASON = POSITION_UNKNOWN_WARNING
INVALID_UNKNOWN_POSITION = "INVALID_UNKNOWN_POSITION"

_WORD_RE = re.compile(r"[a-zа-яёәғқңөұүі]+", re.I)

POSITION_SECTION_HEADER_RE = re.compile(
    r"^(?:"
    r"Ашық\s+вакансиялар|"
    r"Открытые\s+вакансии|"
    r"Открытые\s+вакансия|"
    r"Открыты\s+вакансии|"
    r"Вакансии|"
    r"Вакансиялар|"
    r"Керек|"
    r"Қажет|"
    r"Требуются|"
    r"Требуется"
    r")\s*:?\s*(.*)$",
    re.I,
)

NEXT_SECTION_RE = re.compile(
    r"^(?:"
    r"Компания|Лауазым|Должность|Талаптар|Требования|"
    r"Міндеттері|Обязанности|Шарттары|Условия|Жалақы|Оплата|Зарплата|"
    r"Мекенжай|Адрес|Байланыс|Контакты|Instagram|Инстаграм|"
    r"График|Кесте|Жұмыс\s+уақыты|Жұмыс\s+кестесі|"
    r"Открытые\s+вакансии|Открыты\s+вакансии|Ашық\s+вакансиялар|"
    r"Вакансии|Вакансиялар|Керек|Қажет|Требуются"
    r")\s*:",
    re.I,
)

_PHONE_LINE_RE = re.compile(r"^[\+\d][\d\s\-\(\)]{8,}$")


def is_valid_role(title: str) -> bool:
    """True when title is a publishable role (not empty, unknown, or generic staff)."""
    from profession import looks_like_profession

    t = strip_gender_words((title or "").strip())
    if not t:
        return False
    if is_unknown_position(t):
        return False
    if is_generic_staff(t):
        return False
    return looks_like_profession(t) or _matches_known_role(t)


def valid_positions(positions: list) -> list[str]:
    """Return cleaned valid roles from positions[], preserving order."""
    out: list[str] = []
    for p in positions or []:
        p = (p or "").strip()
        if not p:
            continue
        if is_valid_role(p):
            cap = _capitalize_role(p)
            if cap not in out:
                out.append(cap)
    return out


def roles_from_position_groups(groups: list) -> list[str]:
    """Extract position names from position_groups[]."""
    roles: list[str] = []
    for g in groups or []:
        if isinstance(g, dict):
            pos = (g.get("position") or "").strip()
        else:
            pos = (getattr(g, "position", "") or "").strip()
        if pos:
            roles.append(pos)
    return valid_positions(roles)


def sync_positions_fields(fields: dict) -> dict:
    """
    Pipeline fix: copy roles into positions[] from position_groups or vacancy_title
    when GPT/editor put them only in groups or title.
    """
    out = dict(fields)
    roles = valid_positions(out.get("positions") or [])
    if not roles:
        roles = roles_from_position_groups(out.get("position_groups") or [])
    if not roles:
        title = (out.get("vacancy_title") or "").strip()
        if is_valid_role(title):
            roles = valid_positions([title])
    if roles:
        out["positions"] = roles
    return out


def has_valid_positions(vacancy_title: str = "", positions: Optional[list] = None) -> bool:
    """True when at least one real role exists in positions[] or vacancy_title."""
    if valid_positions(positions or []):
        return True
    return is_valid_role(vacancy_title)


def position_unknown(vacancy_title: str = "", positions: Optional[list] = None) -> bool:
    """UNKNOWN_POSITION only when positions.length == 0."""
    return len(valid_positions(positions or [])) == 0


def is_unknown_position(title: str) -> bool:
    t = (title or "").strip().upper().replace(" ", "_")
    return t in ("UNKNOWN", "UNKNOWN_POSITION")


def contains_critical_invalid_token(title: str) -> bool:
    """True when title is generic staff only — not when a real profession remains."""
    if not title or not title.strip():
        return True
    if is_unknown_position(title):
        return False
    from profession import is_generic_staff
    return is_generic_staff(title)


def is_invalid_job_title(title: str) -> bool:
    """True when title is empty, unknown-bound, or contains critical invalid tokens."""
    if not title or not title.strip():
        return True
    if is_unknown_position(title):
        return False
    return contains_critical_invalid_token(title)


def is_generic_position(title: str) -> bool:
    """Alias used by editor retries."""
    return is_invalid_job_title(title)


def _position_warning(dominant: str) -> str:
    return POSITION_UNKNOWN_WARNING if dominant == "kazakh" else POSITION_UNKNOWN_WARNING_RU


def _capitalize_role(role: str) -> str:
    role = role.strip()
    if not role:
        return role
    if " " in role:
        parts = role.split()
        return " ".join(p[0].upper() + p[1:] if len(p) > 1 else p.upper() for p in parts)
    return role[0].upper() + role[1:] if len(role) > 1 else role.upper()


def role_explicit_in_source(title: str, raw_text: str) -> bool:
    if not title or not raw_text:
        return False

    title_lower = title.strip().lower()
    raw_lower = raw_text.lower()

    if title_lower in raw_lower:
        return True

    if re.search(
        rf"(?<![a-zа-яёәғқңөұүі0-9]){re.escape(title_lower)}(?![a-zа-яёәғқңөұүі0-9])",
        raw_lower,
    ):
        return True

    title_words = [w for w in _WORD_RE.findall(title_lower) if len(w) >= 3]
    if title_words and all(
        re.search(rf"(?<![a-zа-яёәғқңөұүі0-9]){re.escape(w)}(?![a-zа-яёәғқңөұүі0-9])", raw_lower)
        for w in title_words
    ):
        return True

    for role in KNOWN_ROLES_SORTED:
        if role == title_lower and (role in raw_lower or re.search(rf"\b{re.escape(role)}\b", raw_lower)):
            return True

    return False


_GENDER_WORDS = frozenset({
    "қыз", "ұл", "әйел", "ер",
    "девушка", "парень", "мужчина", "женщина",
})

_VENUE_LOCATIVE_RE = re.compile(
    r"(?:дүкеніне|кафесіне|салонына|мекемесіне)",
    re.I,
)

_HIRING_NEED_SUFFIX_RE = re.compile(
    r"(?:қажет|керек|требуется|требуются|нужен|нужна|нужны)\.?\s*$",
    re.I,
)

_VENUE_HIRING_PROFESSION_RE = re.compile(
    r"(?:дүкеніне|кафесіне|салонына|мекемесіне)\s+(.+?)\s+"
    r"(?:қажет|керек|требуется|требуются|нужен|нужна|нужны)\.?\s*$",
    re.I,
)

_INLINE_HIRING_PROFESSION_RE = re.compile(
    r"^(.+?)\s+(?:қажет|керек|требуется|требуются|нужен|нужна|нужны)\.?\s*$",
    re.I,
)


def strip_gender_words(text: str) -> str:
    """Remove gender tokens; keep the real profession."""
    from profession import strip_gender_words as _strip
    return _strip(text)


def _profession_from_hiring_chunk(chunk: str) -> Optional[str]:
    """Turn a hiring phrase fragment into a single profession name."""
    from profession import display_profession, looks_like_profession

    cleaned = strip_gender_words(chunk)
    if not cleaned:
        return None

    lower = cleaned.lower()
    for role in KNOWN_ROLES_SORTED:
        if role == lower or (
            re.search(
                rf"(?<![a-zа-яёәғқңөұүі0-9]){re.escape(role)}(?![a-zа-яёәғқңөұүі0-9])",
                lower,
            )
        ):
            return _capitalize_role(role)

    if looks_like_profession(cleaned) and not contains_critical_invalid_token(cleaned):
        return display_profession(cleaned)
    return None


_RU_VENUE_HIRING_RE = re.compile(
    r"(?:^|\b)(?:в\s+)?(?:"
    r"магазин(?:е|а|)?|кафе|ресторан(?:е|а|)?|салон(?:е|а|)?|"
    r"заведени(?:е|и)|бар(?:е|а|)?|shop|store"
    r")\s+(?:требуется|требуются|нужен|нужна|нужны)\s+(.+?)\.?\s*$",
    re.I,
)


def extract_profession_from_hiring_line(line: str) -> Optional[str]:
    """
    Extract profession from hiring lines, e.g.:
    «Арман» азық-түлік дүкеніне сатушы қыз қажет → Сатушы
    қыз сатушы керек → Сатушы
    """
    s = (line or "").strip()
    if not s:
        return None

    m = _VENUE_HIRING_PROFESSION_RE.search(s)
    if m:
        return _profession_from_hiring_chunk(m.group(1))

    m = _RU_VENUE_HIRING_RE.search(s)
    if m:
        return _profession_from_hiring_chunk(m.group(1))

    if _HIRING_NEED_SUFFIX_RE.search(s) and not _VENUE_LOCATIVE_RE.search(s):
        m = _INLINE_HIRING_PROFESSION_RE.match(s)
        if m:
            return _profession_from_hiring_chunk(m.group(1))

    if not _HIRING_NEED_SUFFIX_RE.search(s) and "," not in s and "/" not in s:
        prof = _profession_from_hiring_chunk(s)
        if prof and len(strip_gender_words(s).split()) <= 3:
            return prof

    return None


def _profession_from_part(part: str) -> Optional[str]:
    """Extract profession from a single list item or short phrase."""
    part = (part or "").strip()
    if not part:
        return None
    hiring = extract_profession_from_hiring_line(part)
    if hiring:
        return hiring
    return _profession_from_hiring_chunk(part)


def extract_positions_from_hiring_lines(raw_text: str) -> list[str]:
    """Scan raw text for venue/inline hiring lines; return distinct professions."""
    if not raw_text:
        return []

    def _add(prof: Optional[str], seen: set[str], out: list[str]) -> None:
        if not prof:
            return
        key = prof.lower()
        if key not in seen:
            seen.add(key)
            out.append(prof)

    out: list[str] = []
    seen: set[str] = set()
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "," in stripped or "/" in stripped:
            from recruiter_reasoning import _split_multi_on_line
            parts = _split_multi_on_line(stripped)
            if len(parts) > 1:
                for part in parts:
                    _add(_profession_from_part(part), seen, out)
                continue
        _add(extract_profession_from_hiring_line(stripped), seen, out)

    if not out:
        stripped = raw_text.strip()
        if "," in stripped or "/" in stripped:
            from recruiter_reasoning import _split_multi_on_line
            parts = _split_multi_on_line(stripped)
            if len(parts) > 1:
                for part in parts:
                    _add(_profession_from_part(part), seen, out)
        else:
            _add(extract_profession_from_hiring_line(stripped), seen, out)
    return out


def _parse_section_candidate_line(line: str) -> Optional[dict]:
    """Parse one vacancy-list line into position + optional salary/requirements."""
    from profession import parse_position_line

    cleaned = re.sub(r"^[\-\•\*—–]\s*", "", (line or "").strip()).strip()
    if not cleaned:
        return None
    if NEXT_SECTION_RE.match(cleaned) or POSITION_SECTION_HEADER_RE.match(cleaned):
        return None
    if _PHONE_LINE_RE.match(cleaned.replace(" ", "")):
        return None

    parsed = parse_position_line(cleaned)
    if not parsed or not (parsed.get("position") or "").strip():
        return None
    if is_generic_staff(parsed["position"]):
        return None
    return parsed


def extract_fallback_from_raw(raw_text: str) -> dict:
    """
    Deterministic fallback — vacancy section labels + cleaned position lines.
    Returns {positions: [], position_groups: []}.
    """
    empty = {"positions": [], "position_groups": []}
    if not raw_text or not raw_text.strip():
        return empty

    lines = raw_text.splitlines()
    groups: list[dict] = []
    seen: set[str] = set()
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()
        m = POSITION_SECTION_HEADER_RE.match(stripped)
        if not m:
            i += 1
            continue

        inline = (m.group(1) or "").strip()
        if inline:
            parsed = _parse_section_candidate_line(inline)
            if parsed:
                key = parsed["position"].lower()
                if key not in seen:
                    seen.add(key)
                    groups.append({
                        "position": parsed["position"],
                        "requirements": list(parsed.get("requirements") or []),
                        "responsibilities": [],
                        "conditions": [],
                        "salary": parsed.get("salary") or "",
                        "schedule": [],
                    })

        i += 1
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if POSITION_SECTION_HEADER_RE.match(line) or NEXT_SECTION_RE.match(line):
                break
            parsed = _parse_section_candidate_line(line)
            if parsed:
                key = parsed["position"].lower()
                if key not in seen:
                    seen.add(key)
                    groups.append({
                        "position": parsed["position"],
                        "requirements": list(parsed.get("requirements") or []),
                        "responsibilities": [],
                        "conditions": [],
                        "salary": parsed.get("salary") or "",
                        "schedule": [],
                    })
            i += 1

    if not groups:
        return empty

    positions = [g["position"] for g in groups]
    return {"positions": positions, "position_groups": groups}


def extract_positions_from_sections(raw_text: str) -> list[str]:
    """Read position lines after vacancy section headers."""
    return extract_fallback_from_raw(raw_text).get("positions") or []


def apply_raw_position_fallback(
    fields: dict,
    raw_text: str,
    dominant: str = "kazakh",
) -> dict:
    """Use raw-text section fallback; fix UNKNOWN title when positions exist."""
    out = dict(fields)
    fb = extract_fallback_from_raw(raw_text) if raw_text.strip() else {}
    fb_positions = fb.get("positions") or []

    if fb_positions:
        out["positions"] = fb_positions
        if fb.get("position_groups"):
            out["position_groups"] = fb["position_groups"]
    else:
        listed = [
            p.strip() for p in (out.get("positions") or [])
            if (p or "").strip() and not is_unknown_position((p or "").strip())
        ]
        if not listed and raw_text.strip():
            from_raw = extract_positions_from_raw(raw_text)
            if from_raw:
                out["positions"] = from_raw

    out, _, _ = enforce_position_priority(out, dominant)
    return out


def extract_positions_from_raw(raw_text: str) -> list[str]:
    """Deterministic fallback first, then hiring lines and recruiter reasoning."""
    section = extract_fallback_from_raw(raw_text).get("positions") or []
    if section:
        return section

    hiring = valid_positions(extract_positions_from_hiring_lines(raw_text))
    if hiring:
        return hiring

    from recruiter_reasoning import extract_with_recruiter_reasoning

    result = extract_with_recruiter_reasoning(raw_text)
    if result.get("positions"):
        return result["positions"]
    return extract_all_roles_from_raw(raw_text)


def extract_position_groups_from_raw(raw_text: str) -> list[dict]:
    """Human recruiter proximity extraction — per-position blocks only."""
    from recruiter_reasoning import extract_position_groups_from_raw as _extract_groups
    return _extract_groups(raw_text)


def multi_vacancy_title(dominant: str = "kazakh") -> str:
    return MULTI_TITLE_KZ if dominant == "kazakh" else MULTI_TITLE_RU


def _matches_known_role(title: str) -> bool:
    """True when title matches a known profession (recruiter-visible role)."""
    t = (title or "").strip().lower()
    if not t:
        return False
    if t in {r.lower() for r in KNOWN_ROLES}:
        return True
    for role in KNOWN_ROLES_SORTED:
        if role == t or (role in t and len(t) <= len(role) + 5):
            return True
    return False


def enforce_position_priority(
    fields: dict,
    dominant: str = "kazakh",
) -> tuple[dict, bool, list[str]]:
    """
    HARD RULE: if positions.length > 0, UNKNOWN_POSITION is forbidden.

    Returns (fixed_fields, had_invalid_unknown, warnings).
    """
    out = dict(fields)
    warnings: list[str] = []
    had_invalid = False

    roles = valid_positions(out.get("positions") or [])
    if not roles:
        listed = [
            p.strip() for p in (out.get("positions") or [])
            if (p or "").strip() and not is_unknown_position((p or "").strip())
        ]
        if listed:
            roles = listed
            out["positions"] = listed
    if not roles:
        groups = out.get("position_groups") or []
        group_roles = []
        for g in groups:
            pos = (g.get("position") if isinstance(g, dict) else getattr(g, "position", "")) or ""
            if pos.strip():
                group_roles.append(pos.strip())
        roles = valid_positions(group_roles)
        if roles:
            out["positions"] = roles

    if not roles:
        return out, False, warnings

    title = (out.get("vacancy_title") or "").strip()
    if is_unknown_position(title):
        had_invalid = True
        warnings.append(
            f"{INVALID_UNKNOWN_POSITION} — {len(roles)} position(s) detected; "
            "vacancy_title corrected (UNKNOWN forbidden when positions exist)"
        )

    if len(roles) >= 2:
        out["vacancy_type"] = MULTI_POSITION
        out["positions"] = roles
        if is_unknown_position(title) or not title:
            out["vacancy_title"] = multi_vacancy_title(dominant)
    else:
        out["vacancy_type"] = SINGLE_POSITION
        out["positions"] = roles
        out["vacancy_title"] = roles[0]

    return out, had_invalid, warnings


def resolve_vacancy_type(
    positions: list,
    raw_text: str,
    dominant: str = "kazakh",
    vacancy_title: str = "",
) -> tuple[str, str, list[str], bool, list[str], int, str]:
    """
    Classify SINGLE_POSITION vs MULTI_POSITION.
    Returns (vacancy_type, vacancy_title, positions, review_required, warnings, penalty, reason).
    """
    roles = valid_positions(positions)
    if not roles:
        roles = valid_positions(extract_positions_from_raw(raw_text))

    if not roles:
        title, rr, warnings, penalty, reason = validate_position(vacancy_title, raw_text, dominant)
        if is_valid_role(title):
            return SINGLE_POSITION, title, [title], False, warnings, penalty, reason
        return SINGLE_POSITION, UNKNOWN_POSITION, [], rr, warnings, penalty, reason

    if len(roles) == 1:
        return SINGLE_POSITION, roles[0], roles, False, [], 0, ""

    return MULTI_POSITION, multi_vacancy_title(dominant), roles, False, [], 0, ""


def is_multi_vacancy(vacancy_type: str = "", positions: Optional[list] = None) -> bool:
    if vacancy_type == MULTI_POSITION:
        return True
    return len(valid_positions(positions or [])) >= 2


def extract_all_roles_from_raw(raw_text: str) -> list[str]:
    """Extract every explicit role word found in source text (multi-vacancy)."""
    if not raw_text:
        return []

    lower = raw_text.lower()
    found: list[tuple[int, str]] = []

    for role in KNOWN_ROLES_SORTED:
        if " " in role:
            start = 0
            while True:
                idx = lower.find(role, start)
                if idx < 0:
                    break
                found.append((idx, _capitalize_role(role)))
                start = idx + len(role)
        else:
            for m in re.finditer(
                rf"(?<![a-zа-яёәғқңөұүі0-9]){re.escape(role)}(?![a-zа-яёәғқңөұүі0-9])",
                lower,
            ):
                found.append((m.start(), _capitalize_role(role)))

    found.sort(key=lambda x: x[0])
    out: list[str] = []
    seen: set[str] = set()
    for _, role in found:
        key = role.lower()
        if key not in seen:
            seen.add(key)
            out.append(role)
    return out


def extract_explicit_role_from_raw(raw_text: str) -> Optional[str]:
    if not raw_text:
        return None

    lower = raw_text.lower()
    for role in KNOWN_ROLES_SORTED:
        if " " in role:
            if role in lower:
                return _capitalize_role(role)
        elif re.search(rf"(?<![a-zа-яёәғқңөұүі0-9]){re.escape(role)}(?![a-zа-яёәғқңөұүі0-9])", lower):
            return _capitalize_role(role)

    return None


def is_generic_staff(title: str) -> bool:
    from profession import is_generic_staff as _is_generic
    return _is_generic(title)


def _recover_profession_from_text(title: str, raw_text: str) -> Optional[str]:
    """Human-recruiter recovery — prefer real job over UNKNOWN."""
    from profession import display_profession, looks_like_profession

    for source in ((title or "").strip(), (raw_text or "").strip()):
        if not source:
            continue
        hiring = extract_profession_from_hiring_line(source)
        if hiring and not is_generic_staff(hiring):
            return hiring

    stripped = strip_gender_words((title or "").strip())
    if stripped and not is_generic_staff(stripped):
        if looks_like_profession(stripped) or _matches_known_role(stripped):
            return display_profession(stripped)

    explicit = extract_explicit_role_from_raw(raw_text)
    if explicit and not is_generic_staff(explicit):
        return explicit

    from_raw = valid_positions(extract_positions_from_hiring_lines(raw_text))
    if from_raw:
        return from_raw[0]

    return None


def _unknown_result(
    dominant: str,
    extra_warnings: Optional[list] = None,
) -> tuple[str, bool, list[str], int, str]:
    warnings = [_position_warning(dominant), POSTER_BLOCKED_MESSAGE]
    if extra_warnings:
        warnings.extend(extra_warnings)
    return UNKNOWN_POSITION, True, warnings, CONFIDENCE_PENALTY, MANAGER_REVIEW_REASON


def validate_position(
    vacancy_title: str,
    raw_text: str,
    dominant: str = "kazakh",
) -> tuple[str, bool, list[str], int, str]:
    """
    Returns (corrected_title, review_required, warnings, confidence_penalty, manager_review_reason).
    Prefer extracted profession; UNKNOWN only when no real job is understandable.
    """
    title = (vacancy_title or "").strip()
    empty_reason = ""

    recovered = _recover_profession_from_text(title, raw_text)
    if recovered:
        return recovered, False, [], 0, ""

    if is_unknown_position(title) or is_generic_staff(title):
        return _unknown_result(dominant)

    from profession import display_profession, looks_like_profession

    stripped = strip_gender_words(title)
    if stripped and (looks_like_profession(stripped) or _matches_known_role(stripped)):
        return display_profession(stripped), False, [], 0, ""

    if role_explicit_in_source(title, raw_text) or role_explicit_in_source(stripped, raw_text):
        return display_profession(stripped or title), False, [], 0, empty_reason

    return _unknown_result(dominant, [POSITION_INVENTED_WARNING])


def validate_positions_list(
    positions: list,
    raw_text: str,
    dominant: str = "kazakh",
) -> tuple[list, bool, list[str], int, str]:
    if not positions:
        from_raw = valid_positions(extract_positions_from_raw(raw_text))
        if from_raw:
            return from_raw, False, [], 0, ""
        return [], False, [], 0, ""

    cleaned: list[str] = []
    warnings: list[str] = []

    for pos in positions:
        p = (pos or "").strip()
        if not p or is_unknown_position(p):
            continue

        if is_valid_role(p):
            cap = _capitalize_role(strip_gender_words(p) or p)
            if cap not in cleaned:
                cleaned.append(cap)
            continue

        recovered = _recover_profession_from_text(p, raw_text)
        if recovered:
            cap = _capitalize_role(recovered)
            if cap not in cleaned:
                cleaned.append(cap)
            continue

        if is_generic_staff(p):
            continue

        if _matches_known_role(p) or role_explicit_in_source(p, raw_text):
            cap = _capitalize_role(strip_gender_words(p) or p)
            if cap not in cleaned:
                cleaned.append(cap)
            continue
        title, _, w, _, _ = validate_position(p, raw_text, dominant)
        if is_valid_role(title):
            cap = title if title != p else _capitalize_role(strip_gender_words(p) or p)
            if cap not in cleaned:
                cleaned.append(cap)
        elif is_unknown_position(title) or is_generic_staff(p):
            for msg in w:
                if msg not in warnings:
                    warnings.append(msg)

    cleaned = valid_positions(cleaned)
    if cleaned:
        return cleaned, False, warnings, 0, ""

    from_raw = valid_positions(extract_positions_from_raw(raw_text))
    if from_raw:
        return from_raw, False, warnings, 0, ""

    return [], True, warnings or [_position_warning(dominant), POSTER_BLOCKED_MESSAGE], CONFIDENCE_PENALTY, MANAGER_REVIEW_REASON
