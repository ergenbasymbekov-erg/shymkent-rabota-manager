"""MVP rewrite — organize vacancy text → publication-ready outputs + poster PNG."""

import json
import os
import re

from parser import get_model, require_api_key
from preserve import preserve_full_outputs
from rewrite_prompt import REWRITE_SYSTEM_PROMPT
from poster_bridge import generate_poster_from_poster_text
from schema import RewriteOutputs, RewriteResponse

_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF"
    "\U0001F1E0-\U0001F1FF\U00002700-\U000027BF"
    "🔥📌📞✅⭐🚀💰📍☎️]+",
    flags=re.UNICODE,
)


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _strip_emojis(text: str) -> str:
    return _EMOJI_RE.sub("", text or "").strip()


async def rewrite_vacancy(raw_text: str) -> RewriteResponse:
    require_api_key()
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = get_model()
    source = raw_text.strip()

    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": source},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    data = _extract_json(content)

    clean_full = _strip_emojis((data.get("clean_full_text") or "").strip())
    telegram = _strip_emojis((data.get("telegram_text") or "").strip())
    whatsapp = _strip_emojis((data.get("whatsapp_text") or "").strip())
    poster = _strip_emojis((data.get("poster_text") or "").strip())

    clean_full, telegram, whatsapp = preserve_full_outputs(source, clean_full, telegram, whatsapp)

    outputs = RewriteOutputs(
        poster_text=poster,
        telegram_text=telegram,
        whatsapp_text=whatsapp,
    )

    png_url = ""
    png_filename = ""
    poster_error = ""
    poster_debug: dict = {}
    if outputs.poster_text:
        output_path, _, poster_error, poster_debug = generate_poster_from_poster_text(
            outputs.poster_text, source
        )
        if output_path:
            png_filename = output_path.name
            png_url = f"/posters/{png_filename}"

    return RewriteResponse(
        before=source,
        clean_full_text=clean_full,
        outputs=outputs,
        poster_png_url=png_url,
        poster_png_filename=png_filename,
        poster_error=poster_error,
        poster_debug=poster_debug,
        model=model,
    )
