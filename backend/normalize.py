"""Full normalization pipeline: Parse → Editor → Quality → Review → Validation → Completeness."""

from editorial import normalize_fields_dict
from completeness import run_completeness_check
from editor import edit_vacancy, fields_to_vacancy
from language import detect_dominant_language, validate_output_language
from parser import get_model, parse_vacancy
from policy import apply_normalization_policy, preserve_from_source
from recruiter_policy import should_flag_manager_review
from position import (
    apply_raw_position_fallback,
    enforce_position_priority,
    position_unknown,
    resolve_vacancy_type,
    sync_positions_fields,
    validate_positions_list,
)
from quality import run_quality_check, _filter_missing_fields
from reviewer import review_vacancy
from schema import NormalizeResponse, PositionGroup, StructuredData
from sections import clean_after_text
from validation import run_global_validation
from unknown_trace import build_unknown_trace
from pipeline_debug import PipelineDebugger, snap_from_model


def to_structured(editor_fields) -> StructuredData:
    return StructuredData(
        company=editor_fields.company,
        vacancy_type=editor_fields.vacancy_type,
        vacancy_title=editor_fields.vacancy_title,
        positions=editor_fields.positions,
        position_groups=editor_fields.position_groups,
        salary=editor_fields.salary,
        address=editor_fields.address,
        address_notes=editor_fields.address_notes,
        phones=editor_fields.phones,
        phones_display=editor_fields.phones_display,
        instagram=editor_fields.instagram,
        requirements=editor_fields.requirements,
        responsibilities=editor_fields.responsibilities,
        conditions=editor_fields.conditions,
        notes=editor_fields.notes,
        unsorted_review=editor_fields.unsorted_review,
    )


