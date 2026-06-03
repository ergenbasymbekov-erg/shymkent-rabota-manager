"""Editorial rules — grammar, headlines, public-output sanitization."""

import re
from typing import Optional

from language import DominantLanguage
from position import (
    MULTI_POSITION,
    SINGLE_POSITION,
    enforce_position_priority,
    has_valid_positions,
    is_multi_vacancy,
    is_unknown_position,
    multi_vacancy_title,
    valid_positions,
)

INTERNAL_TOKENS = frozenset({"UNKNOWN_POSITION", "UNKNOWN", "REVIEW_REQUIRED"})

GRAMMAR_FIXES_KAZAKH: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^Тұрақты\s+жұмыс\s+істейтін\.?$", re.I), "Тұрақты жұмыс істеуге дайын."),
    (re.compile(r"^Жауапкершілігі\s+жоғары\.?$", re.I), "Жауапкершілік."),
    (re.compile(r"^Жасы\s+(\d+\s+жастан\s+жоғары)\.?$", re.I), r"\1."),
    (re.compile(r"^Жасы\s+(\d+)\+?\.?$", re.I), r"\1+."),
    (re.compile(r"^(\d+)\s+жастан\s+жоғары\.?$", re.I), r"\1 жастан жоғары."),
]

GRAMMAR_FIXES_RUSSIAN: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^Ответственный\.?$", re.I), "Ответственность."),
    (re.compile(r"^Ответственность\s+высокая\.?$", re.I), "Ответственность."),
    (re.compile(r"^Возраст\s+(\d+\+?)\.?$", re.I), r"Возраст \1."),
    (re.compile(r"^(\d+)\s*\+\.?$"), r"\1+."),
]

# (pattern, kazakh_dative_suffix, russian_accusative, include_brand_in_russian)
VENUE_RULES: list[tuple[re.Pattern, str, str, bool]] = [
    (re.compile(r"азық.?түлік", re.I), "азық-түлік дүкеніне", "магазин", True),
    (re.compile(r"дүкен|магазин|shop|store|market", re.I), "дүкеніне", "магазин", True),
    (re.compile(r"кофей|coffee|кофех", re.I), "кофейнясына", "кофейню", True),
    (re.compile(r"кофехан", re.I), "кофеханасына", "кофейню", True),
    (re.compile(r"балабақша|детск", re.I), "балабақшасына", "детский сад", True),
    (re.compile(r"халал\s+кафе", re.I), "халал кафесіне", "кафе", True),
    (re.compile(r"кафе|кафес", re.I), "кафесіне", "кафе", True),
    (re.compile(r"ресторан|рестоб", re.I), "рестобарына", "ресторан", True),
    (re.compile(r"аптека", re.I), "аптекасына", "аптеку", True),
    (re.compile(r"оптика", re.I), "оптикаға", "оптику", False),
]

# Venue suffixes used only when splitting brand from trailing venue descriptor
VENUE_SUFFIX_SPLIT = re.compile(
    r"(кофейня|кофехана|балабақша|дүкен|магазин|кафе|кафес|ресторан|аптека|оптика)\w*",
    re.I,
)

KAZAKH_DEFAULT_SUFFIX = "ұйымына"
RUSSIAN_DEFAULT_VENUE = "магазин"


def _lower_position(position: str) -> str:
    p = position.strip()
    if not p:
        return ""
    parts = p.split("-")
    if len(parts) == 2:
        return f"{parts[0].lower()}-{parts[1].lower()}"
    return p.lower()


def _guillemet_brand(name: str) -> str:
    name = (name or "").strip().strip("«»\"' ")
    if not name:
        return ""
    return f"«{name}»"


def _extract_brand(company: str) -> str:
    company = (company or "").strip()
    if not company:
        return ""
    quoted = re.search(r"[«\"']([^»\"']+)[»\"']", company)
    if quoted:
        return quoted.group(1).strip()
    if re.search(r"азық.?түлік", company, re.I):
        first = company.split()[0].strip("«»\"'-–—")
        if first:
            return first
    match = VENUE_SUFFIX_SPLIT.search(company)
    if match and match.start() > 0:
        brand = company[: match.start()].strip(" «»\"'-–—")
        if brand:
            return brand
    return company.strip(" «»\"'")


