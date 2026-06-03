"""Font loading and text measurement."""

from __future__ import annotations

from PIL import ImageFont


def load_font(size: float, font_path: str) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path, max(int(round(size)), 1))


def measure_text(font: ImageFont.FreeTypeFont, text: str) -> tuple[float, float]:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]
