"""
UNKNOWN_POSITION pipeline tracer — shows where positions are lost and why.

Trace: RAW → PARSER → EDITOR → POSITION_VALIDATION → RESOLVE_TYPE → POLICY → EDITORIAL → VALIDATION → FINAL
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from position import (
    UNKNOWN_POSITION,
    contains_critical_invalid_token,
    extract_all_roles_from_raw,
    is_unknown_position,
    is_valid_role,
    valid_positions,
    validate_position,
)
from schema import EditorFields, PipelineStageTrace, UnknownTraceResult, StructuredData, VacancyJSON

logger = logging.getLogger("unknown_position")

UnknownReason = Literal[
    "",
    "generic_staff_word",
    "no_position_detected",
    "parser_failed",
    "editor_removed_position",
    "validation_rejected_position",
]

STAGE_ORDER = (
    "raw",
    "parser",
    "editor",
    "position_validation",
    "resolve_type",
    "policy",
    "editorial",
    "validation",
    "final",
)


def scan_raw_positions(raw_text: str) -> list[str]:
    """Deterministic pre-parser scan — what a recruiter would see in source text."""
    if not raw_text or not raw_text.strip():
        return []
    try:
        from recruiter_reasoning import extract_with_recruiter_reasoning
        result = extract_with_recruiter_reasoning(raw_text)
        roles = valid_positions(result.get("positions") or [])
        if roles:
            return roles
    except Exception:
        pass
    return valid_positions(extract_all_roles_from_raw(raw_text))


def _stage(
    stage: str,
    module: str,
    positions_raw: list,
    vacancy_title: str = "",
    note: str = "",
) -> PipelineStageTrace:
    raw = [str(p).strip() for p in (positions_raw or []) if str(p).strip()]
    return PipelineStageTrace(
        stage=stage,
        module=module,
        positions=valid_positions(raw),
        positions_raw=raw,
        vacancy_title=(vacancy_title or "").strip(),
        note=note,
    )


def _valid_count(positions: list) -> int:
    return len(valid_positions(positions or []))


def _first_unknown_stage(pipeline: list[PipelineStageTrace]) -> str:
    for s in pipeline:
        if is_unknown_position(s.vacancy_title):
            return s.stage
    return ""


def _find_lost_at_stage(pipeline: list[PipelineStageTrace]) -> str:
    prev_valid = None
    prev_stage = ""
    for s in pipeline:
        n = len(s.positions)
        if prev_valid is not None and prev_valid > 0 and n == 0:
            return s.stage
        if prev_valid is not None and prev_valid > n and n == 0:
            return s.stage
        prev_valid = n
        prev_stage = s.stage
    uk = _first_unknown_stage(pipeline)
    return uk or prev_stage or "final"


def _positions_before_unknown(pipeline: list[PipelineStageTrace], lost_at: str) -> list[str]:
    lost_idx = STAGE_ORDER.index(lost_at) if lost_at in STAGE_ORDER else len(STAGE_ORDER) - 1
    for i in range(lost_idx - 1, -1, -1):
        stage_name = STAGE_ORDER[i]
        for s in pipeline:
            if s.stage != stage_name:
                continue
            if s.positions:
                return list(s.positions)
            if s.positions_raw:
                return list(s.positions_raw)
    for s in pipeline:
        if s.positions:
            return list(s.positions)
    return []


def _has_generic_token(title: str, positions: list) -> bool:
    if (title or "").strip() and contains_critical_invalid_token(title):
        return True
    for p in positions or []:
        if (p or "").strip() and contains_critical_invalid_token(p):
            return True
    return False


def _validation_rejected_all(positions_raw: list, raw_text: str, dominant: str) -> bool:
    if not positions_raw:
        return False
    kept = 0
    for p in positions_raw:
        p = (p or "").strip()
        if not p:
            continue
        title, _, _, _, _ = validate_position(p, raw_text, dominant)
        if is_valid_role(title):
            kept += 1
    return kept == 0 and len([p for p in positions_raw if (p or "").strip()]) > 0


def classify_unknown_reason(
    raw_text: str,
    pipeline: list[PipelineStageTrace],
    parsed: VacancyJSON,
    editor_fields: EditorFields,
    dominant: str,
    final_unknown: bool,
) -> tuple[UnknownReason, str, str]:
    """
    Returns (unknown_reason, assigned_by_module, detail).
    """
    if not final_unknown:
        return "", "", ""

    raw_roles = next((s.positions for s in pipeline if s.stage == "raw"), [])
    parser_roles = valid_positions(parsed.positions or [])
    editor_roles = valid_positions(editor_fields.positions or [])
    editor_raw = [p.strip() for p in (editor_fields.positions or []) if (p or "").strip()]

    # Generic staff word — title or position contained forbidden token
    for s in pipeline:
        if _has_generic_token(s.vacancy_title, s.positions_raw):
            return (
                "generic_staff_word",
                s.module,
                f"Generic staff token in title={s.vacancy_title!r} or positions={s.positions_raw!r}",
            )
    if _has_generic_token(parsed.vacancy_title, parsed.positions):
        return (
            "generic_staff_word",
            "parser.py",
            f"Parser title={parsed.vacancy_title!r} positions={parsed.positions!r}",
        )

    # Editor removed positions that parser had
    if parser_roles and not editor_roles:
        removed = [p for p in parsed.positions if p.strip() and p not in editor_fields.positions]
        return (
            "editor_removed_position",
            "editor.py",
            f"Parser had {parser_roles!r}; editor output empty. Removed: {removed or parsed.positions!r}",
        )

    # Validation rejected all editor positions
    if editor_raw and _validation_rejected_all(editor_raw, raw_text, dominant):
        return (
            "validation_rejected_position",
            "position.validate_positions_list",
            f"Editor positions {editor_raw!r} rejected by validate_position()",
        )

    # Resolve/type step cleared positions
    val_stage = next((s for s in pipeline if s.stage == "position_validation"), None)
    resolve_stage = next((s for s in pipeline if s.stage == "resolve_type"), None)
    if val_stage and resolve_stage:
        if val_stage.positions and not resolve_stage.positions:
            if is_unknown_position(resolve_stage.vacancy_title):
                return (
                    "validation_rejected_position",
                    "position.resolve_vacancy_type",
                    f"resolve_vacancy_type cleared positions; title→{resolve_stage.vacancy_title!r}",
                )

    # Policy assigned UNKNOWN
    policy_stage = next((s for s in pipeline if s.stage == "policy"), None)
    if policy_stage and is_unknown_position(policy_stage.vacancy_title) and not policy_stage.positions:
        prev = _positions_before_unknown(pipeline, "policy")
        if prev:
            return (
                "validation_rejected_position",
                "policy.apply_normalization_policy",
                f"Policy set UNKNOWN; had positions before: {prev!r}",
            )

    # Parser failed — raw had roles but parser returned none
    if raw_roles and not parser_roles:
        return (
            "parser_failed",
            "parser.py",
            f"Raw scan found {raw_roles!r} but parser returned positions={parsed.positions!r} title={parsed.vacancy_title!r}",
        )

    # Editor set UNKNOWN explicitly
    if is_unknown_position(editor_fields.vacancy_title) and not editor_roles:
        return (
            "editor_removed_position",
            "editor.py",
            f"Editor set vacancy_title=UNKNOWN_POSITION; positions={editor_fields.positions!r}",
        )

    if is_unknown_position(parsed.vacancy_title) and not parser_roles:
        return (
            "parser_failed",
            "parser.py",
            f"Parser returned UNKNOWN_POSITION with no positions",
        )

    if not raw_roles:
        return (
            "no_position_detected",
            "position.resolve_vacancy_type",
            "No roles in raw text scan and no valid positions at any stage",
        )

    return (
        "no_position_detected",
        _first_unknown_stage(pipeline) or "final",
        "Positions lost — no single stage matched a specific reason",
    )


def build_unknown_trace(
    raw_text: str,
    parsed: VacancyJSON,
    editor_fields: EditorFields,
    after_validate_positions: list,
    vacancy_type: str,
    vacancy_title: str,
    positions_after_resolve: list,
    policy_fields: dict,
    editorial_fields: dict,
    structured: StructuredData,
    validation_unknown: bool,
    dominant: str = "kazakh",
) -> UnknownTraceResult:
    """Build full pipeline trace and classify UNKNOWN reason."""
    raw_roles = scan_raw_positions(raw_text)

    pipeline: list[PipelineStageTrace] = [
        _stage("raw", "recruiter_reasoning + position.extract_all_roles_from_raw", raw_roles,
               note=f"Deterministic scan: {len(raw_roles)} role(s)"),
        _stage("parser", "parser.parse_with_gpt", parsed.positions or [], parsed.vacancy_title,
               note=f"GPT parser: vacancy_type={parsed.vacancy_type}"),
        _stage("editor", "editor.edit_vacancy", editor_fields.positions or [], editor_fields.vacancy_title,
               note="GPT editor output (before validate_positions_list)"),
        _stage("position_validation", "position.validate_positions_list", after_validate_positions, vacancy_title,
               note="After validate_positions_list — invalid/generic roles removed"),
        _stage("resolve_type", "position.resolve_vacancy_type", positions_after_resolve, vacancy_title,
               note=f"vacancy_type={vacancy_type}"),
        _stage("policy", "policy.apply_normalization_policy",
               policy_fields.get("positions") or [], policy_fields.get("vacancy_title", ""),
               note="After recruiter reasoning + SINGLE/MULTI rules"),
        _stage("editorial", "editorial.normalize_fields_dict",
               editorial_fields.get("positions") or [], editorial_fields.get("vacancy_title", ""),
               note="Final field normalization"),
        _stage("validation", "validation.run_global_validation",
               structured.positions or [], structured.vacancy_title,
               note=f"unknown_position flag={validation_unknown}"),
        _stage("final", "normalize.to_structured",
               structured.positions or [], structured.vacancy_title,
               note="Structured output sent to review"),
    ]

    final_unknown = position_unknown_final(structured)
    lost_at = _find_lost_at_stage(pipeline) if final_unknown else ""
    positions_before = _positions_before_unknown(pipeline, lost_at) if final_unknown else []

    reason, assigned_by, detail = classify_unknown_reason(
        raw_text, pipeline, parsed, editor_fields, dominant, final_unknown
    )

    if final_unknown and not assigned_by:
        assigned_by = _module_for_stage(lost_at)

    trace = UnknownTraceResult(
        is_unknown=final_unknown,
        unknown_reason=reason,
        assigned_by_module=assigned_by,
        positions_before_unknown=positions_before,
        pipeline=pipeline,
        lost_at_stage=lost_at,
        detail=detail,
    )

    if final_unknown:
        logger.warning(
            "UNKNOWN_POSITION reason=%s module=%s lost_at=%s positions_before=%s detail=%s",
            reason,
            assigned_by,
            lost_at,
            positions_before,
            detail,
        )

    return trace


def position_unknown_final(structured: StructuredData) -> bool:
    from position import position_unknown
    return position_unknown(structured.vacancy_title, structured.positions)


def _module_for_stage(stage: str) -> str:
    mapping = {
        "raw": "recruiter_reasoning",
        "parser": "parser.py",
        "editor": "editor.py",
        "position_validation": "position.validate_positions_list",
        "resolve_type": "position.resolve_vacancy_type",
        "policy": "policy.apply_normalization_policy",
        "editorial": "editorial.normalize_fields_dict",
        "validation": "validation.run_global_validation",
        "final": "normalize.to_structured",
    }
    return mapping.get(stage, stage)