def _detect_venue(blob: str) -> tuple[str, str, bool]:
    """Return (kazakh_suffix, russian_venue, include_brand_for_russian)."""
    text = (blob or "").lower()
    if re.search(r"24/7", text):
        return "дүкеніне", "магазин", True
    for pattern, kz, ru, include_brand in VENUE_RULES:
        if pattern.search(text):
            return kz, ru, include_brand
    return KAZAKH_DEFAULT_SUFFIX, RUSSIAN_DEFAULT_VENUE, True


def _venue_blob_from_fields(fields: dict) -> str:
    return " ".join(
        str(fields.get(k, "") or "")
        for k in ("company", "notes", "address", "address_notes", "vacancy_title")
    ).strip()


def build_hiring_headline(
    company: str,
    position: str,
    language: DominantLanguage,
    poster_display: bool = False,
    context: str = "",
    fields: Optional[dict] = None,
) -> str:
    """
    Full hiring headline — company + venue + position + hiring intent.

    Kazakh: «La Moka» кофейнясына шеф-повар қажет
    Russian: В кофейню «La Moka» требуется шеф-повар
    """
    position = (position or "").strip()
    if not position or is_unknown_position(position):
        return ""

    blob = _venue_blob_from_fields(fields) if fields else " ".join(x for x in (company, context) if x).strip()
    if not blob:
        blob = " ".join(x for x in (company, context) if x).strip()
    brand = _extract_brand(company)
    kz_suffix, ru_venue, include_brand = _detect_venue(blob)
    pos = _display_position(position, poster_display)

    if language == "kazakh":
        if brand:
            headline = f"{_guillemet_brand(brand)} {kz_suffix} {pos} қажет"
        else:
            headline = f"{pos} қажет"
    else:
        if include_brand and brand:
            headline = f"В {ru_venue} {_guillemet_brand(brand)} требуется {pos}"
        else:
            headline = f"В {ru_venue} требуется {pos}"

    if poster_display:
        return headline.upper()
    return headline


def _display_position(position: str, poster_display: bool) -> str:
    p = (position or "").strip()
    if not p:
        return ""
    if poster_display:
        return p.upper()
    return _capitalize_role_display(p)


def format_hiring_headline(
    position: str,
    language: DominantLanguage,
    poster_display: bool = False,
    company: str = "",
    context: str = "",
) -> str:
    """Backward-compatible wrapper — requires company for full headline."""
    if company:
        return build_hiring_headline(company, position, language, poster_display, context)
    pos = (position or "").strip()
    if not pos or is_unknown_position(pos):
        return ""
    if language == "kazakh":
        headline = f"{_lower_position(pos)} қажет"
    else:
        headline = f"Требуется {_lower_position(pos)}"
    return headline.upper() if poster_display else headline


def build_vacancy_headline(
    company: str,
    position: str,
    language: DominantLanguage,
    context: str = "",
) -> str:
    return build_hiring_headline(company, position, language, poster_display=False, context=context)


def normalize_requirement_line(line: str, language: DominantLanguage = "kazakh") -> str:
    text = (line or "").strip()
    if not text:
        return ""
    fixes = GRAMMAR_FIXES_KAZAKH if language == "kazakh" else GRAMMAR_FIXES_RUSSIAN
    for pattern, repl in fixes:
        if pattern.search(text):
            text = pattern.sub(repl, text)
            break
    return text.strip()


def normalize_list_lines(lines: list[str], language: DominantLanguage = "kazakh") -> list[str]:
    out = []
    for line in lines or []:
        fixed = normalize_requirement_line(line, language)
        if fixed and fixed not in out:
            out.append(fixed)
    return out


