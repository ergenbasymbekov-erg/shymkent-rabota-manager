"""Publish formatted vacancy to Telegram channel via Bot API (web / hosting)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import httpx

from message_format import channel_inline_keyboard, telegram_html
from schema import TelegramButton

CAPTION_LIMIT = 1024
_API = "https://api.telegram.org/bot{token}/{method}"


def _token() -> str:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return token


def _channel_id() -> str:
    channel = (os.environ.get("TELEGRAM_CHANNEL_ID") or "").strip()
    if not channel:
        raise RuntimeError("TELEGRAM_CHANNEL_ID is not set")
    return channel


def _inline_keyboard(rows: list[list[TelegramButton]]) -> dict:
    return {
        "inline_keyboard": [
            [{"text": btn.text, "url": btn.url} for btn in row]
            for row in rows
        ]
    }


async def publish_to_channel(
    *,
    source_text: str,
    telegram_text: str,
    png_path: Optional[Path] = None,
    timeout: float = 120.0,
) -> dict:
    """Send post to TELEGRAM_CHANNEL_ID. Returns Telegram API result dict."""
    token = _token()
    channel = _channel_id()
    caption_html = telegram_html(telegram_text)
    markup = _inline_keyboard(channel_inline_keyboard(source_text))

    async with httpx.AsyncClient(timeout=timeout) as client:
        if png_path and png_path.is_file():
            caption_fits = len(caption_html) <= CAPTION_LIMIT
            with png_path.open("rb") as photo_file:
                data = {
                    "chat_id": channel,
                    "parse_mode": "HTML",
                    "reply_markup": json.dumps(markup),
                }
                if caption_fits:
                    data["caption"] = caption_html
                files = {"photo": (png_path.name, photo_file, "image/png")}
                r = await client.post(
                    _API.format(token=token, method="sendPhoto"),
                    data=data,
                    files=files,
                )
            if not caption_fits:
                r2 = await client.post(
                    _API.format(token=token, method="sendMessage"),
                    json={
                        "chat_id": channel,
                        "text": caption_html,
                        "parse_mode": "HTML",
                        "reply_markup": markup,
                    },
                )
                r2.raise_for_status()
        else:
            r = await client.post(
                _API.format(token=token, method="sendMessage"),
                json={
                    "chat_id": channel,
                    "text": caption_html,
                    "parse_mode": "HTML",
                    "reply_markup": markup,
                },
            )
        r.raise_for_status()
        return r.json()
