import json
import re

from parser import get_model, require_api_key
from reviewer_prompt import REVIEWER_PROMPT
from schema import ReviewResult, VacancyJSON


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _to_result(data: dict) -> ReviewResult:
    verdict = data.get("verdict", "NEEDS_REVIEW")
    if verdict not in ("PASS", "NEEDS_REVIEW"):
        verdict = "NEEDS_REVIEW"

    score = data.get("score", 0)
    try:
        score = max(0, min(100, int(score)))
    except (TypeError, ValueError):
        score = 0

    if score < 90 and verdict == "PASS":
        verdict = "NEEDS_REVIEW"
    if score >= 90 and verdict == "NEEDS_REVIEW" and not data.get("issues"):
        verdict = "PASS"

    return ReviewResult(
        verdict=verdict,
        score=score,
        issues=data.get("issues") or [],
        recommendations=data.get("recommendations") or [],
    )


async def review_vacancy(raw_text: str, parsed: VacancyJSON) -> ReviewResult:
    require_api_key()
    from openai import AsyncOpenAI
    import os

    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = get_model()

    user_content = (
        "RAW TEXT:\n"
        f"{raw_text.strip()}\n\n"
        "PARSED JSON:\n"
        f"{json.dumps(parsed.model_dump(), ensure_ascii=False, indent=2)}"
    )

    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": REVIEWER_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    return _to_result(_extract_json(content))
