"""Bridge ai_recruiter_v2 → Shymkent Rabota poster engine (maket 4)."""

import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Optional, Tuple

from completeness import run_completeness_check
from editorial import build_multi_public_headline, build_single_public_headline
from generate import detect_structured_language
from phones import format_phone_display, normalize_phone_internal
from position import MULTI_POSITION, has_valid_positions, valid_positions
from poster_text_adapter import poster_text_to_debug, poster_text_to_preview, trim_preview_for_fit
from schema import StructuredData
from validation import validation_from_structured

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
POSTERS_DIR = ROOT / "posters" / "generated"
DEFAULT_MAKET_ROOT = Path.home() / "Desktop" / "maket 4"
DEFAULT_TEMPLATE = "AC1665E4-6875-4288-81DF-0CCAFCDD4A94.PNG"


def _maket_root() -> Path:
    return Path(os.environ.get("MAKET4_ROOT", DEFAULT_MAKET_ROOT))


def _template_path() -> Path:
    custom = os.environ.get("MAKET4_TEMPLATE", "")
    if custom:
        return Path(custom)
    return _maket_root() / DEFAULT_TEMPLATE


def _ensure_engine():
    maket = _maket_root()
    if not maket.is_dir():
        raise FileNotFoundError(f"Poster engine not found at {maket}. Set MAKET4_ROOT.")
    engine_pkg = maket / "shymkent_poster_engine"
    if not engine_pkg.is_dir():
        raise FileNotFoundError(f"shymkent_poster_engine missing in {maket}")
    if str(maket) not in sys.path:
        sys.path.insert(0, str(maket))


def _resolve_phone(structured: StructuredData) -> str:
    if structured.phones_display:
        return structured.phones_display[0].strip()
    if structured.phones:
        internal = structured.phones[0].strip()
        norm, err = normalize_phone_internal(internal)
        if not err:
            return format_phone_display(norm)
        return internal
    return ""


def _detect_language(structured: StructuredData, override: str = "") -> str:
    if override:
        o = override.lower()
        if o in ("kazakh", "kk"):
            return "KAZAKH"
        if o in ("russian", "ru"):
            return "RUSSIAN"
        return override.upper()
    lang = detect_structured_language(structured)
    return "KAZAKH" if lang == "kazakh" else "RUSSIAN"


def _lang_key(maket_lang: str) -> str:
    return "kazakh" if maket_lang == "KAZAKH" else "russian"


def structured_to_maket_preview(structured: StructuredData, language: str = "") -> dict:
    """Map approved StructuredData to maket 4 preview JSON."""
    lang = _detect_language(structured, language)
    lang_key = _lang_key(lang)
    fields = structured.model_dump()
    roles = valid_positions(structured.positions or [])
    is_multi = structured.vacancy_type == MULTI_POSITION or len(roles) > 1
    mode = "MULTI" if is_multi else "SINGLE"

    if is_multi and roles:
        vacancy = build_multi_public_headline(fields, lang_key, poster_display=True)
        vacancies = roles
    else:
        vacancy = build_single_public_headline(fields, lang_key, poster_display=True) if roles else ""
        vacancies = []

    address = (structured.address or "").strip()
    notes = (structured.address_notes or "").strip()
    phone = _resolve_phone(structured)

    preview = {
        "language": lang,
        "mode": mode,
        "company": (structured.company or "").strip(),
        "vacancy": vacancy,
        "vacancies": vacancies,
        "salary": "",
        "requirements": [r.strip() for r in (structured.requirements or []) if r.strip()],
        "responsibilities": [],
        "conditions": [c.strip() for c in (structured.conditions or []) if c.strip()],
        "phones": [phone] if phone else [],
        "phone": phone,
        "address": address,
        "address_notes": notes,
        "instagram": "",
        "notes": "",
        "unsorted_review": [u.strip() for u in (structured.unsorted_review or []) if u.strip()],
    }
    return preview


