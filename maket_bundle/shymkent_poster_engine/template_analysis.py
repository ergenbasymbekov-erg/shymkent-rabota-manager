"""Template analysis — detect protected footer logo zone."""

from __future__ import annotations

from PIL import Image

from .geometry import Geometry


def detect_footer_logo_top(template: Image.Image, geo: Geometry) -> float:
    """
    Scan template for red footer logo pixels inside active width.
    Returns Y coordinate (px) above which text must not extend.
    """
    img = template.convert("RGBA")
    w, h = img.size

    scan_top = int(geo.active_top + geo.A_h * 0.55)
    scan_bottom = int(geo.active_bottom)
    x_left = int(geo.active_left)
    x_right = int(geo.active_right)

    logo_rows: list[int] = []
    for y in range(scan_top, min(scan_bottom, h)):
        red_count = 0
        for x in range(x_left, x_right, 2):
            r, g, b, a = img.getpixel((x, y))
            if r > 200 and g < 80 and b < 80 and a > 200:
                red_count += 1
        if red_count > 15:
            logo_rows.append(y)

    if not logo_rows:
        return geo.active_bottom

    logo_top = min(logo_rows)
    margin = 8 * geo.scale_y
    return logo_top - margin


def effective_text_geometry(base: Geometry, text_bottom: float) -> Geometry:
    """Return geometry with reduced active bottom to protect footer logo."""
    if text_bottom >= base.active_bottom:
        return base

    bottom = text_bottom
    top = base.active_top
    left = base.active_left
    right = base.active_right
    a_w = right - left
    a_h = bottom - top

    return base.__class__(
        canvas_w=base.canvas_w,
        canvas_h=base.canvas_h,
        scale_x=base.scale_x,
        scale_y=base.scale_y,
        active_left=left,
        active_top=top,
        active_right=right,
        active_bottom=bottom,
        A_w=a_w,
        A_h=a_h,
        A_area=a_w * a_h,
        C_x=(left + right) / 2,
        C_y=(top + bottom) / 2,
        W_max=0.90 * a_w,
        W_ideal=0.80 * a_w,
        W_min=0.70 * a_w,
        H_min=0.85 * a_h,
        H_ideal=0.90 * a_h,
        H_max=0.95 * a_h,
        G_min=0.015 * a_h,
        G_max=0.08 * a_h,
        balance_tolerance=0.05 * a_h,
        footer_logo_top=text_bottom,
    )
