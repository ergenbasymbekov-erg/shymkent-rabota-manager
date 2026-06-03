"""
Human recruiter reasoning — position-first extraction with proximity logic.

Understand meaning, not keywords. See recruiter_policy.py for full policy.
"""

import re
from typing import Optional

from position import (
    POSITION_SECTION_HEADER_RE,
    _PHONE_LINE_RE,
    extract_positions_from_sections,
    extract_profession_from_hiring_line,
    is_invalid_job_title,
    valid_positions,
)
from profession import (
    display_profession,
    is_generic_staff,
    is_requirement_only_line,
    looks_like_profession,
    parse_position_line,
)

# ── Patterns ──────────────────────────────────────────────────────────────────

_SALARY_RE = re.compile(
    r"(жалақы|зарплат|оплат|salary|тг\b|тенге|₸|\d[\d\s]*(?:000|000)|келісімді)",
    re.I,
)
_SCHEDULE_FIELD_RE = re.compile(r"^(?:график|кесте|время\s+работы|жұмыс\s+уақыты)\s*:", re.I)
_SECTION_HEADER_RE = re.compile(
    r"^(?:"
    r"открытые\s+вакансии|открытые\s+вакансия|вакансии|вакансиялар|"
    r"условия|шарттар|контакты|байланыс|адрес|мекенжай|instagram|инстаграм|"
    r"требования|талаптар|обязанности|міндеттері|керек|қажет|требуются"
    r")\s*:?\s*(.*)$",
    re.I,
)
_INTRO_HIRING_RE = re.compile(
    r"^в\s+(?:заведение|ресторан|кафе|магазин|бар|club|кофейню|кофейня)\s+(.+?)\s+требуются\s*$",
    re.I,
)
_POSITION_COLON_RE = re.compile(r"^(.+?):\s*$")

_CONTACT_STOP_RE = re.compile(
    r"^(?:контакты|контакт|байланыс|тел|адрес|мекенжай|address|instagram|инстаграм)\s*:?\s*",
    re.I,
)

_SLASH_SPLIT_RE = re.compile(r"\s*/\s*")
_COMMA_LIST_RE = re.compile(r"\s*,\s*")


def _empty_group(position: str) -> dict:
    return {
        "position": position,
        "requirements": [],
        "responsibilities": [],
        "conditions": [],
        "salary": "",
        "schedule": [],
    }


def _normalize_position_key(name: str) -> str:
    n = (name or "").lower().strip().rstrip(":").strip()
    n = re.sub(r"\s+", " ", n)
    n = n.replace("универсалый", "универсальный")
    return n


def _canonical_display_name(name: str) -> str:
    key = _normalize_position_key(name)
    if "универсальный повар" in key:
        return "Универсальный повар"
    return display_profession(name)


def _is_section_header(line: str) -> bool:
    return bool(_SECTION_HEADER_RE.match(line.strip()))


def _is_intro_line(line: str) -> bool:
    return bool(_INTRO_HIRING_RE.match(line.strip()))


def _should_stop(line: str) -> bool:
    s = line.strip()
    if _PHONE_LINE_RE.match(s.replace(" ", "")) and len(re.sub(r"\D", "", s)) >= 10:
        return True
    if _CONTACT_STOP_RE.match(s):
        return True
    return False


def _split_multi_on_line(line: str) -> list[str]:
    """Повар / Официант / Кассир or Повар, официант, кассир → separate candidates."""
    if _SLASH_SPLIT_RE.search(line):
        parts = _SLASH_SPLIT_RE.split(line.strip())
        if 1 < len(parts) <= 8:
            return [p.strip() for p in parts if p.strip()]
    if "," in line:
        parts = [p.strip() for p in _COMMA_LIST_RE.split(line.strip()) if p.strip()]
        if 1 < len(parts) <= 8:
            professionish = sum(
                1 for p in parts
                if parse_position_line(p) or looks_like_profession(p)
            )
            if professionish >= 2:
                return parts
    return [line.strip()]


def _apply_parsed_to_group(g: dict, parsed: dict) -> None:
    if parsed.get("salary") and not g.get("salary"):
        g["salary"] = parsed["salary"]
    for q in parsed.get("requirements") or []:
        if q and q not in g["requirements"]:
            g["requirements"].append(q)


def _parse_position_colon_header(line: str) -> Optional[str]:
    m = _POSITION_COLON_RE.match(line.strip())
    if not m:
        return None
    title = m.group(1).strip()
    if _is_section_header(title + ":") or _is_section_header(title):
        return None
    if is_generic_staff(title):
        return None
    parsed = parse_position_line(title)
    if parsed:
        return parsed["position"]
    if looks_like_profession(title) and not is_invalid_job_title(title):
        return display_profession(title)
    return None


