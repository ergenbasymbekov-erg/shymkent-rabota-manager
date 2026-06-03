import json
import re

from quality_prompt import QUALITY_PROMPT
from parser import get_model, require_api_key
from schema import QualityResult, StructuredData
from position import valid_positions, roles_from_position_groups


def _filter_missing_fields(missing: list, structured: StructuredData) -> list:
    """Drop false positives when structured JSON already has positions/title."""
    if not missing:
        return []
    listed = [p.strip() for p in (structured.positions or []) if (p or "").strip()]
    if len(listed) >= 1:
        return [
            field for field in missing
            if (field or "").strip().lower() not in ("positions", "vacancy_title")
        ]
    roles = valid_positions(structured.positions)
    if not roles:
        roles = roles_from_position_groups(structured.position_groups)
    title = (structured.vacancy_title or "").strip()
    out = []
    for field in missing:
        f = (field or "").strip().lower()
        if f == "positions" and roles:
            continue
        if f == "vacancy_title" and (title or roles):
            continue
        out.append(field)
    return out


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _to_result(data: dict) -> QualityResult:
    confidence = data.get("confidence", 0)
    try:
        confidence = max(0, min(100, int(confidence)))
    except (TypeError, ValueError):
        confidence = 0

    return QualityResult(
        confidence=confidence,
        information_lost=bool(data.get("information_lost")),
        information_duplicated=bool(data.get("information_duplicated")),
        information_invented=bool(data.get("information_invented")),
        mistakes_fixed=bool(data.get("mistakes_fixed", True)),
        vacancy_title_logical=bool(data.get("vacancy_title_logical", True)),
        company_logical=bool(data.get("company_logical", True)),
        editorial_clean=bool(data.get("editorial_clean", True)),
        language_preserved=bool(data.get("language_preserved", True)),
        missing_fields=data.get("missing_fields") or [],
        warnings=data.get("warnings") or [],
    )


async def run_quality_check(
    raw_text: str,
    after_text: str,
    structured: StructuredData,
    debugger=None,
) -> QualityResult:
    require_api_key()
    from openai import AsyncOpenAI
    import os

    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = get_model()

    user_content = (
        "RAW EMPLOYER TEXT:\n"
        f"{raw_text.strip()}\n\n"
        "CLEANED OFFICIAL TEXT:\n"
        f"{after_text.strip()}\n\n"
        "STRUCTURED JSON:\n"
        f"{json.dumps(structured.model_dump(), ensure_ascii=False, indent=2)}"
    )

    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": QUALITY_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    raw_q = _extract_json(content)
    result = _to_result(raw_q)
    result.missing_fields = _filter_missing_fields(result.missing_fields, structured)
    if debugger and getattr(debugger, "enabled", False):
        debugger.snap(
            "15_quality_gpt",
            "quality.run_quality_check",
            {
                "vacancy_title": structured.vacancy_title,
                "positions": structured.positions,
            },
            note=f"missing_fields={raw_q.get('missing_fields')!r} (UI shows this, not structured)",
            raw_gpt=raw_q,
        )
    return result
