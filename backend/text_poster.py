"""Render manager text onto poster template — styling only, no content changes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from poster_bridge import POSTERS_DIR, _ensure_engine, _template_path
from template_mode import LineRole, classify_lines

TEXT_COLOR = (237, 28, 36)

# Relative size vs base scale S
SIZE = {
    "hero": 1.00,
    "section_header": 0.62,
    "phone": 0.72,
    "body": 0.48,
    "blank": 0.0,
}

LINE_HEIGHT = {
    "hero": 1.12,
    "section_header": 1.14,
    "phone": 1.12,
    "body": 1.15,
    "blank": 0.5,
}

GAP_BEFORE = {
    "hero": 0.08,
    "section_header": 0.22,
    "phone": 0.10,
    "body": 0.06,
    "blank": 0.04,
}

MIN_S = 8.0
MAX_S = 90.0


@dataclass
class DrawLine:
    text: str
    role: LineRole
    font_size: float
    lines: list[str]
    line_widths: list[float]
    block_height: float
    gap_before: float
    y: float = 0.0


def _resolve_font() -> str:
    from poster_bridge import ROOT as APP_ROOT

    for name in ("Arial-Bold.ttf", "Montserrat-ExtraBold.ttf"):
        bundled = (APP_ROOT / "maket_bundle" / "fonts" / name).resolve()
        if bundled.is_file():
            return str(bundled)
    _ensure_engine()
    from shymkent_poster_engine.engine import _resolve_font as maket_font
    return maket_font()


def _resolve_geo(template_path: Path):
    _ensure_engine()
    from shymkent_poster_engine.geometry import Geometry
    from shymkent_poster_engine.template_analysis import detect_footer_logo_top, effective_text_geometry

    img = Image.open(template_path).convert("RGBA")
    base = Geometry.from_canvas(*img.size)
    logo_top = detect_footer_logo_top(img, base)
    return img, effective_text_geometry(base, logo_top)


def _measure(font: ImageFont.FreeTypeFont, text: str) -> tuple[float, float]:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _load_font(size: float, font_path: str) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path, max(int(round(size)), 1))


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    words = text.split()
    if not words:
        return [text] if text else []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _measure(font, candidate)[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    result: list[str] = []
    for line in lines:
        if _measure(font, line)[0] <= max_width:
            result.append(line)
            continue
        chunk = ""
        for ch in line:
            test = chunk + ch
            if _measure(font, test)[0] <= max_width:
                chunk = test
            else:
                if chunk:
                    result.append(chunk)
                chunk = ch
        if chunk:
            result.append(chunk)
    return result if result else [text]


def _build_blocks(classified: list[tuple[str, LineRole]], s: float, font_path: str, wrap_w: float) -> list[DrawLine]:
    blocks: list[DrawLine] = []
    for text, role in classified:
        if role == "blank":
            blocks.append(DrawLine("", "blank", 0, [], [], s * LINE_HEIGHT["blank"], s * GAP_BEFORE["blank"]))
            continue
        fs = s * SIZE[role]
        font = _load_font(fs, font_path)
        wrapped = _wrap(text, font, wrap_w)
        widths = [_measure(font, ln)[0] for ln in wrapped]
        lh = fs * LINE_HEIGHT[role]
        blocks.append(DrawLine(
            text=text,
            role=role,
            font_size=fs,
            lines=wrapped,
            line_widths=widths,
            block_height=len(wrapped) * lh,
            gap_before=s * GAP_BEFORE[role],
        ))
    return blocks


def _stack_height(blocks: list[DrawLine]) -> float:
    total = 0.0
    for i, b in enumerate(blocks):
        if i > 0 and b.role != "blank":
            total += b.gap_before
        total += b.block_height
    return total


def _layout(blocks: list[DrawLine], geo) -> float:
    h = _stack_height(blocks)
    y = geo.active_top + (geo.A_h - h) / 2
    for i, b in enumerate(blocks):
        if i > 0 and b.role != "blank":
            y += b.gap_before
        b.y = y
        y += b.block_height
    return h


def generate_text_poster(text: str) -> tuple[Optional[Path], str, list[dict]]:
    """
    Render exact manager text onto template.
    Returns (png_path, warning_message, debug_lines).
    """
    if not text.strip():
        return None, "Text is empty", []

    classified = classify_lines(text)
    if not classified:
        return None, "No renderable lines", []

    template = _template_path()
    if not template.is_file():
        return None, f"Template not found: {template}", []

    canvas, geo = _resolve_geo(template)
    font_path = _resolve_font()
    wrap_w = geo.W_max

    warning = ""
    chosen_s = MIN_S
    blocks: list[DrawLine] = []
    stack_h = 0.0

    for s in [MAX_S - i * 2 for i in range(int((MAX_S - MIN_S) / 2) + 1)]:
        trial = _build_blocks(classified, s, font_path, wrap_w)
        stack_h = _layout(trial, geo)
        if stack_h <= geo.H_max:
            chosen_s = s
            blocks = trial
            break
        blocks = trial
        chosen_s = s

    if stack_h > geo.H_max:
        warning = "Poster text is too long, please shorten manually."
        blocks = _build_blocks(classified, MIN_S, font_path, wrap_w)
        _layout(blocks, geo)
        max_y = geo.active_top + geo.H_max
        kept: list[DrawLine] = []
        for block in blocks:
            if block.role == "blank":
                kept.append(block)
                continue
            if block.y >= max_y:
                break
            if block.y + block.block_height > max_y:
                break
            kept.append(block)
        blocks = kept

    draw = ImageDraw.Draw(canvas)
    cx = geo.C_x
    for block in blocks:
        if block.role == "blank":
            continue
        font = _load_font(block.font_size, font_path)
        y = block.y
        step = block.font_size * LINE_HEIGHT[block.role]
        for line in block.lines:
            w, _ = _measure(font, line)
            draw.text((cx - w / 2, y), line, font=font, fill=TEXT_COLOR)
            y += step

    POSTERS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"poster_{uuid.uuid4().hex[:12]}.png"
    output = POSTERS_DIR / filename
    canvas.save(output, "PNG")

    debug = [
        {"text": b.text, "role": b.role, "font_size": round(b.font_size, 1), "lines": b.lines}
        for b in blocks if b.role != "blank"
    ]
    return output, warning, debug
