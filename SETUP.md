# AI Recruiter v2 — Setup (macOS)

GPT-only parser. No fallback. No regex parser.

## 1. Where `OPENAI_API_KEY` is configured

Create this file:

```
/Users/erg/Desktop/second ai/ai_recruiter_v2/.env
```

It is loaded automatically by `backend/main.py`:

```python
load_dotenv(ROOT / ".env")
```

The key is read in `backend/parser.py`:

```python
os.environ["OPENAI_API_KEY"]
```

## 2. Exact macOS commands

```bash
# Go to project
cd "/Users/erg/Desktop/second ai/ai_recruiter_v2"

# Create .env from template
cp .env.example .env

# Edit .env — paste your OpenAI key
nano .env
```

In `.env`, set:

```
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxx
OPENAI_MODEL=gpt-4o-mini
PORT=8790
```

Save in nano: `Ctrl+O`, Enter, `Ctrl+X`

```bash
# First-time install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
chmod +x run.sh

# Start server
./run.sh
```

Open: **http://localhost:8790**

## 3. Verify GPT is connected

```bash
curl http://localhost:8790/api/health
```

Expected when key is set:

```json
{
  "status": "ok",
  "mode": "gpt",
  "model": "gpt-4o-mini",
  "gpt_ready": true,
  "env_file": "/Users/erg/Desktop/second ai/ai_recruiter_v2/.env",
  "message": "GPT ready (gpt-4o-mini)"
}
```

## 4. Test one parse

```bash
curl -X POST http://localhost:8790/api/parse \
  -H "Content-Type: application/json" \
  -d '{"raw_text":"Тошико Суши Шымкент жеткізу орталығына курьер қажет\nКонтакты: 87071234567"}'
```

## 5. Get an API key

https://platform.openai.com/api-keys

## Important

- `.env` is gitignored — never commit your key
- Without `OPENAI_API_KEY`, parsing returns HTTP 503
- There is no mock/fallback parser in v2
