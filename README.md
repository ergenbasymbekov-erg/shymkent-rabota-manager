# Shymkent Rabota — AI Recruiter v2

Production system for formatting job vacancy posts and publishing them to the **@Shymkent_Rabota_Job** Telegram channel via a private **Manager Bot**.

**Project path (Mac):**
```
/Users/erg/Desktop/second ai/ai_recruiter_v2
```

**Full handover documentation:** see [PROJECT_DOCUMENTATION.md](./PROJECT_DOCUMENTATION.md)

---

## What this project does

1. A **manager** (owner only) sends final approved vacancy text to the Manager Bot.
2. The bot generates:
   - **Telegram post** (formatted HTML with bold, emojis, WhatsApp links)
   - **WhatsApp copy** (plain text, same content order)
   - **Poster PNG** (manager text rendered onto a fixed banner template — optional via `FAST_TEXT_ONLY_MODE`)
3. The manager reviews a **preview** in Telegram and taps **Publish** or **Cancel**.
4. On publish, the formatted post goes to the public channel with platform inline buttons.

**Important:** The live Manager Bot uses **template mode** — no OpenAI calls. The manager's text is the source of truth; the system only applies formatting and layout.

---

## Quick start (Manager Bot)

```bash
cd "/Users/erg/Desktop/second ai/ai_recruiter_v2"
cp .env.example .env
# Edit .env — set TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, OWNER_USER_ID

chmod +x run_bot.sh
./run_bot.sh
```

Poster generation requires the external **maket 4** engine at `~/Desktop/maket 4` (or set `MAKET4_ROOT` in `.env`).

---

## Quick start (Web UI — optional)

Legacy/dev web interface for GPT parsing and template testing:

```bash
chmod +x run.sh
./run.sh
# Open http://localhost:8790
```

---

## Environment variables (minimum for bot)

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `TELEGRAM_CHANNEL_ID` | Yes | e.g. `@Shymkent_Rabota_Job` |
| `OWNER_USER_ID` | Yes | Your Telegram user ID (from @userinfobot) |
| `FAST_TEXT_ONLY_MODE` | No | `true` = skip poster/photo (fast preview); `false` = full mode |
| `MAKET4_ROOT` | No | Path to maket 4 folder (default: `~/Desktop/maket 4`) |

See [PROJECT_DOCUMENTATION.md § Configuration](./PROJECT_DOCUMENTATION.md#8-configuration) for all variables.

---

## Restart the bot

```bash
pkill -f "telegram_bot.py" 2>/dev/null || true
cd "/Users/erg/Desktop/second ai/ai_recruiter_v2"
./run_bot.sh
```

Confirm startup log:
```
Manager bot started — channel @Shymkent_Rabota_Job owner <id> fast_text_only=False
```

---

## Architecture (high level)

```
Manager Telegram message
        │
        ▼
telegram_bot.py (on_text)
        │
        ▼
template_generate.py (generate_from_template)
        ├── message_format.py  → Telegram + WhatsApp text
        └── text_poster.py     → PNG banner (if not FAST_TEXT_ONLY_MODE)
        │
        ▼
Preview in Telegram → Publish → Channel post
```

---

## Key files

| File | Purpose |
|------|---------|
| `backend/telegram_bot.py` | Manager Bot — preview, publish, security |
| `backend/template_generate.py` | Orchestrates text + poster generation |
| `backend/message_format.py` | Telegram/WhatsApp formatting (designer mode) |
| `backend/text_poster.py` | Renders text onto banner PNG |
| `backend/template_mode.py` | Line classification for poster styling |
| `backend/phones.py` | Phone normalization and display |
| `run_bot.sh` | Start Manager Bot |
| `run.sh` | Start FastAPI web UI |
| `.env` | Secrets and configuration |

---

## Folder structure

```
ai_recruiter_v2/
├── backend/           # All Python application code
├── frontend/          # Optional web UI (HTML/JS)
├── posters/generated/ # Output PNG files
├── samples/           # Test vacancy JSON
├── reports/           # Batch pipeline reports
├── run_bot.sh         # Start Manager Bot
├── run.sh             # Start web server
├── .env               # Local config (not in git)
└── PROJECT_DOCUMENTATION.md  # Full technical handover
```

---

## Security

- Only `OWNER_USER_ID` can use the Manager Bot.
- All other users receive `⛔ Access denied` and are logged.
- Same Telegram account works on all devices (iPhone, iPad, Mac).

---

## Modes

| Mode | Entry point | Uses GPT? |
|------|-------------|-----------|
| **Production (Manager Bot)** | `run_bot.sh` | No |
| **Template API** | `POST /api/generate` | No |
| **Legacy GPT pipeline** | `POST /api/parse`, `/api/normalize`, etc. | Yes |

---

## Backup checklist

- `.env` (tokens, owner ID)
- `backend/message_format.py` (formatting rules)
- `~/Desktop/maket 4/` (poster template + engine — separate folder)
- Optional: `posters/generated/` (not required; regenerated on each post)

---

## Support for new developers

Read in this order:

1. This README — orientation
2. [PROJECT_DOCUMENTATION.md](./PROJECT_DOCUMENTATION.md) — complete technical reference
3. `backend/telegram_bot.py` — live bot flow
4. `backend/message_format.py` — formatting rules

---

## License / external dependencies

- **python-telegram-bot** — Telegram Bot API
- **Pillow** — PNG rendering
- **maket 4 / shymkent_poster_engine** — external poster template engine (sibling project on Desktop)