def sanitize_internal_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text
    for token in INTERNAL_TOKENS:
        cleaned = re.sub(re.escape(token), "", cleaned, flags=re.I)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def normalize_fields_dict(fields: dict, language: DominantLanguage) -> dict:
    out = dict(fields)
    for key in ("requirements", "conditions", "responsibilities"):
        if out.get(key):
            out[key] = normalize_list_lines(out[key], language)
    if out.get("positions"):
        out["positions"] = [
            p.strip() for p in out["positions"]
            if p.strip() and not is_unknown_position(p.strip())
        ]
    out, _, _ = enforce_position_priority(out, language)
    roles = valid_positions(out.get("positions") or [])
    if roles:
        if len(roles) >= 2:
            out["vacancy_type"] = MULTI_POSITION
            if is_unknown_position(out.get("vacancy_title", "")):
                out["vacancy_title"] = multi_vacancy_title(language)
        elif len(roles) == 1:
            out["vacancy_type"] = SINGLE_POSITION
            out["vacancy_title"] = roles[0]
    elif not roles and not (out.get("positions") or []):
        if is_unknown_position((out.get("vacancy_title") or "").strip()):
            out["vacancy_title"] = "UNKNOWN_POSITION"
    if out.get("vacancy_type") not in (SINGLE_POSITION, MULTI_POSITION):
        out["vacancy_type"] = MULTI_POSITION if len(roles) >= 2 else SINGLE_POSITION
    return out


def primary_position(fields: dict) -> str:
    if fields.get("positions"):
        for p in fields["positions"]:
            p = (p or "").strip()
            if p and not is_unknown_position(p):
                return p
    title = (fields.get("vacancy_title") or "").strip()
    if title and not is_unknown_position(title):
        return title
    return ""


def _headline_context(fields: dict) -> str:
    parts = [
        fields.get("address") or "",
        fields.get("address_notes") or "",
        fields.get("notes") or "",
    ]
    return " ".join(p.strip() for p in parts if p and str(p).strip())


def _kazakh_locative(kz_dative: str) -> str:
    """Convert dative venue suffix to locative for multi-staff headline."""
    if kz_dative.endswith("іне"):
        return kz_dative[:-3] + "інде"
    if kz_dative.endswith("ына"):
        return kz_dative[:-3] + "ында"
    if kz_dative.endswith("не"):
        return kz_dative[:-2] + "де"
    if kz_dative.endswith("на"):
        return kz_dative[:-2] + "да"
    return kz_dative


def build_multi_staff_headline(
    company: str,
    language: DominantLanguage,
    context: str = "",
    poster_display: bool = False,
) -> str:
    """Multi-position summary: требуются сотрудники / қызметкерлер қажет."""
    blob = " ".join(x for x in (company, context) if x).strip()
    brand = _extract_brand(company)
    kz_suffix, ru_venue, include_brand = _detect_venue(blob)

    if language == "kazakh":
        if brand:
            loc = _kazakh_locative(kz_suffix)
            headline = f"{_guillemet_brand(brand)} {loc} қызметкерлер қажет"
        else:
            headline = "Қызметкерлер қажет"
    else:
        if include_brand and brand:
            headline = f"В {ru_venue} {_guillemet_brand(brand)} требуются сотрудники"
        else:
            headline = f"В {ru_venue} требуются сотрудники"

    if poster_display:
        return headline.upper()
    return headline


def build_multi_list_headline(
    company: str,
    positions: list[str],
    language: DominantLanguage,
    context: str = "",
    poster_display: bool = False,
) -> str:
    """Multi-position with bullet list under открыты вакансии / ашық вакансиялар."""
    blob = " ".join(x for x in (company, context) if x).strip()
    brand = _extract_brand(company)
    _, ru_venue, include_brand = _detect_venue(blob)

    if language == "kazakh":
        if brand:
            intro = f"{_guillemet_brand(brand)} ашық вакансиялар:"
        else:
            intro = "Ашық вакансиялар:"
    else:
        if include_brand and brand:
            intro = f"В {ru_venue} {_guillemet_brand(brand)} открыты вакансии:"
        else:
            intro = f"В {ru_venue} открыты вакансии:"

    bullets = "\n".join(f"• {p}" for p in positions)
    headline = f"{intro}\n{bullets}"
    if poster_display:
        return headline.upper()
    return headline