async def normalize_vacancy(raw_text: str) -> NormalizeResponse:
    dbg = PipelineDebugger()
    parsed, _ = await parse_vacancy(raw_text, debugger=dbg)
    edited = await edit_vacancy(raw_text, parsed, debugger=dbg)
    dominant = detect_dominant_language(raw_text)

    # Merge parser + editor; sync positions[] from position_groups (GPT often omits flat list)
    merged_input = sync_positions_fields({
        **edited.fields.model_dump(),
        "positions": edited.fields.positions or parsed.positions,
        "position_groups": edited.fields.position_groups or parsed.position_groups,
    })
    edited.fields = edited.fields.model_copy(update=merged_input)
    dbg.snap("5a_sync_positions", "position.sync_positions_fields", edited.fields.model_dump())

    fallback_pre = apply_raw_position_fallback(edited.fields.model_dump(), raw_text, dominant)
    edited.fields = edited.fields.model_copy(update=fallback_pre)
    dbg.snap("5c_raw_fallback_pre", "position.apply_raw_position_fallback", edited.fields.model_dump())

    editor_snapshot = edited.fields.model_copy()
    snap_from_model(dbg, "5b_editor_snapshot", "editor.py", editor_snapshot, "Before validate_positions_list")

    pos_warnings: list[str] = []
    penalty = 0
    manager_review_reason = ""

    positions, _, pos_w, pos_p, _ = validate_positions_list(
        edited.fields.positions, raw_text, dominant
    )
    positions_after_validation = list(positions)
    dbg.snap(
        "6_validate_positions_list",
        "position.validate_positions_list",
        {"vacancy_title": edited.fields.vacancy_title, "positions": positions},
        note=f"in={edited.fields.positions!r}",
    )
    pos_warnings.extend(pos_w)
    penalty = max(penalty, pos_p)

    vacancy_type, vacancy_title, positions, pos_rr, pos_w2, pos_p2, mgr_reason = resolve_vacancy_type(
        positions,
        raw_text,
        dominant,
        edited.fields.vacancy_title,
    )
    pos_warnings.extend(w for w in pos_w2 if w not in pos_warnings)
    penalty = max(penalty, pos_p2)
    manager_review_reason = mgr_reason

    edited.fields.vacancy_type = vacancy_type
    edited.fields.vacancy_title = vacancy_title
    edited.fields.positions = positions
    dbg.snap(
        "7_resolve_vacancy_type",
        "position.resolve_vacancy_type",
        {"vacancy_title": vacancy_title, "positions": positions, "vacancy_type": vacancy_type},
    )

    review_required = pos_rr or edited.review_required

    merged = preserve_from_source(edited.fields.model_dump(), parsed.model_dump(), raw_text)
    merged = sync_positions_fields(merged)
    edited.fields = edited.fields.model_copy(update=merged)
    dbg.snap("8_preserve_from_source", "policy.preserve_from_source", edited.fields.model_dump())

    policy_fields = apply_normalization_policy(edited.fields.model_dump(), raw_text, dominant)
    policy_fields = sync_positions_fields(policy_fields)
    dbg.snap("9_apply_normalization_policy", "policy.apply_normalization_policy", policy_fields)
    pg_raw = policy_fields.get("position_groups") or []
    position_groups = [
        PositionGroup(**g) if isinstance(g, dict) else g for g in pg_raw
    ]
    edited.fields = edited.fields.model_copy(update={
        "vacancy_type": policy_fields["vacancy_type"],
        "vacancy_title": policy_fields["vacancy_title"],
        "positions": policy_fields["positions"],
        "position_groups": position_groups,
        "requirements": policy_fields.get("requirements", edited.fields.requirements),
        "responsibilities": policy_fields.get("responsibilities", edited.fields.responsibilities),
        "conditions": policy_fields.get("conditions", edited.fields.conditions),
        "salary": policy_fields.get("salary", edited.fields.salary),
        "unsorted_review": policy_fields.get("unsorted_review", edited.fields.unsorted_review),
    })
    dbg.snap("9b_after_policy_merge", "normalize.model_copy", edited.fields.model_dump())

    recruiter_warnings = policy_fields.get("unsorted_review") or []
    if should_flag_manager_review(recruiter_warnings):
        review_required = True
        if not manager_review_reason:
            manager_review_reason = recruiter_warnings[0]
        pos_warnings.extend(w for w in recruiter_warnings if w not in pos_warnings)

    fields_dict = normalize_fields_dict(edited.fields.model_dump(), dominant)
    fields_dict = sync_positions_fields({
        **fields_dict,
        "positions": fields_dict.get("positions") or policy_fields.get("positions") or positions,
    })
    dbg.snap("10_normalize_fields_dict", "editorial.normalize_fields_dict", fields_dict)
    fields_dict, had_invalid_unknown, invalid_warnings = enforce_position_priority(
        fields_dict, dominant
    )
    fields_dict = apply_raw_position_fallback(fields_dict, raw_text, dominant)
    dbg.snap("11_enforce_position_priority", "position.enforce_position_priority", fields_dict)
    if had_invalid_unknown:
        review_required = True
        pos_warnings.extend(w for w in invalid_warnings if w not in pos_warnings)
    edited.fields = edited.fields.model_copy(update={
        "vacancy_type": fields_dict.get("vacancy_type", vacancy_type),
        "vacancy_title": fields_dict.get("vacancy_title", vacancy_title),
        "positions": fields_dict.get("positions") or [],
        "position_groups": edited.fields.position_groups,
        "requirements": fields_dict.get("requirements", edited.fields.requirements),
        "conditions": fields_dict.get("conditions", edited.fields.conditions),
        "responsibilities": fields_dict.get("responsibilities", edited.fields.responsibilities),
    })
    edited.after = clean_after_text(edited.after, edited.fields.model_dump(), dominant)

    final_fields = apply_raw_position_fallback(edited.fields.model_dump(), raw_text, dominant)
    edited.fields = edited.fields.model_copy(update=final_fields)
    dbg.snap("12_raw_fallback_final", "position.apply_raw_position_fallback", edited.fields.model_dump())

    structured = to_structured(edited.fields)
    dbg.snap("13_structured_final", "normalize.to_structured", structured.model_dump())

    pre_validation = apply_raw_position_fallback(structured.model_dump(), raw_text, dominant)
    pg_pre = pre_validation.get("position_groups") or []
    structured = structured.model_copy(update={
        "vacancy_type": pre_validation.get("vacancy_type", structured.vacancy_type),
        "vacancy_title": pre_validation.get("vacancy_title", structured.vacancy_title),
        "positions": pre_validation.get("positions") or structured.positions,
        "position_groups": [
            PositionGroup(**g) if isinstance(g, dict) else g for g in pg_pre
        ] if pg_pre else structured.position_groups,
    })
    dbg.snap("13b_raw_fallback_pre_validation", "position.apply_raw_position_fallback", structured.model_dump())

    vacancy = fields_to_vacancy(edited.fields, parsed)
    dbg.snap(
        "14_fields_to_vacancy",
        "editor.fields_to_vacancy",
        vacancy.model_dump(),
        note="Used for review_vacancy — position_groups NOT copied to VacancyJSON",
    )

    quality = await run_quality_check(raw_text, edited.after, structured, debugger=dbg)
    review = await review_vacancy(raw_text, vacancy)

    validation = run_global_validation(
        raw_text=raw_text,
        after=edited.after,
        structured=structured,
        parsed_phones=parsed.phones,
        dominant=dominant,
    )
    dbg.snap(
        "16_validation",
        "validation.run_global_validation",
        {
            "vacancy_title": structured.vacancy_title,
            "positions": structured.positions,
        },
        note=f"unknown_position={validation.unknown_position}",
    )

    unknown_trace = build_unknown_trace(
        raw_text=raw_text,
        parsed=parsed,
        editor_fields=editor_snapshot,
        after_validate_positions=positions_after_validation,
        vacancy_type=vacancy_type,
        vacancy_title=vacancy_title,
        positions_after_resolve=positions,
        policy_fields=policy_fields,
        editorial_fields=fields_dict,
        structured=structured,
        validation_unknown=validation.unknown_position,
        dominant=dominant,
    )

    completeness = run_completeness_check(structured, validation)

    review_required = review_required or validation.review_required
    if completeness.status in ("REVIEW", "INCOMPLETE"):
        review_required = True
    can_approve = validation.can_approve and completeness.can_poster

    if review_required:
        quality.review_required = True
        quality.position_unknown = position_unknown(
            structured.vacancy_title, structured.positions
        )
        quality.confidence = max(0, quality.confidence - penalty)
        for w in pos_warnings:
            if w not in quality.warnings:
                quality.warnings.append(w)
        review.verdict = "NEEDS_REVIEW"
        if pos_warnings and pos_warnings[0] not in review.issues:
            review.issues.insert(0, pos_warnings[0])

    for w in validation.warnings:
        if w not in quality.warnings:
            quality.warnings.append(w)
    for w in completeness.warnings:
        if w not in quality.warnings:
            quality.warnings.append(w)
    for e in validation.errors:
        if e not in review.issues:
            review.issues.insert(0, e)

    lang_ok, lang_err = validate_output_language(dominant, edited.after, structured.model_dump())
    if not lang_ok and lang_err not in review.issues:
        review.issues.insert(0, lang_err)

    if review_required and manager_review_reason:
        if manager_review_reason not in review.issues:
            review.issues.insert(0, manager_review_reason)

    if unknown_trace.is_unknown and unknown_trace.unknown_reason:
        trace_msg = (
            f"UNKNOWN_POSITION: {unknown_trace.unknown_reason} "
            f"(module: {unknown_trace.assigned_by_module}, lost_at: {unknown_trace.lost_at_stage})"
        )
        if trace_msg not in review.issues:
            review.issues.insert(0, trace_msg)
        if unknown_trace.detail and unknown_trace.detail not in quality.warnings:
            quality.warnings.append(unknown_trace.detail)

    ui_state = {
        "structured_vacancy_title": structured.vacancy_title,
        "structured_positions": structured.positions,
        "quality_missing_fields": quality.missing_fields,
        "completeness_missing": completeness.missing,
        "validation_unknown_position": validation.unknown_position,
    }
    pipeline_debug = dbg.build(
        ui_state=ui_state,
        quality_missing_fields=quality.missing_fields,
        structured_positions=structured.positions,
        structured_title=structured.vacancy_title,
    )

    api_final = apply_raw_position_fallback(structured.model_dump(), raw_text, dominant)
    pg_api = api_final.get("position_groups") or []
    structured = structured.model_copy(update={
        "vacancy_type": api_final.get("vacancy_type", structured.vacancy_type),
        "vacancy_title": api_final.get("vacancy_title", structured.vacancy_title),
        "positions": api_final.get("positions") or structured.positions,
        "position_groups": [
            PositionGroup(**g) if isinstance(g, dict) else g for g in pg_api
        ] if pg_api else structured.position_groups,
    })
    quality.missing_fields = _filter_missing_fields(quality.missing_fields, structured)

    return NormalizeResponse(
        before=edited.before,
        after=edited.after,
        structured=structured,
        parsed=parsed,
        quality=quality,
        review=review,
        validation=validation,
        completeness=completeness,
        review_required=review_required,
        can_approve=can_approve,
        manager_review_reason=manager_review_reason if review_required else "",
        unknown_trace=unknown_trace,
        pipeline_debug=pipeline_debug,
        model=get_model(),
    )
