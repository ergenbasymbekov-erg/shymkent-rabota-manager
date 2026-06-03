"""
Global Recruiter Reasoning Policy — understand first, extract second, format last.

Applies to parser, editor, review, validation, and deterministic extraction.
"""

import re
from typing import Optional

from position import valid_positions

RECRUITER_POLICY_CORE = """
GLOBAL RECRUITER REASONING POLICY

Think like an experienced recruiter. Read the vacancy and understand what job is offered.
Do not overthink. Do not reject real professions.

CORE RULE:
If a normal human can understand what job is offered, extract it as a position.

UNKNOWN_POSITION: last resort only when NO profession can be identified
(Қызметкер керек, Сотрудники требуются, Персонал нужен, Жұмысшы керек).
If at least one profession exists — UNKNOWN_POSITION is FORBIDDEN.

Gender words (қыз, девушка, парень, etc.) are NOT positions but must NOT delete the real job.

POSITION CONTEXT:
Salary, age, experience, schedule inline on the same line NEVER invalidate the position.

MULTI POSITION:
Multiple professions → separate positions. Never merge.

When unsure — keep the likely position and add manager warning.
Never destroy valid positions because of imperfect formatting.
Be practical. Be human. Preserve real jobs.
"""

UNCERTAINTY_WARNING_KZ = "RECRUITER: нақты бөлу белгісіз — менеджер тексеруі керек."
UNCERTAINTY_WARNING_RU = "RECRUITER: неясно к какой должности относится информация — требуется проверка менеджера."
MERGE_RISK_RU = "RECRUITER: риск смешивания требований между должностями — проверить position_groups."
MULTI_SHARED_REQ_RU = (
    "RECRUITER: общие требования при нескольких должностях — "
    "уточнить, относятся ли ко всем ролям или к одной."
)
MULTI_STRUCTURE_RU = (
    "RECRUITER: несколько должностей с отдельными условиями — "
    "проверить привязку к каждой роли."
)
MISSING_DETAIL_RU = "RECRUITER: для «{role}» не найдены детали — возможна потеря информации."
UNCLASSIFIED_RU = "RECRUITER: строка не привязана к должности: {line}"
NO_POSITIONS_RU = "RECRUITER: должности не извлечены — проверить текст вручную."

_SALARY_INLINE = re.compile(r"[—–-]\s*.*(?:тг|₸|тенге|\d+\s*000)", re.I)


def _profession_hint_in_raw(raw_text: str) -> bool:
    """True when raw text likely contains a profession (meaning-based, not hardcoded list)."""
    from profession import looks_like_profession, parse_position_line
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if parse_position_line(line) or looks_like_profession(line):
            return True
    return False


def _group_has_detail(group: dict) -> bool:
    return bool(
        (group.get("requirements") or [])
        or (group.get("salary") or "").strip()
        or (group.get("conditions") or [])
        or (group.get("responsibilities") or [])
        or (group.get("schedule") or [])
    )


def human_candidate_review(
    fields: dict,
    raw_text: str = "",
    reasoning: Optional[dict] = None,
    dominant: str = "kazakh",
) -> list[str]:
    """
    Human recruiter test — would a candidate understand the result?
    Returns manager warnings (never invents data).
    """
    warnings: list[str] = []
    reasoning = reasoning or {}
    positions = valid_positions(fields.get("positions") or [])
    groups = _normalize_groups(fields.get("position_groups") or [])
    flat_reqs = fields.get("requirements") or []

    if not positions and raw_text.strip() and _profession_hint_in_raw(raw_text):
        warnings.append(NO_POSITIONS_RU if dominant == "russian" else UNCERTAINTY_WARNING_KZ)

    if len(positions) >= 2 and flat_reqs and groups and any(_group_has_detail(g) for g in groups):
        warnings.append(MERGE_RISK_RU)

    if len(positions) >= 2 and flat_reqs and not groups:
        warnings.append(MULTI_SHARED_REQ_RU)

    if len(positions) >= 2 and not groups:
        inline_salaries = len(_SALARY_INLINE.findall(raw_text))
        colon_blocks = len(re.findall(r"^.+:\s*$", raw_text, re.M))
        if inline_salaries >= 2 or colon_blocks >= 2:
            warnings.append(MULTI_STRUCTURE_RU)

    for g in groups:
        if not _group_has_detail(g):
            warnings.append(MISSING_DETAIL_RU.format(role=g.get("position", "?")))

    for line in (reasoning.get("uncertain_lines") or [])[:5]:
        snippet = (line or "").strip()[:100]
        if snippet:
            warnings.append(UNCLASSIFIED_RU.format(line=snippet))

    for w in reasoning.get("warnings") or []:
        if w not in warnings:
            warnings.append(w)

    if reasoning.get("needs_manager_review") and not warnings:
        warnings.append(
            UNCERTAINTY_WARNING_RU if dominant == "russian" else UNCERTAINTY_WARNING_KZ
        )

    return warnings


def _normalize_groups(groups: list) -> list[dict]:
    out = []
    for g in groups:
        if isinstance(g, dict):
            out.append(g)
        elif hasattr(g, "model_dump"):
            out.append(g.model_dump())
    return out


def apply_manager_warnings(
    fields: dict,
    warnings: list[str],
) -> dict:
    """Append recruiter warnings to unsorted_review — never silent uncertainty."""
    out = dict(fields)
    if not warnings:
        return out
    review = list(out.get("unsorted_review") or [])
    for w in warnings:
        if w and w not in review:
            review.append(w)
    out["unsorted_review"] = review
    return out


def should_flag_manager_review(warnings: list[str]) -> bool:
    return bool(warnings)
