"""
Global Vacancy Normalization Policy — mandatory for all pipeline stages.

Mission: job-board organizer. Never invent. Never lose information.
"""

from typing import Optional

from position import (
    MULTI_POSITION,
    SINGLE_POSITION,
    UNKNOWN_POSITION,
    contains_critical_invalid_token,
    enforce_position_priority,
    extract_fallback_from_raw,
    extract_positions_from_raw,
    is_unknown_position,
    multi_vacancy_title,
    sync_positions_fields,
    valid_positions,
)
from recruiter_reasoning import extract_with_recruiter_reasoning
from recruiter_policy import (
    apply_manager_warnings,
    human_candidate_review,
)

PRESERVED_FIELDS = (
    "positions",
    "position_groups",
    "requirements",
    "responsibilities",
    "conditions",
    "salary",
    "address",
    "address_notes",
    "phones",
    "instagram",
    "notes",
)


def unknown_position_flag(
    positions: Optional[list] = None,
    position_groups: Optional[list] = None,
) -> bool:
    """UNKNOWN only when positions.length == 0 (including position_groups)."""
    if valid_positions(positions or []):
        return False
    if position_groups:
        group_roles = []
        for g in position_groups:
            pos = (g.get("position") if isinstance(g, dict) else getattr(g, "position", "")) or ""
            if pos.strip():
                group_roles.append(pos.strip())
        if valid_positions(group_roles):
            return False
    return True


def apply_normalization_policy(
    fields: dict,
    raw_text: str = "",
    dominant: str = "kazakh",
) -> dict:
    """
    Enforce SINGLE/MULTI classification, vacancy_title, and vacancy_type.
    Preserves position groups with separate requirements.
    """
    out = dict(fields)
    reasoning: dict = {}

    if raw_text:
        fb = extract_fallback_from_raw(raw_text)
        if fb.get("positions"):
            out["positions"] = fb["positions"]
            if fb.get("position_groups"):
                out["position_groups"] = fb["position_groups"]

        reasoning = extract_with_recruiter_reasoning(raw_text)
        if reasoning.get("positions") and not valid_positions(out.get("positions") or []):
            out["positions"] = reasoning["positions"]
        if reasoning.get("company_hint") and not (out.get("company") or "").strip():
            out["company"] = reasoning["company_hint"]
        if reasoning.get("global_conditions"):
            existing = list(out.get("conditions") or [])
            for c in reasoning["global_conditions"]:
                if c not in existing:
                    existing.append(c)
            out["conditions"] = existing
        if reasoning.get("global_requirements"):
            existing = list(out.get("requirements") or [])
            for r in reasoning["global_requirements"]:
                if r not in existing:
                    existing.append(r)
            if existing and not (reasoning.get("use_groups") and reasoning.get("position_groups")):
                out["requirements"] = existing
        if reasoning.get("use_groups") and reasoning.get("position_groups"):
            if not out.get("position_groups"):
                out["position_groups"] = reasoning["position_groups"]
                out["requirements"] = []
                out["responsibilities"] = []
                out["salary"] = ""
                if reasoning.get("global_conditions"):
                    out["conditions"] = list(reasoning["global_conditions"])

    groups = out.get("position_groups") or []

    roles = valid_positions(out.get("positions") or [])
    if not roles and raw_text:
        roles = valid_positions(extract_positions_from_raw(raw_text))
        if roles:
            out["positions"] = roles

    if groups:
        group_roles = [
            (g.get("position") if isinstance(g, dict) else g.position).strip()
            for g in groups
            if (g.get("position") if isinstance(g, dict) else g.position or "").strip()
        ]
        if group_roles:
            out["positions"] = valid_positions(group_roles)
            shared_conditions = list(out.get("conditions") or [])
            out["requirements"] = []
            out["responsibilities"] = []
            out["conditions"] = shared_conditions
            out["salary"] = ""
            roles = out["positions"]

    if len(roles) >= 2:
        out["vacancy_type"] = MULTI_POSITION
        out["vacancy_title"] = multi_vacancy_title(dominant)
        out["positions"] = roles
    elif len(roles) == 1:
        out["vacancy_type"] = SINGLE_POSITION
        out["vacancy_title"] = roles[0]
        out["positions"] = roles
    elif not roles:
        title = (out.get("vacancy_title") or "").strip()
        if (
            not title
            or is_unknown_position(title)
            or contains_critical_invalid_token(title)
        ):
            out["vacancy_title"] = UNKNOWN_POSITION

    out, _, _ = enforce_position_priority(out, dominant)

    recruiter_warnings = human_candidate_review(out, raw_text, reasoning, dominant)
    out = apply_manager_warnings(out, recruiter_warnings)

    return out


def preserve_from_source(target: dict, source: dict, raw_text: str = "") -> dict:
    """Never drop fields that exist in parser output unless truly empty in source."""
    out = dict(target)
    for key in PRESERVED_FIELDS:
        if key == "phones":
            if source.get("phones") and not out.get("phones"):
                out["phones"] = list(source["phones"])
            continue
        src_val = source.get(key)
        if src_val is None:
            continue
        if key == "position_groups":
            if src_val and not out.get(key):
                out[key] = list(src_val)
            continue
        if isinstance(src_val, list):
            if src_val and not out.get(key):
                out[key] = list(src_val)
        elif isinstance(src_val, str):
            if src_val.strip() and not (out.get(key) or "").strip():
                out[key] = src_val.strip()
    return sync_positions_fields(out)


def vacancy_title_present(fields: dict) -> bool:
    """vacancy_title is NOT missing when positions.length >= 1."""
    roles = valid_positions(fields.get("positions") or [])
    if roles:
        return True
    title = (fields.get("vacancy_title") or "").strip()
    return bool(title) and title.upper().replace(" ", "_") not in ("UNKNOWN", "UNKNOWN_POSITION")