def validate_for_poster(structured: StructuredData) -> Tuple[bool, list[str]]:
    """Pre-flight checks before calling layout engine."""
    errors: list[str] = []

    def add(msg: str) -> None:
        if msg and msg not in errors:
            errors.append(msg)

    if not (structured.company or "").strip():
        add("Company is required for poster")

    if not has_valid_positions(structured.vacancy_title, structured.positions):
        add("Position is required for poster")

    phone = _resolve_phone(structured)
    if not phone:
        add("Phone is required for poster")
    elif structured.phones:
        _, err = normalize_phone_internal(structured.phones[0])
        if err:
            add(f"PHONE_ERROR: {err}")

    if structured.unsorted_review:
        add(f"Unsorted review items remain ({len(structured.unsorted_review)})")

    validation = validation_from_structured(structured)
    completeness = run_completeness_check(structured, validation)
    if not completeness.can_poster:
        if completeness.score < 70:
            add("Completeness below 70 — poster generation blocked")
        if validation.unknown_position:
            add("UNKNOWN_POSITION — poster blocked until position is confirmed")
        if validation.phone_error:
            add("PHONE_ERROR — phone number invalid or incomplete")

    _ensure_engine()
    from shymkent_poster_engine.workflow import validate_preview

    preview = structured_to_maket_preview(structured)
    maket_val = validate_preview(preview)
    for err in maket_val.errors:
        add(err)

    return len(errors) == 0, errors


def generate_poster_png(
    structured: StructuredData,
    language: str = "",
) -> Tuple[Path, dict]:
    """
    Generate PNG poster from approved structured JSON.
    Returns (output_path, maket_preview_dict).
    """
    ok, errors = validate_for_poster(structured)
    if not ok:
        raise ValueError("; ".join(errors))

    _ensure_engine()
    from shymkent_poster_engine.engine import generate_poster_from_json

    template = _template_path()
    if not template.is_file():
        raise FileNotFoundError(f"Poster template not found: {template}")

    POSTERS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"poster_{uuid.uuid4().hex[:12]}.png"
    output = POSTERS_DIR / filename

    preview = structured_to_maket_preview(structured, language)
    generate_poster_from_json(template, preview, output)

    return output, preview


def generate_poster_from_poster_text(
    poster_text: str,
    raw_text: str = "",
) -> Tuple[Optional[Path], dict, str, dict]:
    """
    Generate PNG from rewrite poster_text — no validation gates.
    Returns (output_path or None, preview_dict, error_message, debug_dict).
    """
    poster_text = (poster_text or "").strip()
    debug = poster_text_to_debug(poster_text, raw_text) if poster_text else {}

    if not poster_text:
        return None, {}, "poster_text is empty", debug

    try:
        _ensure_engine()
    except FileNotFoundError as e:
        return None, {}, str(e), debug

    template = _template_path()
    if not template.is_file():
        return None, {}, f"Poster template not found: {template}", debug

    POSTERS_DIR.mkdir(parents=True, exist_ok=True)
    preview = poster_text_to_preview(poster_text, raw_text)
    debug = poster_text_to_debug(poster_text, raw_text)

    logger.info("[POSTER_DEBUG] data passed to generator:\n%s", json.dumps(debug, ensure_ascii=False, indent=2))
    print("[POSTER_DEBUG] data passed to generator:")
    print(json.dumps(debug, ensure_ascii=False, indent=2))

    last_err = ""
    for attempt in range(8):
        try:
            filename = f"poster_{uuid.uuid4().hex[:12]}.png"
            output = POSTERS_DIR / filename
            _render_poster_relaxed(template, preview, output)
            return output, preview, "", debug
        except ValueError as e:
            last_err = str(e)
            trimmed = trim_preview_for_fit(preview)
            if trimmed == preview:
                break
            preview = trimmed
            debug["maket_preview_after_trim"] = preview
        except Exception as e:
            return None, preview, str(e), debug

    return None, preview, last_err or "Poster layout failed", debug


def _render_poster_relaxed(template_path: Path, preview: dict, output_path: Path) -> None:
    """Render poster via maket 4 engine without strict validation gates."""
    from PIL import Image
    from shymkent_poster_engine.engine import _resolve_font
    from shymkent_poster_engine.geometry import Geometry
    from shymkent_poster_engine.layout import solve_layout
    from shymkent_poster_engine.renderer import render_poster
    from shymkent_poster_engine.template_analysis import detect_footer_logo_top, effective_text_geometry
    from shymkent_poster_engine.workflow import vacancy_from_preview

    vacancy = vacancy_from_preview(preview)
    if not (
        vacancy.vacancy_title
        or vacancy.positions
        or vacancy.company
        or vacancy.phone
    ):
        raise ValueError("No renderable content in poster_text")

    original = Image.open(template_path).convert("RGBA")
    base_geo = Geometry.from_canvas(*original.size)
    logo_top = detect_footer_logo_top(original, base_geo)
    geo = effective_text_geometry(base_geo, logo_top)
    font = _resolve_font()

    layout = solve_layout(vacancy, font, geo)
    render_poster(original, layout, font, output_path)
