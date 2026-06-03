import json
import os
import re

from editor_prompt import EDITOR_PROMPT, RETRY_PROMPT
from phones import process_phones
from sections import clean_after_text
from language import (
    detect_dominant_language,
    language_instruction,
    validate_neutral_style,
    validate_output_language,
)
from parser import get_model, require_api_key
from position import (
    enforce_position_priority,
    has_valid_positions,
    is_generic_position,
    is_unknown_position,
    sync_positions_fields,
    valid_positions,
    validate_position,
)
from schema import EditorFields, EditorResult, PositionGroup, VacancyJSON

try:
    from pipeline_debug import PipelineDebugger
except ImportError:
    PipelineDebugger = None  # type: ignore

MAX_EDITOR_RETRIES = 3

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF❤🔥⭐✨]+",
    flags=re.UNICODE,
)


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _strip_visual_markers(text: str) -> str:
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            lines.append("")
            continue
        line = re.sub(r"^\*\*(.+)\*\*$", r"\1", line)
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"^[\-\•\*—–]\s+", "", line)
        # Require . or ) after digits — avoids stripping "8708 2196801" phone numbers
        line = re.sub(r"^\d+[\.\)]\s+", "", line)
        line = line.replace("**", "").replace("*", "")
        line = EMOJI_RE.sub("", line)
        lines.append(line)
    out = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def _clean_list_items(items: list[str]) -> list[str]:
    return [_strip_visual_markers(i) for i in items if _strip_visual_markers(i)]


def _to_fields(data: dict) -> EditorFields:
    f = data.get("fields") or {}
    return EditorFields(
        company=f.get("company", ""),
        vacancy_type=f.get("vacancy_type", "SINGLE_POSITION"),
        vacancy_title=f.get("vacancy_title", ""),
        positions=_clean_list_items(f.get("positions") or []),
        position_groups=[
            PositionGroup(**g) if isinstance(g, dict) else g
            for g in (f.get("position_groups") or [])
        ],
        salary=f.get("salary", ""),
        requirements=_clean_list_items(f.get("requirements") or []),
        responsibilities=_clean_list_items(f.get("responsibilities") or []),
        conditions=_clean_list_items(f.get("conditions") or []),
        phones=f.get("phones") or [],
        phones_display=[],
        address=f.get("address", ""),
        address_notes=f.get("address_notes", ""),
        instagram=f.get("instagram", ""),
        notes=_strip_visual_markers(f.get("notes", "")),
        unsorted_review=_clean_list_items(f.get("unsorted_review") or []),
    )


def fields_to_vacancy(fields: EditorFields, parsed: VacancyJSON) -> VacancyJSON:
    vt = fields.vacancy_type or parsed.vacancy_type
    if vt in ("single", "SINGLE_POSITION"):
        vt = "SINGLE_POSITION"
    elif vt in ("multi", "MULTI_POSITION"):
        vt = "MULTI_POSITION"
    return VacancyJSON(
        language=parsed.language,
        company=fields.company,
        vacancy_type=vt,
        vacancy_title=fields.vacancy_title,
        positions=fields.positions,
        position_groups=fields.position_groups,
        salary=fields.salary,
        requirements=fields.requirements,
        responsibilities=fields.responsibilities,
        conditions=fields.conditions,
        phones=fields.phones,
        address=fields.address,
        address_notes=fields.address_notes,
        instagram=fields.instagram,
        notes=fields.notes,
        unsorted_review=fields.unsorted_review or parsed.unsorted_review,
    )


async def _call_editor(client, model: str, user_content: str, extra_system: str = "") -> dict:
    system = EDITOR_PROMPT
    if extra_system:
        system = system + "\n\n" + extra_system
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    return _extract_json(content)


