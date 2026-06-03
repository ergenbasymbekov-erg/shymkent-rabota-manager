import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from editor import edit_vacancy
from editorial import can_publish_public
from generate import generate_all
from normalize import normalize_vacancy
from rewrite import rewrite_vacancy
from parser import get_model, gpt_configured, parse_vacancy, require_api_key
from reviewer import review_vacancy
from poster_bridge import POSTERS_DIR, generate_poster_png, validate_for_poster
from manager_auth import manager_key_configured, require_manager_key
from template_generate import fast_text_only_mode, generate_from_template
from telegram_publish import publish_to_channel
from schema import (
    EditRequest,
    EditResponse,
    GenerateRequest,
    GenerateResponse,
    NormalizeRequest,
    NormalizeResponse,
    ParseRequest,
    ParseResponse,
    PosterGenerateRequest,
    PosterGenerateResponse,
    ReviewRequest,
    ReviewResponse,
    RewriteRequest,
    RewriteResponse,
    ManagerPublishRequest,
    ManagerPublishResponse,
    TemplateGenerateRequest,
    TemplateGenerateResponse,
)

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

app = FastAPI(title="Vacancy Template Generator", version="4.0.0-template")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FRONTEND = ROOT / "frontend"
SAMPLES = ROOT / "samples" / "vacancies_20.json"
POSTERS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "mode": "template",
        "message": "Template mode — paste final text and generate poster + messaging",
        "manager_web": manager_key_configured(),
        "fast_text_only": fast_text_only_mode(),
    }


@app.post(
    "/api/manager/preview",
    response_model=TemplateGenerateResponse,
    dependencies=[Depends(require_manager_key)],
)
async def manager_preview(req: TemplateGenerateRequest):
    """Mobile web: preview poster + texts (same as /api/generate, requires key)."""
    if not req.text.strip():
        raise HTTPException(400, "text is empty")
    return generate_from_template(req.text)


@app.post(
    "/api/manager/publish",
    response_model=ManagerPublishResponse,
    dependencies=[Depends(require_manager_key)],
)
async def manager_publish(req: ManagerPublishRequest):
    """Mobile web: format and publish directly to the Telegram channel."""
    if not req.text.strip():
        raise HTTPException(400, "text is empty")
    result = generate_from_template(req.text)
    if not result.outputs.telegram_text.strip():
        raise HTTPException(400, result.error or "empty telegram text")

    png_path = None
    if result.poster_png_filename:
        candidate = POSTERS_DIR / result.poster_png_filename
        if candidate.is_file():
            png_path = candidate

    try:
        await publish_to_channel(
            source_text=result.source_text,
            telegram_text=result.outputs.telegram_text,
            png_path=png_path,
        )
    except Exception as e:
        raise HTTPException(502, f"Telegram publish failed: {e}") from e

    return ManagerPublishResponse(
        channel=os.environ.get("TELEGRAM_CHANNEL_ID", ""),
        message="Published to channel",
        poster_used=bool(png_path),
    )


@app.post("/api/generate", response_model=TemplateGenerateResponse)
async def generate_template(req: TemplateGenerateRequest):
    """Template mode: manager text in → poster PNG + Telegram + WhatsApp out. No AI."""
    if not req.text.strip():
        raise HTTPException(400, "text is empty")
    return generate_from_template(req.text)


@app.post("/api/parse", response_model=ParseResponse)
async def parse_one(req: ParseRequest):
    if not req.raw_text.strip():
        raise HTTPException(400, "raw_text is empty")
    try:
        data, model = await parse_vacancy(req.raw_text)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return ParseResponse(data=data, mode="gpt", model=model)


@app.post("/api/rewrite", response_model=RewriteResponse)
async def rewrite_one(req: RewriteRequest):
    """MVP: rewrite messy vacancy text into poster / Telegram / WhatsApp copy."""
    if not req.raw_text.strip():
        raise HTTPException(400, "raw_text is empty")
    try:
        return await rewrite_vacancy(req.raw_text)
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.post("/api/normalize", response_model=NormalizeResponse)
async def normalize_one(req: NormalizeRequest):
    """Legacy pipeline — prefer /api/rewrite for MVP."""
    if not req.raw_text.strip():
        raise HTTPException(400, "raw_text is empty")
    try:
        return await normalize_vacancy(req.raw_text)
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.post("/api/edit", response_model=EditResponse)
async def edit_one(req: EditRequest):
    if not req.raw_text.strip():
        raise HTTPException(400, "raw_text is empty")
    try:
        editor = await edit_vacancy(req.raw_text, req.data)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return EditResponse(editor=editor, model=get_model())


@app.post("/api/review", response_model=ReviewResponse)
async def review_one(req: ReviewRequest):
    if not req.raw_text.strip():
        raise HTTPException(400, "raw_text is empty")
    try:
        review = await review_vacancy(req.raw_text, req.data)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    return ReviewResponse(review=review, model=get_model())


@app.post("/api/generate-all", response_model=GenerateResponse)
async def generate_all_outputs(req: GenerateRequest):
    """Generate poster, Telegram, and WhatsApp text from approved structured JSON."""
    structured = req.structured
    if not any([
        structured.company,
        structured.vacancy_title,
        structured.phones,
        structured.requirements,
    ]):
        raise HTTPException(400, "structured data is empty — approve a vacancy first")
    lang = req.language.strip() if req.language else None
    if lang and lang not in ("kazakh", "russian"):
        raise HTTPException(400, "language must be kazakh or russian")
    if not can_publish_public(structured.model_dump()):
        raise HTTPException(
            400,
            "Public outputs blocked — confirm a real position before generating Telegram, WhatsApp, or poster text.",
        )
    generated = generate_all(structured, language=lang or None)
    return GenerateResponse(generated=generated)


@app.post("/api/generate-poster", response_model=PosterGenerateResponse)
async def generate_poster(req: PosterGenerateRequest):
    """Generate Shymkent Rabota PNG poster from approved structured JSON."""
    structured = req.structured
    lang = req.language.strip() if req.language else ""
    ok, errors = validate_for_poster(structured)
    if not ok:
        raise HTTPException(400, "; ".join(errors))
    try:
        output_path, _ = generate_poster_png(structured, language=lang)
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Poster generation failed: {e}")
    return PosterGenerateResponse(
        png_url=f"/posters/{output_path.name}",
        filename=output_path.name,
    )


@app.post("/api/parse-batch")
async def parse_batch():
    if not SAMPLES.exists():
        raise HTTPException(404, "vacancies_20.json not found")
    items = json.loads(SAMPLES.read_text(encoding="utf-8"))
    require_api_key()
    model = get_model()

    results = []
    for item in items:
        try:
            data, _ = await parse_vacancy(item["raw_text"])
            results.append({"id": item["id"], "title": item["title"], "ok": True, "data": data.model_dump()})
        except Exception as e:
            results.append({"id": item["id"], "title": item["title"], "ok": False, "error": str(e)})

    return {"mode": "gpt", "model": model, "total": len(results), "results": results}


@app.get("/api/samples")
async def samples():
    if SAMPLES.exists():
        return json.loads(SAMPLES.read_text(encoding="utf-8"))
    return []


@app.get("/")
async def index():
    return FileResponse(FRONTEND / "manager.html")


@app.get("/dev")
async def dev_ui():
    return FileResponse(FRONTEND / "index.html")


app.mount("/posters", StaticFiles(directory=POSTERS_DIR), name="posters")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