def _try_parse_profession_line(line: str) -> Optional[dict]:
    """Meaning-based profession parse — any valid occupation line."""
    for candidate in _split_multi_on_line(line):
        parsed = parse_position_line(candidate)
        if parsed:
            return parsed
        if looks_like_profession(candidate) and not is_generic_staff(candidate):
            return {"position": display_profession(candidate), "salary": "", "requirements": []}
    return None


def _groups_to_list(groups_map: dict) -> list[dict]:
    groups = []
    for g in groups_map.values():
        merged = dict(g)
        sched = merged.pop("schedule", [])
        for item in sched:
            if item not in merged["conditions"]:
                merged["conditions"].append(item)
        groups.append(merged)
    return groups


def extract_company_from_intro(raw_text: str) -> str:
    for line in raw_text.splitlines():
        m = _INTRO_HIRING_RE.match(line.strip())
        if m:
            return m.group(1).strip()
    return ""


def count_distinct_positions(raw_text: str) -> int:
    result = extract_with_recruiter_reasoning(raw_text)
    return len(result.get("positions") or [])


def extract_with_recruiter_reasoning(raw_text: str) -> dict:
    """
    Human-recruiter extraction — reconstruct structure from messy real text.

    Returns positions, position_groups, use_groups, global_conditions,
    global_requirements, company_hint, uncertain_lines, warnings.
    """
    empty = {
        "positions": [],
        "position_groups": [],
        "use_groups": False,
        "global_conditions": [],
        "global_requirements": [],
        "company_hint": "",
        "uncertain_lines": [],
        "warnings": [],
        "needs_manager_review": False,
    }
    if not raw_text or not raw_text.strip():
        return empty

    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    groups_map: dict[str, dict] = {}
    global_conditions: list[str] = []
    global_requirements: list[str] = []
    company_hint = extract_company_from_intro(raw_text)
    uncertain_lines: list[str] = []
    warnings: list[str] = []

    mode = "scan"  # scan | vacancy_list | global_conditions | global_requirements | position_detail
    current_key: Optional[str] = None
    classified_lines: set[str] = set()

    def ensure_group(name: str) -> str:
        key = _normalize_position_key(name)
        if key not in groups_map:
            groups_map[key] = _empty_group(_canonical_display_name(name))
        return key

    def _mark(line: str) -> None:
        classified_lines.add(line.strip())

    def _register_profession(parsed: dict, line: str) -> str:
        _mark(line)
        key = ensure_group(parsed["position"])
        _apply_parsed_to_group(groups_map[key], parsed)
        return key

    for line in lines:
        if _should_stop(line):
            break

        if _is_intro_line(line):
            _mark(line)
            continue

        hiring_prof = extract_profession_from_hiring_line(line)
        if hiring_prof:
            _mark(line)
            current_key = ensure_group(hiring_prof)
            mode = "position_detail"
            continue

        # Section headers
        sec = _SECTION_HEADER_RE.match(line)
        if sec:
            _mark(line)
            header = line.split(":")[0].strip().lower()
            if re.search(r"открыты|вакансии|вакансиялар|керек|қажет", header, re.I):
                mode = "vacancy_list"
                current_key = None
                inline = (sec.group(1) or "").strip()
                if inline:
                    for part in _split_multi_on_line(inline):
                        p = _try_parse_profession_line(part)
                        if p:
                            _register_profession(p, part)
                continue
            if re.search(r"условия|шарт", header, re.I):
                mode = "global_conditions"
                current_key = None
                inline = (sec.group(1) or "").strip()
                if inline:
                    global_conditions.append(inline)
                continue
            if re.search(r"требован|талап|обязан|міндет", header, re.I):
                mode = "global_requirements"
                current_key = None
                inline = (sec.group(1) or "").strip()
                if inline and not is_requirement_only_line(inline):
                    global_requirements.append(inline)
                elif inline:
                    global_requirements.append(inline)
                continue
            mode = "scan"
            current_key = None
            continue

        # Position block header: "Универсальный повар:"
        colon_role = _parse_position_colon_header(line)
        if colon_role:
            _mark(line)
            current_key = ensure_group(colon_role)
            mode = "position_detail"
            continue

        # Multi on one line: Повар / Официант / Кассир or Повар, официант, кассир
        multi_parts = _split_multi_on_line(line)
        if len(multi_parts) > 1 and mode in ("vacancy_list", "scan"):
            found_any = False
            for part in multi_parts:
                p = _try_parse_profession_line(part)
                if p:
                    _register_profession(p, part)
                    found_any = True
            if found_any:
                mode = "vacancy_list"
                continue

        # Profession line with context (salary, age, experience inline)
        if mode in ("vacancy_list", "scan", "position_detail"):
            parsed = _try_parse_profession_line(line)
            if parsed:
                current_key = _register_profession(parsed, line)
                if mode == "scan":
                    mode = "position_detail"
                elif mode == "vacancy_list":
                    mode = "vacancy_list"
                continue

        # Detail lines under position block (proximity)
        if mode == "position_detail" and current_key:
            if _SCHEDULE_FIELD_RE.match(line) or re.search(r"\d{1,2}/\d{1,2}|\d{1,2}:\d{2}", line):
                _mark(line)
                if line not in groups_map[current_key]["schedule"]:
                    groups_map[current_key]["schedule"].append(line)
                continue
            if _looks_like_requirement_line(line) or is_requirement_only_line(line):
                _mark(line)
                if line not in groups_map[current_key]["requirements"]:
                    groups_map[current_key]["requirements"].append(line)
                continue

        # Global requirements section
        if mode == "global_requirements":
            if line and not _is_section_header(line) and not _parse_position_colon_header(line):
                _mark(line)
                if line not in global_requirements:
                    global_requirements.append(line)
            continue

        # Global conditions section
        if mode == "global_conditions":
            if line and not _is_section_header(line) and not _parse_position_colon_header(line):
                _mark(line)
                if line not in global_conditions:
                    global_conditions.append(line)
            continue

        # Proximity: attach non-profession lines to current position
        if current_key and mode in ("scan", "position_detail"):
            is_new_profession = bool(_try_parse_profession_line(line))
            if not is_new_profession and (
                _looks_like_requirement_line(line)
                or is_requirement_only_line(line)
                or re.match(r"^категор(?:ии|ия)\s", line, re.I)
            ):
                _mark(line)
                if line not in groups_map[current_key]["requirements"]:
                    groups_map[current_key]["requirements"].append(line)
                continue

        if POSITION_SECTION_HEADER_RE.match(line):
            _mark(line)
            mode = "vacancy_list"
            continue

    _collect_uncertain_lines(lines, classified_lines, uncertain_lines, groups_map)

    def _result(**kwargs) -> dict:
        base = {
            "uncertain_lines": uncertain_lines,
            "warnings": warnings,
            "needs_manager_review": bool(uncertain_lines or warnings),
            "global_requirements": global_requirements,
        }
        base.update(kwargs)
        return base

    if not groups_map:
        section_roles = extract_positions_from_sections(raw_text)
        if section_roles:
            return _result(
                positions=valid_positions(section_roles),
                position_groups=[],
                use_groups=False,
                global_conditions=global_conditions,
                company_hint=company_hint,
            )
        # Last resort: scan all lines for professions
        for line in lines:
            if _should_stop(line) or _is_intro_line(line) or _is_section_header(line):
                continue
            for part in _split_multi_on_line(line):
                p = _try_parse_profession_line(part)
                if p:
                    key = ensure_group(p["position"])
                    _apply_parsed_to_group(groups_map[key], p)

    if not groups_map:
        return _result(
            positions=[],
            position_groups=[],
            use_groups=False,
            global_conditions=global_conditions,
            company_hint=company_hint,
        )

    groups = _groups_to_list(groups_map)
    positions = valid_positions([g["position"] for g in groups])

    def _has_data(g: dict) -> bool:
        return bool(
            g.get("requirements") or g.get("salary") or g.get("conditions")
            or g.get("responsibilities") or g.get("schedule")
        )

    use_groups = len(groups) >= 2 and any(_has_data(g) for g in groups)

    return _result(
        positions=positions,
        position_groups=groups if use_groups else [],
        use_groups=use_groups,
        global_conditions=global_conditions,
        company_hint=company_hint,
    )


