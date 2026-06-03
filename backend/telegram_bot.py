"""Telegram Manager Bot — preview vacancy outputs, publish to channel on confirm."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from db import VacancyStore, init_db
from db.connection import db_path
from message_format import channel_inline_keyboard, telegram_html
from schema import TelegramButton
from template_generate import fast_text_only_mode, generate_from_template

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _timing_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

CAPTION_LIMIT = 1024
CB_PUBLISH = "mgr_publish"
CB_CANCEL = "mgr_cancel"
ACCESS_DENIED = "⛔ Access denied"
OWNER_TEXT_ONLY = (
    "Мен тек мәтін қабылдаймын.\n"
    "Вакансияны жазып жіберіңіз (көшіру/жазу), сурет немесе дауыс емес.\n\n"
    "Команда: /start"
)


@dataclass
class PendingPost:
    vacancy_id: int
    source_text: str
    telegram_preview_text: str
    telegram_channel_text: str
    whatsapp_text: str
    channel_buttons: list[TelegramButton]
    png_path: Optional[Path]
    poster_warning: str = ""
    preview_message_ids: list[int] = field(default_factory=list)


def _store() -> VacancyStore:
    return VacancyStore()


def _telegram_request() -> HTTPXRequest:
    """Large poster PNGs (~1.6 MB) need a longer media upload timeout."""
    return HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
        media_write_timeout=120.0,
    )


async def _send_photo_retry(send_fn, png_path: Path, *, attempts: int = 2):
    """Retry Telegram photo upload (large PNGs can hit the default 20s limit)."""
    last_exc: Optional[BaseException] = None
    for attempt in range(attempts):
        try:
            with png_path.open("rb") as photo:
                return await send_fn(photo)
        except Exception as e:
            last_exc = e
            logger.warning("sendPhoto attempt %s failed: %s", attempt + 1, e)
            if attempt + 1 < attempts:
                await asyncio.sleep(2)
    if last_exc:
        raise last_exc
    raise RuntimeError("sendPhoto failed")


async def _reply_photo_retry(message, png_path: Path, *, attempts: int = 2):
    return await _send_photo_retry(message.reply_photo, png_path, attempts=attempts)


def _bot_token() -> str:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")
    return token


def _channel_id() -> str:
    channel = (os.environ.get("TELEGRAM_CHANNEL_ID") or "").strip()
    if not channel:
        raise RuntimeError("TELEGRAM_CHANNEL_ID is not set in .env")
    return channel


def _owner_user_id() -> int:
    raw = (os.environ.get("OWNER_USER_ID") or "").strip()
    if not raw:
        raise RuntimeError("OWNER_USER_ID is not set in .env")
    return int(raw)


def _is_owner(user_id: int) -> bool:
    return user_id == _owner_user_id()


async def _deny_access(update: Update, *, source: str) -> None:
    user = update.effective_user
    if not user:
        return
    logger.warning(
        "Unauthorized access attempt: user_id=%s username=%s source=%s",
        user.id,
        user.username or "",
        source,
    )
    if update.callback_query:
        await update.callback_query.answer(ACCESS_DENIED, show_alert=True)
    elif update.message:
        await update.message.reply_text(ACCESS_DENIED)


async def _guard_owner(update: Update, *, source: str) -> bool:
    """Return True when the update must be rejected (not the owner)."""
    if not update.effective_user:
        return True
    if _is_owner(update.effective_user.id):
        return False
    await _deny_access(update, source=source)
    return True


def _pending_from_stored(stored) -> PendingPost:
    return PendingPost(
        vacancy_id=stored.vacancy_id,
        source_text=stored.source_text,
        telegram_preview_text=stored.telegram_preview_text,
        telegram_channel_text=stored.telegram_channel_text,
        whatsapp_text=stored.whatsapp_text,
        channel_buttons=stored.channel_buttons,
        png_path=stored.png_path if stored.png_path and stored.png_path.is_file() else None,
        poster_warning=stored.poster_warning,
        preview_message_ids=stored.preview_message_ids,
    )


def _buttons_to_markup(rows: list[list[TelegramButton]]) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(btn.text, url=btn.url) for btn in row]
        for row in rows
    ]
    return InlineKeyboardMarkup(keyboard)


def _preview_actions_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Publish to Telegram", callback_data=CB_PUBLISH),
            InlineKeyboardButton("Cancel", callback_data=CB_CANCEL),
        ],
    ])


async def _clear_preview(context: ContextTypes.DEFAULT_TYPE, chat_id: int, pending: PendingPost) -> None:
    for msg_id in pending.preview_message_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            logger.debug("Could not delete preview message %s", msg_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if await _guard_owner(update, source="command:start"):
        return
    await update.message.reply_text(
        "Send the final approved vacancy text.\n\n"
        + (
            "I will generate a Telegram post preview.\n"
            "Then choose Publish to Telegram or Cancel.\n"
            if fast_text_only_mode()
            else "I will generate:\n"
            "• Poster PNG\n"
            "• Telegram post preview\n"
            "• Copy-ready messaging text\n\n"
            "Then choose Publish to Telegram or Cancel.\n"
        )
        + "/cancel — discard current preview\n"
        + "/stats — published vacancies count (database)\n"
        + "/ping — check bot is online and your Telegram ID"
    )


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if await _guard_owner(update, source="command:stats"):
        return
    user_id = update.effective_user.id
    count = await asyncio.to_thread(_store().count_published, user_id)
    await update.message.reply_text(
        f"Published vacancies in database: {count}\n"
        f"Storage: {db_path().resolve()}"
    )


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message:
        return
    if await _guard_owner(update, source="command:cancel"):
        return
    await _cancel_for_user(update, context, update.effective_user.id, update.message.chat_id)


async def _cancel_for_user(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
) -> None:
    stored = await asyncio.to_thread(_store().get_pending, user_id)
    if stored:
        pending = _pending_from_stored(stored)
        await _clear_preview(context, chat_id, pending)
        await asyncio.to_thread(_store().clear_pending, user_id)
    msg = update.message or update.callback_query.message
    if msg:
        await msg.reply_text("Cancelled.")


async def _reply_owner_error(update: Update, exc: BaseException) -> None:
    logger.exception("Handler failed: %s", exc)
    msg = update.message or (update.callback_query.message if update.callback_query else None)
    if msg:
        await msg.reply_text(
            f"Қате болды, қайта көріңіз.\n"
            f"Error: {type(exc).__name__}: {exc}"
        )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled bot error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_user and _is_owner(update.effective_user.id):
        try:
            await _reply_owner_error(update, context.error or RuntimeError("unknown"))
        except Exception:
            pass


async def ping_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if await _guard_owner(update, source="command:ping"):
        return
    uid = update.effective_user.id if update.effective_user else 0
    await update.message.reply_text(
        f"✅ Бот жұмыс істейді.\n"
        f"Сіздің Telegram ID: {uid}\n"
        f"Рұқсат берілген ID (.env): {_owner_user_id()}"
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user or not update.message or not update.message.text:
        return
    if await _guard_owner(update, source="message:text"):
        return
    user_id = update.effective_user.id
    chat_id = update.message.chat_id

    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Text is empty.")
        return

    total_t0 = time.perf_counter()
    logger.info("TIMING [1] message received user_id=%s at %s", user_id, _timing_ts())

    if fast_text_only_mode():
        ack_text = "⏳ Қабылданды, мәтін preview дайындау…"
    else:
        ack_text = "⏳ Қабылданды, постер + мәтін дайындау…"
    ack = await update.message.reply_text(ack_text)

    try:
        await _process_vacancy_text(update, context, user_id, chat_id, text, total_t0, ack_msg=ack)
    except Exception as e:
        if ack:
            try:
                await ack.delete()
            except Exception:
                pass
        await _reply_owner_error(update, e)


async def _process_vacancy_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    text: str,
    total_t0: float,
    *,
    ack_msg=None,
) -> None:

    old_stored = await asyncio.to_thread(_store().get_pending, user_id)
    if old_stored:
        await _clear_preview(context, chat_id, _pending_from_stored(old_stored))
        await asyncio.to_thread(_store().clear_pending, user_id)

    fast = fast_text_only_mode()
    status = None
    if not fast and not ack_msg:
        status = await update.message.reply_text("Generating…")
    result = await asyncio.to_thread(generate_from_template, text)

    if result.error and not fast and not result.poster_png_filename:
        if status:
            await status.edit_text(f"Error: {result.error}")
        else:
            await update.message.reply_text(f"Error: {result.error}")
        return

    png_path = None
    if not fast and result.poster_png_filename:
        png_path = ROOT / "posters" / "generated" / result.poster_png_filename

    vacancy_id = await asyncio.to_thread(
        _store().save_pending,
        user_id,
        source_text=result.source_text,
        telegram_preview_text=result.outputs.telegram_text,
        telegram_channel_text=result.outputs.telegram_text,
        whatsapp_text=result.outputs.whatsapp_text,
        channel_buttons=result.outputs.telegram_buttons,
        png_path=png_path if png_path and png_path.is_file() else None,
        poster_warning=result.poster_warning or "",
    )
    pending = PendingPost(
        vacancy_id=vacancy_id,
        source_text=result.source_text,
        telegram_preview_text=result.outputs.telegram_text,
        telegram_channel_text=result.outputs.telegram_text,
        whatsapp_text=result.outputs.whatsapp_text,
        channel_buttons=result.outputs.telegram_buttons,
        png_path=png_path if png_path and png_path.is_file() else None,
        poster_warning=result.poster_warning or "",
    )

    if status:
        await status.delete()
    if ack_msg:
        try:
            await ack_msg.delete()
        except Exception:
            pass
    preview_ids: list[int] = []

    if not fast and pending.png_path:
        logger.info("TIMING [4] sendPhoto starts at %s", _timing_ts())
        send_photo_t0 = time.perf_counter()
        photo_msg = await _reply_photo_retry(update.message, pending.png_path)
        send_photo_ms = (time.perf_counter() - send_photo_t0) * 1000
        logger.info(
            "TIMING [5] sendPhoto finishes at %s (%.1f ms)",
            _timing_ts(),
            send_photo_ms,
        )
        preview_ids.append(photo_msg.message_id)
    elif not fast and result.error:
        err_msg = await update.message.reply_text(f"Poster: {result.error}")
        preview_ids.append(err_msg.message_id)

    if not fast and pending.poster_warning:
        warn_msg = await update.message.reply_text(f"⚠ {pending.poster_warning}")
        preview_ids.append(warn_msg.message_id)

    tg_msg = await update.message.reply_text(
        f"<b>Telegram post preview</b>\n\n{telegram_html(pending.telegram_preview_text)}",
        parse_mode=ParseMode.HTML,
    )
    preview_ids.append(tg_msg.message_id)

    if not fast:
        wa_msg = await update.message.reply_text(pending.whatsapp_text)
        preview_ids.append(wa_msg.message_id)

    action_msg = await update.message.reply_text(
        "Ready to publish to the channel?",
        reply_markup=_preview_actions_markup(),
    )
    preview_ids.append(action_msg.message_id)
    pending.preview_message_ids = preview_ids
    await asyncio.to_thread(_store().update_preview_ids, vacancy_id, preview_ids)

    total_ms = (time.perf_counter() - total_t0) * 1000
    logger.info(
        "TIMING [6] total processing time: %.1f ms (finished at %s)",
        total_ms,
        _timing_ts(),
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data or not query.from_user:
        return
    if await _guard_owner(update, source="callback"):
        return
    await query.answer()

    user_id = query.from_user.id

    stored = await asyncio.to_thread(_store().get_pending, user_id)
    if not stored:
        await query.edit_message_text("No pending post. Send vacancy text again.")
        return
    pending = _pending_from_stored(stored)

    chat_id = query.message.chat_id if query.message else user_id

    if query.data == CB_CANCEL:
        await asyncio.to_thread(_store().clear_pending, user_id)
        await _clear_preview(context, chat_id, pending)
        if query.message:
            await query.message.edit_text("Cancelled.")
        return

    if query.data != CB_PUBLISH:
        return

    channel = _channel_id()
    caption_html = telegram_html(pending.telegram_channel_text)
    channel_markup = _buttons_to_markup(channel_inline_keyboard(pending.source_text))

    try:
        if not fast_text_only_mode() and pending.png_path:
            caption_fits = len(caption_html) <= CAPTION_LIMIT
            if caption_fits:
                await _send_photo_retry(
                    lambda photo: context.bot.send_photo(
                        chat_id=channel,
                        photo=photo,
                        caption=caption_html,
                        parse_mode=ParseMode.HTML,
                        reply_markup=channel_markup,
                    ),
                    pending.png_path,
                )
            else:
                await _send_photo_retry(
                    lambda photo: context.bot.send_photo(chat_id=channel, photo=photo),
                    pending.png_path,
                )
                await context.bot.send_message(
                    chat_id=channel,
                    text=caption_html,
                    parse_mode=ParseMode.HTML,
                    reply_markup=channel_markup,
                )
        else:
            await context.bot.send_message(
                chat_id=channel,
                text=caption_html,
                parse_mode=ParseMode.HTML,
                reply_markup=channel_markup,
            )
    except Exception as e:
        logger.exception("Publish failed")
        await query.edit_message_text(f"Publish failed: {e}")
        return

    await asyncio.to_thread(_store().mark_published, pending.vacancy_id)
    action_id = query.message.message_id if query.message else None
    pending.preview_message_ids = [
        mid for mid in pending.preview_message_ids if mid != action_id
    ]
    await _clear_preview(context, chat_id, pending)
    if query.message:
        await query.message.edit_text("Published to Telegram channel ✓")


async def on_other_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Photos/voice/etc. — tell owner to send plain text; deny others."""
    if not update.message or not update.effective_user:
        return
    if _is_owner(update.effective_user.id):
        await update.message.reply_text(OWNER_TEXT_ONLY)
        return
    await _deny_access(update, source="message:other")


async def on_other_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reject unknown commands from unauthorized users."""
    if not update.message:
        return
    if _is_owner(update.effective_user.id) if update.effective_user else False:
        return
    await _deny_access(update, source="command:other")


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    app = (
        Application.builder()
        .token(_bot_token())
        .request(_telegram_request())
        .build()
    )
    init_db()
    app.add_error_handler(on_error)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(filters.COMMAND, on_other_command))
    app.add_handler(MessageHandler(~filters.TEXT & ~filters.COMMAND, on_other_message))
    app.add_handler(CallbackQueryHandler(on_callback))

    owner_id = _owner_user_id()
    logger.info(
        "Manager bot started — channel %s owner %s fast_text_only=%s db=%s",
        _channel_id(),
        owner_id,
        fast_text_only_mode(),
        db_path(),
    )
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