def build_multi_hiring_headline(
    company: str,
    language: DominantLanguage,
    context: str = "",
    poster_display: bool = False,
    variant: str = "open",
    fields: Optional[dict] = None,
) -> str:
    """
    MULTI_POSITION hiring headline with company.
    variant: 'open' → открыты вакансии / вакансиялар ашық
             'staff' → требуются сотрудники / бірнеше маман қажет
    """
    blob = _venue_blob_from_fields(fields) if fields else " ".join(x for x in (company, context) if x).strip()
    if not blob:
        blob = " ".join(x for x in (company, context) if x).strip()
    brand = _extract_brand(company)
    kz_suffix, ru_venue, include_brand = _detect_venue(blob)

    if language == "kazakh":
        if brand:
            if variant == "staff":
                headline = f"{_guillemet_brand(brand)} {kz_suffix} бірнеше маман қажет"
            else:
                headline = f"{_guillemet_brand(brand)} ұйымында вакансиялар ашық"
        else:
            headline = "Бірнеше маман қажет" if variant == "staff" else "Вакансиялар ашық"
    else:
        if brand:
            if variant == "staff":
                headline = f"В {_guillemet_brand(brand)} требуются сотрудники"
            else:
                headline = f"В {_guillemet_brand(brand)} открыты вакансии"
        else:
            headline = "Требуются сотрудники" if variant == "staff" else "Открыты вакансии"

    if poster_display:
        return headline.upper()
    return headline


def build_multi_positions_bullets(positions: list[str]) -> str:
    roles = valid_positions(positions)
    if not roles:
        return ""
    return "\n".join(roles)


def _capitalize_role_display(role: str) -> str:
    role = role.strip()
    if not role:
        return role
    if " " in role:
        parts = role.split()
        return " ".join(p[0].upper() + p[1:] if len(p) > 1 else p.upper() for p in parts)
    return role[0].upper() + role[1:] if len(role) > 1 else role.upper()


def has_position_groups(fields: dict) -> bool:
    groups = fields.get("position_groups") or []
    return len(groups) >= 2 and any((g.get("position") or "").strip() for g in groups)


def _group_dicts(fields: dict) -> list[dict]:
    groups = fields.get("position_groups") or []
    out = []
    for g in groups:
        if isinstance(g, dict):
            out.append(g)
        else:
            out.append(g.model_dump() if hasattr(g, "model_dump") else dict(g))
    return out


def build_position_groups_body(fields: dict, language: DominantLanguage) -> str:
    """Each position with its own requirements, salary, schedule — never merged."""
    groups = _group_dicts(fields)
    if len(groups) < 2:
        return ""

    req_label = "Талаптар:" if language == "kazakh" else "Требования:"
    resp_label = "Міндеттері:" if language == "kazakh" else "Обязанности:"
    cond_label = "Шарттары:" if language == "kazakh" else "Условия:"
    sal_label = "Жалақы:" if language == "kazakh" else "Оплата:"
    sched_label = "График:" if language == "russian" else "Кесте:"
    blocks: list[str] = []

    for g in groups:
        pos = (g.get("position") or "").strip()
        if not pos:
            continue
        blocks.append(_capitalize_role_display(pos))

        salary = (g.get("salary") or "").strip()
        if salary:
            blocks.append(f"{sal_label} {salary}")

        schedule = [s.strip() for s in (g.get("schedule") or []) if s.strip()]
        for item in schedule:
            blocks.append(f"{sched_label} {item}")

        reqs = [r.strip() for r in (g.get("requirements") or []) if r.strip()]
        if reqs:
            blocks.append(req_label)
            blocks.extend(f"• {r}" for r in reqs)

        resps = [r.strip() for r in (g.get("responsibilities") or []) if r.strip()]
        if resps:
            blocks.append(resp_label)
            blocks.extend(f"• {r}" for r in resps)

        conds = [c.strip() for c in (g.get("conditions") or []) if c.strip()]
        if conds:
            blocks.append(cond_label)
            blocks.extend(f"• {c}" for c in conds)

        blocks.append("")

    return "\n".join(blocks).strip()


