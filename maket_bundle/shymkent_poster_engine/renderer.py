"""Renderer — text overlay only; background untouched."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from .constants import TEXT_COLOR_RGB
from .fonts import load_font, measure_text
from .layout import LayoutSolution


def render_poster(
    template: Image.Image,
    solution: LayoutSolution,
    font_path: str,
    output_path: str | Path,
) -> Image.Image:
    canvas = template.convert("RGBA").copy()
    _draw_solution(ImageDraw.Draw(canvas), solution, font_path)
    canvas.save(output_path, "PNG")
    return canvas


def render_preview(
    template: Image.Image,
    solution: LayoutSolution,
    font_path: str,
) -> Image.Image:
    canvas = template.convert("RGBA").copy()
    _draw_solution(ImageDraw.Draw(canvas), solution, font_path)
    return canvas


def _draw_solution(
    draw: ImageDraw.ImageDraw,
    solution: LayoutSolution,
    font_path: str,
) -> None:
    cx = solution.geometry.C_x
    for block in solution.blocks:
        font = load_font(block.font_size, font_path)
        y = block.y
        step = block.font_size * block.line_height_coef
        for line in block.lines:
            w, _ = measure_text(font, line)
            draw.text((cx - w / 2, y), line, font=font, fill=TEXT_COLOR_RGB)
            y += step
