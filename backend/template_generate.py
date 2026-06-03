"""Template mode — generate poster + messaging from final manager text."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime

from schema import TemplateGenerateResponse, TemplateOutputs
from message_format import build_telegram_buttons, telegram_html, telegram_text, whatsapp_text
from text_poster import generate_text_poster

logger = logging.getLogger(__name__)


def _timing_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def fast_text_only_mode() -> bool:
    raw = os.environ.get("FAST_TEXT_ONLY_MODE", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def generate_from_template(text: str) -> TemplateGenerateResponse:
    """No AI. Manager text is the source of truth."""
    source = text  # preserve exactly — only reject if entirely whitespace
    if not source.strip():
        return TemplateGenerateResponse(
            error="Text is empty",
            source_text=source,
        )

    tg = telegram_text(source)
    wa = whatsapp_text(source)
    buttons = build_telegram_buttons(source)

    if fast_text_only_mode():
        logger.info("FAST_TEXT_ONLY_MODE: poster generation skipped")
        return TemplateGenerateResponse(
            source_text=source,
            outputs=TemplateOutputs(
                telegram_text=tg,
                whatsapp_text=wa,
                telegram_buttons=buttons,
            ),
            telegram_html=telegram_html(tg),
        )

    try:
        logger.info("TIMING [2] poster generation starts at %s", _timing_ts())
        poster_t0 = time.perf_counter()
        png_path, warning, _debug = generate_text_poster(source)
        poster_ms = (time.perf_counter() - poster_t0) * 1000
        logger.info(
            "TIMING [3] poster generation finishes at %s (%.1f ms)",
            _timing_ts(),
            poster_ms,
        )
    except FileNotFoundError as e:
        return TemplateGenerateResponse(
            error=str(e),
            source_text=source,
            outputs=TemplateOutputs(telegram_text=tg, whatsapp_text=wa, telegram_buttons=buttons),
            telegram_html=telegram_html(tg),
        )

    png_url = ""
    png_filename = ""
    if png_path:
        png_url = f"/posters/{png_path.name}"
        png_filename = png_path.name

    return TemplateGenerateResponse(
        source_text=source,
        outputs=TemplateOutputs(
            telegram_text=tg,
            whatsapp_text=wa,
            telegram_buttons=buttons,
        ),
        telegram_html=telegram_html(tg),
        poster_png_url=png_url,
        poster_png_filename=png_filename,
        poster_warning=warning,
        error="" if png_path else (warning or "Poster generation failed"),
    )