def headline_covers_company(fields: dict, headline: str) -> bool:
    company = (fields.get("company") or "").strip()
    if not company or not headline:
        return False
    brand = _extract_brand(company)
    if brand and brand.lower() in headline.lower():
        return True
    return company.lower() in headline.lower()


def build_single_public_headline(
    fields: dict,
    language: DominantLanguage,
    poster_display: bool = False,
) -> str:
    """SINGLE_POSITION — company + venue + position + hiring action."""
    roles = valid_positions(fields.get("positions") or [])
    position = roles[0] if roles else primary_position(fields)
    company = fields.get("company") or ""
    ctx = _headline_context(fields)
    return build_hiring_headline(company, position, language, poster_display, ctx, fields=fields)


def build_multi_public_headline(
    fields: dict,
    language: DominantLanguage,
    poster_display: bool = False,
    variant: str = "open",
) -> str:
    """MULTI_POSITION hiring headline with company."""
    company = fields.get("company") or ""
    ctx = _headline_context(fields)
    return build_multi_hiring_headline(company, language, ctx, poster_display, variant, fields=fields)


def build_multi_positions_block(
    positions: list[str],
    language: DominantLanguage,
) -> str:
    """Bullet list of positions (simple multi, no grouped requirements)."""
    bullets = build_multi_positions_bullets(positions)
    if not bullets:
        return ""
    return bullets


def build_public_headline(
    fields: dict,
    language: DominantLanguage,
    poster_display: bool = False,
    multi_mode: str = "list",
) -> str:
    """
    Full public hiring headline for all outputs.
    multi_mode: 'list' adds positions or grouped blocks; 'headline' title only (poster PNG).
    """
    vacancy_type = fields.get("vacancy_type") or ""
    roles = valid_positions(fields.get("positions") or [])
    is_multi = vacancy_type == MULTI_POSITION or len(roles) >= 2

    if is_multi and len(roles) >= 2:
        headline = build_multi_public_headline(fields, language, poster_display)
        if multi_mode == "headline":
            return headline
        if has_position_groups(fields):
            body = build_position_groups_body(fields, language)
            return f"{headline}\n\n{body}" if body else headline
        bullets = build_multi_positions_bullets(roles)
        return f"{headline}\n\n{bullets}" if bullets else headline

    if len(roles) == 1:
        return build_single_public_headline(fields, language, poster_display)

    pos = primary_position(fields)
    if pos:
        return build_hiring_headline(
            fields.get("company") or "",
            pos,
            language,
            poster_display,
            _headline_context(fields),
            fields=fields,
        )
    return ""


def build_public_preamble(fields: dict, language: DominantLanguage) -> str:
    """Full opening block: headline + positions (or grouped blocks) for public outputs."""
    return build_public_headline(fields, language, poster_display=False, multi_mode="list")


def public_position_lines(fields: dict, language: DominantLanguage) -> list[str]:
    """Lines for vacancy section in messaging outputs."""
    vacancy_type = fields.get("vacancy_type") or ""
    roles = valid_positions(fields.get("positions") or [])
    is_multi = vacancy_type == MULTI_POSITION or len(roles) >= 2

    if is_multi and has_position_groups(fields):
        return build_position_groups_body(fields, language).split("\n")
    if is_multi and len(roles) >= 2:
        return roles
    if len(roles) == 1:
        return [build_single_public_headline(fields, language)]
    pos = primary_position(fields)
    if pos:
        return [build_single_public_headline(fields, language)]
    return []


def public_vacancy_section_label(fields: dict, language: DominantLanguage) -> str:
    """Section label for position block in Telegram/WhatsApp."""
    if has_position_groups(fields):
        return ""
    if is_multi_vacancy(fields.get("vacancy_type", ""), fields.get("positions")):
        return ""
    return "Лауазым:" if language == "kazakh" else "Должность:"


def skip_global_requirements(fields: dict) -> bool:
    """When position groups carry their own requirements, skip flat list."""
    return has_position_groups(fields)


def can_publish_public(fields: dict) -> bool:
    return has_valid_positions(fields.get("vacancy_title", ""), fields.get("positions"))
