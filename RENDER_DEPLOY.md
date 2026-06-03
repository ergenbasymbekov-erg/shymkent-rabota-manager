# Render deploy — 10 минут

## 1. GitHub

```bash
cd "/Users/erg/Desktop/second ai/ai_recruiter_v2"
# GitHub.com → New repository → имя: shymkent-rabota-manager (Private ұсынылады)
git remote add origin https://github.com/SIZIN_USER/shymkent-rabota-manager.git
git push -u origin main
```

## 2. Render.com

1. https://dashboard.render.com → **Sign Up** (GitHub арқылы)
2. **New +** → **Blueprint**
3. Репозиторийді таңдаңыз → `render.yaml` автоматты оқылады
4. **Environment** (қолмен толтырыңыз):

| Key | Value |
|-----|--------|
| `TELEGRAM_BOT_TOKEN` | BotFather токен |
| `MANAGER_WEB_KEY` | `shymkent-manager-2026` (немесе өзіңіздің ұзын код) |
| `OPENAI_API_KEY` | бос қалдыруға болады (веб жариялауға керек емес) |

5. **Apply** → deploy 3–5 мин

## 3. Телефон

Deploy соңғы URL: `https://shymkent-rabota-manager.onrender.com`

- Safari → закладка
- Кіру коды: `MANAGER_WEB_KEY` мәні

**Ескерту:** тегін план 15 мин өшпесе ұйықайды — бірінші ашу 30–60 сек болуы мүмкін.
