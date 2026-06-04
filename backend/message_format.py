"""Format manager text for Telegram and WhatsApp — styling only, no rewriting.

DESIGNER MODE: preserve original line order and wording exactly.
Do not reorder, merge, split, move, or edit vacancy content.
Allowed changes only: formatting, emojis, bold, WhatsApp links, footer.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Optional

from language import DominantLanguage, detect_dominant_language
from phones import format_phone_display, normalize_phone_internal, process_phones
from schema import TelegramButton
from template_mode import is_phone_line, should_skip_line

PLATFORM_WA_URL = "https://wa.me/77763837171"
PLATFORM_PHONE_DISPLAY = "+7 776 383 7171"
TG_WA_LINK_LABEL = "💬 WhatsApp"
WA_LINK_MARKER = re.compile(r"\{\{WA:(https://wa\.me/\d+)\}\}")
ROLE_IN_PARENS_RE = re.compile(r"\(([^)]+)\)\s*$")

PLATFORM_BUTTONS = (
    ("🔥 ВАКАНСИЯ ЖАРИЯЛАУ", PLATFORM_WA_URL),
    ("Разместить своё объявление", PLATFORM_WA_URL),
)

TG_FOOTER_RULE = "────────────"
WA_FOOTER_RULE = "━━━━━━━━━━━━"
FOOTER_PROMOTION = "🔥 Өз хабарландыруыңызды орналастыру"

_GLOBAL_SECTIONS = frozenset({"contacts", "address", "instagram"})
_BODY_SECTIONS = frozenset({"requirements", "conditions", "responsibilities"})
_LABEL_VALUE_RE = re.compile(r"^[^:]{1,50}:\s*\S", re.UNICODE)
_REQ_HINT_RE = re.compile(
    r"(?:тәжірибе|тəжірибе|жауапкерш|ответствен|коммуник|жасы|график|жалақы|"
    r"опыт|треб|минимум|максимум|миндетті|обязательн|график)",
    re.I | re.UNICODE,
)
_VALUE_HIGHLIGHT_PATTERNS = (
    re.compile(
        r"^(.{0,48}?\b(?:жалақы|жалakы|зарплата|з\s*/\s*п|з\.?\s*п\.?|оплата|salary)\b\s*[:：]\s*)(.+)$",
        re.I | re.UNICODE,
    ),
    re.compile(
        r"^(.{0,48}?\bграфик\b\s*[:：]\s*)(.+)$",
        re.I | re.UNICODE,
    ),
    re.compile(
        r"^(.{0,48}?\b(?:жұмыс\s+уақыты|рабоч(?:ее|ие)\s+время|время\s+работы)\b\s*[:：]\s*)(.+)$",
        re.I | re.UNICODE,
    ),
)
_HIRING_SUFFIX_RE = re.compile(
    r"(\s+(?:қажет|керек|требуется|требуются|нужен|нужна|нужны))\s*$",
    re.I | re.UNICODE,
)
_VENUE_WORD_RE = re.compile(
    r"(?:іне|ина|ына|ге|ка|ye|сine|asy|ное|ную|ный|ная)$",
    re.I | re.UNICODE,
)

SECTION_MARKER = "◽️"
TG_SECTION_MARKER = "▫️"
INSTAGRAM_EMOJI = "📸"
TG_INSTAGRAM_EMOJI = "📱"

HEADERS_BY_LANG: dict[DominantLanguage, dict[str, str]] = {
    "kazakh": {
        "requirements": f"{SECTION_MARKER} Талаптар",
        "responsibilities": f"{SECTION_MARKER} Міндеттері",
        "conditions": f"{SECTION_MARKER} Шарттары",
        "contacts": f"{SECTION_MARKER} Байланыс",
        "address": f"{SECTION_MARKER} Мекенжай",
        "instagram": f"{SECTION_MARKER} Instagram",
    },
    "russian": {
        "requirements": f"{SECTION_MARKER} Требования",
        "responsibilities": f"{SECTION_MARKER} Обязанности",
        "conditions": f"{SECTION_MARKER} Условия",
        "contacts": f"{SECTION_MARKER} Контакты",
        "address": f"{SECTION_MARKER} Адрес",
        "instagram": f"{SECTION_MARKER} Instagram",
    },
}

TG_HEADERS_BY_LANG = HEADERS_BY_LANG
WA_HEADERS_BY_LANG = HEADERS_BY_LANG

# Words that mark the start of venue / hiring phrase — company name is everything before.
_VENUE_PHRASE_START = re.compile(
    r"\s+(?=(?:"
    r"фастфуд\b|"
    r"команд(?:а|асына)\b|"
    r"орталы(?:ğ|г|g)?(?:ы|ы)?(?:на|ға|ga)?\b|"
    r"мейрамхан(?:а|асына|asy)?\b|"
    r"дүкен(?:і|іне|ine|ine)?\b|"
    r"ресторан(?:ы|ына|ына)?\b|"
    r"кафе(?:сі|сіне|se|sine)?\b|"
    r"кофейня(?:сына)?\b|"
    r"кофехан(?:а|асына)?\b|"
    r"ұйым(?:ы|ына|y)?\b|"
    r"балабақша(?:сына)?\b|"
    r"аптека(?:сына)?\b|"
    r"магазин(?:а|е)?\b|"
    r"супермаркет(?:іне|і|е|а)?\b|"
    r"рестobar(?:ы|ына)?\b|"
    r"требу(?:ет|ются)\b|"
    r"ищ(?:ем|ут)\b"
    r"))",
    re.I | re.UNICODE,
)

_BRAND_TOKEN = re.compile(
    r"^(?:"
    r"[A-Za-z0-9][A-Za-z0-9&'.\-]*|"
    r"[А-ЯЁӘҒҚҢӨҰҮІ][А-ЯЁӘҒҚҢӨҰҮІa-zA-Z0-9\-]+|"
    r"[A-ZА-ЯЁӘҒҚҢӨҰҮІ]{2,}|"
    r"Shymkent|Almaty|Astana|Taraz|Turkestan"
    r")$",
    re.I | re.UNICODE,
)

_DESCRIPTOR_WORD = re.compile(
    r"^(?:"
    r"фастфуд|"
    r"команд(?:а|асына)|"
    r"орталы(?:ğ|г|g)?(?:ы)?(?:на|ға)?|"
    r"мейрамхан(?:а|асына)?|"
    r"дүкен(?:і|іне|ine)?|"
    r"ресторан(?:ы|ына)?|"
    r"кафе(?:сі|сіне)?|"
    r"кофейня(?:сына)?|"
    r"ұйым(?:ы|ына)?|"
    r"магазин(?:а|е)?|"
    r"требу(?:ет|ются)|"
    r"ищ(?:ем|ут)|"
    r"в\b|"
    r"на\b"
    r")$",
    re.I | re.UNICODE,
)

_QUOTED_BRAND = re.compile(r'^[«"\']([^»"\']+)[»"\']\s*(.*)$', re.DOTALL)

_KK_SECTION_MARKERS = (
    "талаптар", "шарттары", "байланыс", "мекенжай", "міндеттері", "жалақы", "қажет", "керек",
)
_RU_SECTION_MARKERS = (
    "требования", "условия", "контакты", "адрес", "обязанности", "зарплата", "требуется", "нужен",
)

SECTION_ALIASES: dict[str, set[str]] = {
    "vacancies": {
        "открытые вакансии", "ашық вакансиялар", "ашык вакансиялар",
        "вакансии", "вакансиялар", "ашық вакансиялар",
    },
    "requirements": {"требования", "талаптар"},
    "responsibilities": {"обязанности", "міндеттері", "миндеттері", "міндеттер"},
    "conditions": {
        "условия", "шарттары", "условия работы", "жұмыс шарттары", "жумыс шарттары",
        "зарплата", "жалақы", "жалакы", "оплата",
    },
    "contacts": {"контакты", "байланыс", "телефон", "phone", "contacts"},
    "address": {"адрес", "мекенжай", "мекен-жай", "address"},
    "instagram": {"instagram", "insta", "инстаграм"},
}

BULLET_RE = re.compile(r"^[\•\-\–\*✓]\s*")
PHONE_CHARS_RE = re.compile(r"[\d\s+\-()]+")
_PHONE_LABEL_RE = re.compile(
    r"^(?:номер|телефон|tel|phone|whatsapp|ватсап|whats)\s*[:：]\s*(.*)$",
    re.I | re.UNICODE,
)


def _norm_header(s: str) -> str:
    return s.strip().rstrip(":：").lower()


def header_section_key(line: str) -> Optional[str]:
    key = _norm_header(line)
    for section, aliases in SECTION_ALIASES.items():
        if key in aliases:
            return section
    return None


def detect_post_language(text: str) -> DominantLanguage:
    """Pick one language for all section headers — no mixing."""
    lower = text.lower()
    kk = sum(1 for m in _KK_SECTION_MARKERS if m in lower)
    ru = sum(1 for m in _RU_SECTION_MARKERS if m in lower)
    if kk > ru:
        return "kazakh"
    if ru > kk:
        return "russian"
    return detect_dominant_language(text)


def _tg_headers(lang: DominantLanguage) -> dict[str, str]:
    return TG_HEADERS_BY_LANG[lang]


def _wa_headers(lang: DominantLanguage) -> dict[str, str]:
    return WA_HEADERS_BY_LANG[lang]


def _tg_bold(text: str) -> str:
    return f"**{text}**"


def _wa_bold(text: str) -> str:
    return f"*{text}*"


def _tg_section_header(header: str) -> str:
    """▫️ Талаптар → ▫️ **Талаптар**"""
    label = header
    for marker in (TG_SECTION_MARKER, SECTION_MARKER):
        if header.startswith(marker):
            label = header[len(marker):].strip()
            break
    return f"{TG_SECTION_MARKER} {_tg_bold(label)}"


def _wa_section_header(header: str) -> str:
    label = header[len(SECTION_MARKER):].strip() if header.startswith(SECTION_MARKER) else header
    return f"{SECTION_MARKER} {_wa_bold(label)}"


def split_company_from_title(title: str) -> tuple[str, str]:
    """Return (company_name, rest_of_title) — wording preserved, no rewrite."""
    s = title.strip()
    if not s:
        return "", ""

    quoted = _QUOTED_BRAND.match(s)
    if quoted:
        company = quoted.group(1).strip()
        rest = quoted.group(2).strip()
        return company, rest

    venue = _VENUE_PHRASE_START.search(s)
    if venue and venue.start() > 0:
        return s[:venue.start()].strip(), s[venue.start():].strip()

    words = s.split()
    brand: list[str] = []
    for word in words:
        if _DESCRIPTOR_WORD.match(word):
            break
        if brand or _BRAND_TOKEN.match(word):
            brand.append(word)
        else:
            break

    if brand and len(brand) < len(words):
        return " ".join(brand), " ".join(words[len(brand):])

    if words and _BRAND_TOKEN.match(words[0]):
        return words[0], " ".join(words[1:])

    for i, word in enumerate(words):
        if i == 0:
            continue
        if _DESCRIPTOR_WORD.match(word) or re.match(
            r"^(?:кафе|кофейня|ресторан|дүкен|мейрамхана|магазин|орталы|супермаркет)", word, re.I
        ):
            company = " ".join(words[:i]).strip()
            rest = " ".join(words[i:]).strip()
            if company:
                return company, rest
            break

    return "", s


def _split_venue_and_position(middle: str) -> tuple[str, str]:
    """Split 'кафесіне ыдыс жуушы' → venue phrase + position phrase."""
    words = middle.split()
    if len(words) >= 2 and _VENUE_WORD_RE.search(words[0]):
        return words[0], " ".join(words[1:])
    return "", middle.strip()


def _format_title_line(title: str, *, tg: bool) -> str:
    """Bold company + position in title — preserve all original words."""
    bold = _tg_bold if tg else _wa_bold
    company, rest = split_company_from_title(title)
    if not company:
        return title

    suffix_match = _HIRING_SUFFIX_RE.search(rest)
    if not suffix_match:
        return f"{bold(company)} {rest}".strip()

    middle = rest[: suffix_match.start()].strip()
    suffix = suffix_match.group(1)  # includes leading space + qажет
    venue, position = _split_venue_and_position(middle)

    parts: list[str] = [bold(company)]
    if venue:
        parts.append(venue)
    if position:
        parts.append(bold(position))
    return " ".join(parts) + suffix


def _tg_title_block(title: str) -> str:
    return _format_title_line(title, tg=True)


def _wa_title_block(title: str) -> str:
    return _format_title_line(title, tg=False)


def _strip_bullet(line: str) -> str:
    """Remove list marker only — keep manager wording."""
    return BULLET_RE.sub("", line.strip()).strip()


def _highlight_key_values(text: str, *, tg: bool) -> str:
    """Bold salary / schedule / hours values only — labels and words unchanged."""
    bold_fn = _tg_bold if tg else _wa_bold
    for pattern in _VALUE_HIGHLIGHT_PATTERNS:
        match = pattern.match(text)
        if match:
            return match.group(1) + bold_fn(match.group(2).strip())
    return text


def _format_position_line(text: str, *, tg: bool) -> str:
    content = _strip_bullet(text)
    bold_fn = _tg_bold if tg else _wa_bold
    return f"✓ {bold_fn(content)}"


def _body_line(text: str, *, tg: bool = True) -> str:
    """Original wording + ✓ — bold salary/schedule/hours values only."""
    content = _strip_bullet(text)
    if not content:
        return ""
    content = _highlight_key_values(content, tg=tg)
    return f"✓ {content}"


def _check_line(text: str, *, tg: bool = True) -> str:
    return _body_line(text, tg=tg)


def _address_line(text: str) -> str:
    return f"📍 {_strip_bullet(text)}"


def _looks_like_position_line(line: str) -> bool:
    s = _strip_bullet(line).strip()
    if not s or should_skip_line(line):
        return False
    if header_section_key(line):
        return False
    if _line_has_phone(line):
        return False
    if _LABEL_VALUE_RE.match(s):
        return False
    if _REQ_HINT_RE.search(s):
        return False
    if len(s) > 90:
        return False
    return True


def _flush_block(blocks: list[PositionBlock], current: PositionBlock) -> PositionBlock:
    if (
        current.positions
        or current.requirements
        or current.responsibilities
        or current.conditions
    ):
        blocks.append(current)
        return PositionBlock()
    return current


def parse_vacancy_layout(text: str) -> VacancyLayout:
    """Parse manager text into title, per-position blocks, and shared footer sections."""
    layout = VacancyLayout()
    current = PositionBlock()
    phase: Optional[str] = None
    global_section: Optional[str] = None
    seen_phones: set[str] = set()

    for line in text.splitlines():
        if not line.strip() or should_skip_line(line):
            continue

        section_key = header_section_key(line)
        if section_key == "vacancies":
            continue

        if _line_has_phone(line):
            current = _flush_block(layout.blocks, current)
            global_section = "contacts"
            entry = _parse_phone_entry(line)
            if entry and entry.display not in seen_phones:
                seen_phones.add(entry.display)
                layout.phones.append(entry)
            continue

        if section_key in _GLOBAL_SECTIONS:
            current = _flush_block(layout.blocks, current)
            global_section = section_key
            phase = None
            continue

        if section_key in _BODY_SECTIONS:
            global_section = None
            phase = section_key
            continue

        if global_section == "contacts":
            continue
        if global_section == "address":
            layout.address.append(line)
            continue
        if global_section == "instagram":
            layout.instagram.append(line)
            continue

        if not layout.title:
            layout.title = line.strip()
            phase = "positions"
            continue

        if _looks_like_position_line(line):
            pos = _strip_bullet(line)
            if current.positions and (
                current.requirements or current.conditions or current.responsibilities
            ):
                current = _flush_block(layout.blocks, current)
            current.positions.append(pos)
            phase = "positions"
            continue

        if phase == "positions":
            if not current.positions:
                layout.extra.append(line)
            else:
                phase = "requirements"
                current.requirements.append(line)
            continue

        bucket = {
            "requirements": current.requirements,
            "conditions": current.conditions,
            "responsibilities": current.responsibilities,
        }.get(phase or "")
        if bucket is not None:
            bucket.append(line)
        elif phase == "positions" and not current.positions:
            layout.extra.append(line)
        else:
            layout.extra.append(line)

    _flush_block(layout.blocks, current)
    _split_multi_position_blocks(layout)

    if not layout.phones:
        for display in _collect_phone_displays(text):
            if display not in seen_phones:
                layout.phones.append(PhoneEntry(display=display))
                seen_phones.add(display)

    if not layout.blocks:
        parsed = parse_sections(text)
        title, positions = _split_hero(parsed.hero)
        if title and not layout.title:
            layout.title = title
        if positions:
            for pos in positions:
                layout.blocks.append(
                    PositionBlock(
                        positions=[pos],
                        requirements=list(parsed.requirements),
                        responsibilities=list(parsed.responsibilities),
                        conditions=list(parsed.conditions),
                    )
                )
        elif (
            parsed.requirements
            or parsed.responsibilities
            or parsed.conditions
        ):
            layout.blocks.append(
                PositionBlock(
                    requirements=parsed.requirements,
                    responsibilities=parsed.responsibilities,
                    conditions=parsed.conditions,
                )
            )
        if not layout.address:
            layout.address = parsed.address
        if not layout.instagram:
            layout.instagram = parsed.instagram
        if not layout.extra:
            layout.extra = parsed.extra

    return layout


def _split_multi_position_blocks(layout: VacancyLayout) -> None:
    """One position per block — duplicate shared sections when splitting."""
    split: list[PositionBlock] = []
    for block in layout.blocks:
        if len(block.positions) <= 1:
            split.append(block)
            continue
        for pos in block.positions:
            split.append(
                PositionBlock(
                    positions=[pos],
                    requirements=list(block.requirements),
                    responsibilities=list(block.responsibilities),
                    conditions=list(block.conditions),
                )
            )
    layout.blocks = split


def _phone_display(raw: str) -> str:
    internal, err = normalize_phone_internal(raw)
    if err or not internal:
        return raw.strip()
    return format_phone_display(internal)


def _wa_me_url(raw: str) -> str:
    internal, err = normalize_phone_internal(raw)
    if err or not internal:
        return ""
    return f"https://wa.me/7{internal[1:]}"


@dataclass
class PositionBlock:
    positions: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)


@dataclass
class VacancyLayout:
    title: str = ""
    blocks: list[PositionBlock] = field(default_factory=list)
    phones: list[PhoneEntry] = field(default_factory=list)
    address: list[str] = field(default_factory=list)
    instagram: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)


@dataclass
class PhoneEntry:
    display: str
    role: str = ""


@dataclass
class ParsedSections:
    hero: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    address: list[str] = field(default_factory=list)
    instagram: list[str] = field(default_factory=list)
    phones: list[PhoneEntry] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)


def _role_after_phone(line: str, display: str) -> str:
    """Text remaining on the line after the phone number."""
    s = line.strip()
    paren = ROLE_IN_PARENS_RE.search(s)
    if paren:
        return paren.group(1).strip()
    for chunk in PHONE_CHARS_RE.findall(s):
        digits = re.sub(r"\D", "", chunk)
        if len(digits) >= 10:
            s = s.replace(chunk, " ", 1)
    return " ".join(s.split()).strip(" -–—:,")


def _parse_phone_entry(line: str) -> Optional[PhoneEntry]:
    s = line.strip()
    if not s:
        return None

    phone_text = s
    label_match = _PHONE_LABEL_RE.match(s)
    if label_match:
        extracted = (label_match.group(1) or "").strip()
        if extracted:
            phone_text = extracted

    _, displays, _, _ = process_phones(raw_text=phone_text)
    if not displays:
        _, displays, _, _ = process_phones(raw_text=s)
    if displays:
        display = displays[0]
    else:
        internal, err = normalize_phone_internal(phone_text)
        if err or not internal:
            return None
        display = phone_text

    role = _role_after_phone(s, display)
    return PhoneEntry(display=display, role=role)


def _line_has_phone(line: str) -> bool:
    if is_phone_line(line.strip()):
        return True
    return bool(re.sub(r"\D", "", line)) and len(re.sub(r"\D", "", line)) >= 10


def _is_phone_label_only(line: str) -> bool:
    """Skip bare 'Номер:' / 'Телефон:' lines — no digits on the line."""
    match = _PHONE_LABEL_RE.match(line.strip())
    if not match:
        return False
    return len(re.sub(r"\D", "", match.group(1) or "")) < 10


def _tg_instagram_line(text: str) -> str:
    handle = text.strip()
    if handle and not handle.startswith("@"):
        handle = f"@{handle.lstrip('@')}"
    return f"{TG_INSTAGRAM_EMOJI} {handle}"


def parse_sections(text: str) -> ParsedSections:
    """Split manager text into sections — content words unchanged."""
    sections = ParsedSections()
    buckets = {
        "hero": sections.hero,
        "requirements": sections.requirements,
        "responsibilities": sections.responsibilities,
        "conditions": sections.conditions,
        "address": sections.address,
        "instagram": sections.instagram,
        "contacts": sections.extra,
    }
    current = "hero"
    seen_phones: set[str] = set()

    for line in text.splitlines():
        if not line.strip():
            continue
        if should_skip_line(line):
            continue

        section_key = header_section_key(line)
        if section_key:
            current = "hero" if section_key == "vacancies" else section_key
            continue

        if _line_has_phone(line):
            entry = _parse_phone_entry(line)
            if entry and entry.display not in seen_phones:
                seen_phones.add(entry.display)
                sections.phones.append(entry)
            continue

        if current == "contacts":
            continue

        buckets.get(current, sections.extra).append(line)

    if not sections.phones:
        for display in _collect_phone_displays(text):
            if display not in seen_phones:
                sections.phones.append(PhoneEntry(display=display))
                seen_phones.add(display)

    return sections


def _collect_phone_displays(text: str) -> list[str]:
    _, displays, _, _ = process_phones(raw_text=text)
    return displays


def _norm_line_key(s: str) -> str:
    return _strip_bullet(s).rstrip(":：").strip().lower()


def _filter_extra(
    extra: list[str],
    positions: list[str],
    phones: list[PhoneEntry],
) -> list[str]:
    """Drop lines already shown in the vacancy or contact sections."""
    known = {_norm_line_key(p) for p in positions}
    known.update(_norm_line_key(p.role) for p in phones if p.role)
    out: list[str] = []
    for ln in extra:
        key = _norm_line_key(ln)
        if not key or key in known:
            continue
        out.append(ln)
    return out


def _split_hero(hero: list[str]) -> tuple[str, list[str]]:
    lines = [ln.strip() for ln in hero if ln.strip() and not is_phone_line(ln)]
    if not lines:
        return "", []
    if len(lines) == 1:
        return lines[0], []
    return lines[0], lines[1:]


def _tg_body_section(header: str, body_lines: list[str]) -> str:
    body = [_body_line(ln) for ln in body_lines if ln.strip()]
    if not body:
        return ""
    return f"{_tg_section_header(header)}\n" + "\n".join(body)


def _wa_body_section(header: str, body_lines: list[str]) -> str:
    body = [_body_line(ln) for ln in body_lines if ln.strip()]
    if not body:
        return ""
    return f"{_wa_section_header(header)}\n" + "\n".join(body)


def _tg_address_section(header: str, body_lines: list[str]) -> str:
    body = [_address_line(ln) for ln in body_lines if ln.strip()]
    if not body:
        return ""
    return f"{_tg_section_header(header)}\n" + "\n".join(body)


def _wa_address_section(header: str, body_lines: list[str]) -> str:
    body = [_address_line(ln) for ln in body_lines if ln.strip()]
    if not body:
        return ""
    return f"{_wa_section_header(header)}\n" + "\n".join(body)


def _tg_position_block(block: PositionBlock, headers: dict[str, str]) -> str:
    parts: list[str] = []
    if block.positions:
        parts.append("\n".join(_tg_position_line(p) for p in block.positions))
    for key in ("requirements", "responsibilities", "conditions"):
        section = _tg_body_section(headers[key], getattr(block, key))
        if section:
            parts.append(section)
    return _join_blocks(parts)


def _wa_position_block(block: PositionBlock, headers: dict[str, str]) -> str:
    parts: list[str] = []
    if block.positions:
        parts.append("\n".join(_wa_position_line(p) for p in block.positions))
    for key in ("requirements", "responsibilities", "conditions"):
        section = _wa_body_section(headers[key], getattr(block, key))
        if section:
            parts.append(section)
    return _join_blocks(parts)


def _all_positions(layout: VacancyLayout) -> list[str]:
    out: list[str] = []
    for block in layout.blocks:
        out.extend(block.positions)
    return out


def _phone_contact_line(entry: PhoneEntry, multiple: bool) -> str:
    line = f"📞 {entry.display}"
    if multiple and entry.role:
        line = f"{line} ({entry.role})"
    return line


def _tg_contact_line(entry: PhoneEntry, multiple: bool, *, include_wa_links: bool) -> str:
    """One compact line: phone | WhatsApp link (Telegram HTML via marker)."""
    phone = f"📞 {entry.display}"
    if multiple and entry.role:
        phone = f"{phone} ({entry.role})"
    if include_wa_links:
        url = _wa_me_url(entry.display)
        if url:
            return f"{phone} | {{{{WA:{url}}}}}"
    return phone


def _tg_contacts(
    phones: list[PhoneEntry],
    headers: dict[str, str],
    *,
    include_wa_links: bool,
) -> str:
    if not phones:
        return ""
    multiple = len(phones) > 1
    lines = [_tg_section_header(headers["contacts"])]
    lines.extend(
        _tg_contact_line(entry, multiple, include_wa_links=include_wa_links)
        for entry in phones
    )
    return "\n".join(lines)


def _wa_contacts(phones: list[PhoneEntry], headers: dict[str, str]) -> str:
    if not phones:
        return ""
    multiple = len(phones) > 1
    lines = [_wa_section_header(headers["contacts"])]
    lines.extend(_phone_contact_line(entry, multiple) for entry in phones)
    return "\n".join(lines)


def _tg_instagram(lines: list[str], headers: dict[str, str]) -> str:
    body = [ln.strip() for ln in lines if ln.strip()]
    if not body:
        return ""
    return _tg_section_header(headers["instagram"]) + "\n" + "\n".join(
        f"📱 {ln.lstrip('@')}" for ln in body
    )


def _wa_instagram(lines: list[str], headers: dict[str, str]) -> str:
    body = [ln.strip() for ln in lines if ln.strip()]
    if not body:
        return ""
    return _wa_section_header(headers["instagram"]) + "\n" + "\n".join(
        f"📱 {ln.lstrip('@')}" for ln in body
    )


def _tg_footer() -> str:
    return f"{FOOTER_PROMOTION}\n\n📞 {PLATFORM_PHONE_DISPLAY}"


def _wa_footer() -> str:
    return ""


_PLATFORM_FOOTER_RE = re.compile(
    r"(?:хабарландыру|776\s*383\s*7171|77763837171|wa\.me/77763837171)",
    re.I | re.UNICODE,
)


def _strip_wa_platform_footer(text: str) -> str:
    """Remove platform promo footer lines from WhatsApp output (any code path)."""
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if stripped == FOOTER_PROMOTION:
            continue
        if stripped == f"📞 {PLATFORM_PHONE_DISPLAY}":
            continue
        if stripped == PLATFORM_PHONE_DISPLAY:
            continue
        if stripped == WA_FOOTER_RULE or stripped == TG_FOOTER_RULE:
            continue
        if _PLATFORM_FOOTER_RE.search(stripped):
            continue
        lines.append(line)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).strip()


def _join_blocks(blocks: list[str], gap: str = "\n\n") -> str:
    return gap.join(b for b in blocks if b.strip()).strip()


def _format_preserve_order(
    text: str,
    *,
    tg: bool,
    include_wa_links: bool,
) -> str:
    """Walk lines in original order — format each in place, append footer."""
    lang = detect_post_language(text)
    headers = _tg_headers(lang)

    out: list[str] = []
    first_content = True
    current_section: Optional[str] = None

    for line in text.splitlines():
        stripped = line.strip()

        if not stripped:
            out.append("")
            continue

        if should_skip_line(stripped):
            continue

        if _is_phone_label_only(stripped):
            continue

        section_key = header_section_key(line)
        if section_key == "vacancies":
            continue

        if section_key and section_key in headers:
            current_section = section_key
            header = headers[section_key]
            out.append(
                _tg_section_header(header) if tg else _wa_section_header(header)
            )
            first_content = False
            continue

        if _line_has_phone(stripped):
            entry = _parse_phone_entry(stripped)
            if entry:
                if tg:
                    out.append(
                        _tg_contact_line(
                            entry, False, include_wa_links=include_wa_links
                        )
                    )
                else:
                    out.append(_phone_contact_line(entry, False))
            else:
                out.append(stripped)
            first_content = False
            continue

        if first_content:
            out.append(
                _tg_title_block(stripped) if tg else _wa_title_block(stripped)
            )
            first_content = False
            continue

        if current_section == "instagram":
            if tg:
                out.append(_tg_instagram_line(stripped))
            else:
                out.append(f"{INSTAGRAM_EMOJI} {stripped.lstrip('@')}")
            continue

        if current_section == "address":
            out.append(_address_line(stripped))
            continue

        if current_section in ("requirements", "conditions", "responsibilities"):
            out.append(_body_line(stripped, tg=tg))
            continue

        if _looks_like_position_line(stripped):
            out.append(_format_position_line(stripped, tg=tg))
            continue

        out.append(_body_line(stripped, tg=tg))

    footer = _tg_footer() if tg else _wa_footer()
    if footer.strip():
        if out and out[-1] != "":
            out.append("")
        out.append(footer)
    return "\n".join(out).strip()


def _build_telegram(text: str, *, include_wa_links: bool) -> str:
    return _format_preserve_order(text, tg=True, include_wa_links=include_wa_links)


def telegram_text(text: str) -> str:
    """Telegram post — WhatsApp link under every phone number."""
    return _build_telegram(text, include_wa_links=True)


def telegram_preview_text(text: str) -> str:
    """Manager preview — same as channel format."""
    return telegram_text(text)


def whatsapp_text(text: str) -> str:
    """WhatsApp vacancy post — same order as source, formatting only."""
    return _strip_wa_platform_footer(
        _format_preserve_order(text, tg=False, include_wa_links=False)
    )


def build_telegram_buttons(text: str) -> list[TelegramButton]:
    """Platform inline buttons only."""
    return [TelegramButton(text=label, url=url) for label, url in PLATFORM_BUTTONS]


def _format_bold_html(segment: str) -> str:
    escaped = html.escape(segment)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)


def _render_telegram_line(line: str) -> str:
    """Convert **bold** and inline {{WA:url}} markers to Telegram HTML."""
    if not WA_LINK_MARKER.search(line):
        return _format_bold_html(line)
    parts: list[str] = []
    last = 0
    for match in WA_LINK_MARKER.finditer(line):
        parts.append(_format_bold_html(line[last:match.start()]))
        url = match.group(1)
        parts.append(f'<a href="{html.escape(url)}">{html.escape(TG_WA_LINK_LABEL)}</a>')
        last = match.end()
    parts.append(_format_bold_html(line[last:]))
    return "".join(parts)


def telegram_html(text: str) -> str:
    """Convert **bold** and WhatsApp link markers to Telegram HTML."""
    return "\n".join(_render_telegram_line(line) for line in text.splitlines())


def channel_inline_keyboard(text: str) -> list[list[TelegramButton]]:
    """Platform buttons — one per row at the bottom of the post."""
    return [[btn] for btn in build_telegram_buttons(text)]