async def edit_vacancy(
    raw_text: str,
    parsed: VacancyJSON,
    debugger: "PipelineDebugger | None" = None,
) -> EditorResult:
    require_api_key()
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = get_model()

    dominant = detect_dominant_language(raw_text)
    lang_label = "RUSSIAN" if dominant == "russian" else "KAZAKH"

    base_user = (
        language_instruction(dominant)
        + "\nRAW CLIENT TEXT:\n"
        + raw_text.strip()
        + "\n\nPARSED JSON:\n"
        + json.dumps(parsed.model_dump(), ensure_ascii=False, indent=2)
    )

    result = None
    after = ""
    fields_dict: dict = {}
    last_error = ""

    for attempt in range(MAX_EDITOR_RETRIES):
        extra = ""
        if attempt > 0:
            extra = RETRY_PROMPT.format(language=lang_label) + f"\n\nPREVIOUS ERROR: {last_error}"

        result = await _call_editor(client, model, base_user, extra)
        if debugger and debugger.enabled:
            fields_raw = result.get("fields") or {}
            debugger.snap(
                "3_editor_gpt_raw",
                "editor._call_editor",
                {
                    "vacancy_title": fields_raw.get("vacancy_title", ""),
                    "positions": fields_raw.get("positions") or [],
                    "position_groups": fields_raw.get("position_groups") or [],
                },
                note=f"GPT editor keys: {list(result.keys())}",
                raw_gpt=result,
            )
        fields = _to_fields(result)
        fields_dict = sync_positions_fields(fields.model_dump())
        fields = fields.model_copy(update=fields_dict)
        if debugger and debugger.enabled:
            debugger.snap(
                "4_editor_fields",
                "editor._to_fields",
                fields.model_dump(),
                note="After _clean_list_items on positions",
            )
        internals, displays, phone_error, phone_msgs = process_phones(
            fields.phones, parsed.phones, raw_text
        )
        fields.phones = internals
        fields.phones_display = displays
        fields_dict = fields.model_dump()
        after_raw = _strip_visual_markers(result.get("after", ""))
        after = clean_after_text(after_raw, fields_dict, dominant)

        ok, err = validate_output_language(dominant, after, fields_dict)
        if ok:
            ok, err = validate_neutral_style(after, fields_dict)
        rr = False
        if ok and is_generic_position(fields.vacancy_title):
            if not has_valid_positions("", fields.positions):
                ok, err = False, f"POSITION_ERROR: generic title '{fields.vacancy_title}'"
        if ok and has_valid_positions("", fields.positions):
            if len(valid_positions(fields.positions)) == 1:
                fields.vacancy_title = valid_positions(fields.positions)[0]
            fields_dict["vacancy_title"] = fields.vacancy_title
        elif ok:
            title, rr, _, _, _ = validate_position(fields.vacancy_title, raw_text, dominant)
            fields.vacancy_title = title
            fields_dict["vacancy_title"] = title
        if ok:
            after = clean_after_text(after_raw, fields_dict, dominant)
            fields_dict, _, _ = enforce_position_priority(fields_dict, dominant)
            fields = fields.model_copy(update={
                "vacancy_type": fields_dict.get("vacancy_type", fields.vacancy_type),
                "vacancy_title": fields_dict.get("vacancy_title", fields.vacancy_title),
                "positions": fields_dict.get("positions", fields.positions),
            })
            if debugger and debugger.enabled:
                debugger.snap(
                    "5_editor_final",
                    "editor.edit_vacancy",
                    fields.model_dump(),
                    note="After validate_position + enforce_position_priority",
                )
            if is_unknown_position(fields.vacancy_title) and not has_valid_positions("", fields.positions):
                result["review_required"] = True
            review_required = result.get("review_required", False) or rr
            return EditorResult(
                before=raw_text.strip(),
                after=after,
                fields=fields,
                review_required=review_required,
            )

        last_error = err

    raise RuntimeError(
        f"EDITOR_ERROR after {MAX_EDITOR_RETRIES} attempts: {last_error}. "
        f"Dominant language was {dominant}."
    )
