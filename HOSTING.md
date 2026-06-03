# Телефоннан жариялау — тегін хостинг (домен сатып алмай)

## Не аласыз

Телефонда браузер ашып сілтемеге кіресіз:

- вакансия мәтінін қоясыз  
- **Preview**  
- **Каналға жариялау** → `@Shymkent_Rabota_Job`

Бот компьютерде жүргізудің қажеті жоқ.

## Локальды тексеру (Mac)

```bash
cd ai_recruiter_v2
cp .env.example .env   # толтырыңыз
# .env ішіне қосыңыз:
# MANAGER_WEB_KEY=өзіңіздің-ұзын-кодыңыз

./run.sh
```

Телефон (бір Wi‑Fi): `http://<Mac-IP>:8790`  
Компьютер: `http://localhost:8790`

## Render.com (тегін, ұсынылады)

1. GitHub-қа жобаны жүктеңіз (немесе Render GitHub-қа қосыңыз).  
2. [render.com](https://render.com) → **New Web Service** → репозиторий.  
3. **Root Directory:** `ai_recruiter_v2`  
4. **Build:** `pip install -r requirements.txt`  
5. **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT --app-dir backend`  
6. **Environment variables:**

| Атау | Мән |
|------|-----|
| `TELEGRAM_BOT_TOKEN` | BotFather токені |
| `TELEGRAM_CHANNEL_ID` | `@Shymkent_Rabota_Job` |
| `MANAGER_WEB_KEY` | Құпия код (телефонда кіру үшін) |
| `FAST_TEXT_ONLY_MODE` | `true` (серверде постер шаблоны жоқ) |

7. Deploy соңында сілтеме: `https://shymkent-rabota-manager.onrender.com` (өз атауыңыз болады).

Телефонда осы сілтемені Safari/Chrome закладкаға салыңыз.

## Постер (PNG)

- **Тегін серверде** әдетте тек **мәтін** ( `FAST_TEXT_ONLY_MODE=true` ).  
- Постер керек болса — Mac-та бот (`./run_bot.sh`) немесе кейін серверге `maket 4` шаблонын қосу.

## Қауіпсіздік

- `MANAGER_WEB_KEY` — ұзын кездейсоқ сөз (мысалы 20+ таңба).  
- Бот токенін ешкімге жібермейді.