def _collect_uncertain_lines(
    lines: list[str],
    classified: set[str],
    uncertain: list[str],
    groups_map: dict,
) -> None:
    if not groups_map:
        return
    noise = re.compile(
        r"^(?:@|tel|тел|whatsapp|wa\.me|https?://|\+\d|instagram|инстаграм)\b",
        re.I,
    )
    for line in lines:
        s = line.strip()
        if not s or s in classified:
            continue
        if _should_stop(s) or _is_intro_line(s):
            continue
        if _SECTION_HEADER_RE.match(s) or POSITION_SECTION_HEADER_RE.match(s):
            continue
        if len(s) < 5 or noise.match(s):
            continue
        if s not in uncertain:
            uncertain.append(s)
        if len(uncertain) >= 8:
            break


def _looks_like_requirement_line(line: str) -> bool:
    if is_requirement_only_line(line):
        return True
    if re.match(r"^категор(?:ии|ия)\s", line, re.I):
        return True
    if re.search(r"^(?:опыт|возраст|категория|от\s+\d+\s+лет)", line, re.I):
        return True
    if re.search(r"\(\s*от\s+\d+", line, re.I):
        return False
    return False


def extract_position_groups_from_raw(raw_text: str) -> list[dict]:
    result = extract_with_recruiter_reasoning(raw_text)
    if result.get("use_groups"):
        return result["position_groups"]
    return []
