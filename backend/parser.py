import json
import os
import re

from schema import PositionGroup, VacancyJSON
from prompt import SYSTEM_PROMPT
from position import valid_positions, roles_from_position_groups

try:
    from pipeline_debug import PipelineDebugger
except ImportError:
    PipelineDebugger = None  # type: ignore


def gpt_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def get_model() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


def require_api_key() -> None:
    if not gpt_configured():
        raise RuntimeError(
            "OPENAI_API_KEY is not set. "
            "Create ai_recruiter_v2/.env from .env.example and add your key."
        )


def _extract_json(text: str) -> dict:
    """Strip markdown fences from GPT response — not a vacancy parser."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _to_model(data: dict) -> VacancyJSON:
    pg_raw = data.get("position_groups") or []
    position_groups = [
        PositionGroup(**g) if isinstance(g, dict) else g for g in pg_raw
    ]
    positions = valid_positions(data.get("positions") or [])
    if not positions and position_groups:
        positions = roles_from_position_groups(position_groups)

    vt = data.get("vacancy_type", "SINGLE_POSITION")
    if vt in ("single", "SINGLE_POSITION"):
        vt = "SINGLE_POSITION"
    elif vt in ("multi", "MULTI_POSITION"):
        vt = "MULTI_POSITION"
    elif len(positions) >= 2:
        vt = "MULTI_POSITION"
    else:
        vt = "SINGLE_POSITION"

    return VacancyJSON(
        language=data.get("language", ""),
        company=data.get("company", ""),
        vacancy_type=vt,
        vacancy_title=data.get("vacancy_title", ""),
        positions=positions,
        position_groups=position_groups,
        salary=data.get("salary", ""),
        requirements=data.get("requirements") or [],
        responsibilities=data.get("responsibilities") or [],
        conditions=data.get("conditions") or [],
        phones=data.get("phones") or [],
        address=data.get("address", ""),
        address_notes=data.get("address_notes", ""),
        instagram=data.get("instagram", ""),
        notes=data.get("notes", ""),
        unsorted_review=data.get("unsorted_review") or [],
    )


async def parse_with_gpt(
    raw_text: str,
    debugger: "PipelineDebugger | None" = None,
) -> VacancyJSON:
    require_api_key()
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = get_model()
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": raw_text},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    raw_dict = _extract_json(content)
    if debugger and debugger.enabled:
        debugger.snap(
            "1_parser_gpt_raw",
            "parser.parse_with_gpt",
            {
                "vacancy_title": raw_dict.get("vacancy_title", ""),
                "positions": raw_dict.get("positions") or [],
                "position_groups": raw_dict.get("position_groups") or [],
            },
            note=f"GPT keys: {list(raw_dict.keys())}",
            raw_gpt=raw_dict,
        )
    data = _to_model(raw_dict)
    if debugger and debugger.enabled:
        debugger.snap(
            "2_parser_model",
            "parser._to_model",
            data.model_dump(),
            note="After VacancyJSON mapping (position_groups synced into positions[])",
        )
    return data


async def parse_vacancy(
    raw_text: str,
    debugger: "PipelineDebugger | None" = None,
) -> tuple[VacancyJSON, str]:
    data = await parse_with_gpt(raw_text, debugger=debugger)
    return data, get_model()
