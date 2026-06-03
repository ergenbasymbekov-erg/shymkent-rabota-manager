"""Strict constraint validation — all rules before export."""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from .constants import GAP_AFTER, HIERARCHY, O_h_max, O_h_min, O_w_max, O_w_min
from .geometry import Geometry
from .fonts import load_font, measure_text
from .layout import LayoutSolution


CONTENT_KEYS = frozenset({
    "company", "vacancy_title", "multi_title", "position_list",
    "salary", "requirements_heading", "requirements_items",
    "responsibilities_heading", "responsibilities_items",
    "conditions_heading", "conditions_items",
})

WIDTH_OCCUPANCY_KEYS = frozenset({
    "company", "vacancy_title", "multi_title", "salary",
    "requirements_heading", "requirements_items",
    "responsibilities_heading", "responsibilities_items",
    "conditions_heading", "conditions_items",
})


@dataclass
class ValidationReport:
    valid: bool = True
    errors: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.errors.append(msg)
        self.valid = False


def validate_solution(sol: LayoutSolution, font_path: str, geo: Geometry) -> ValidationReport:
    report = ValidationReport()

    if not (geo.H_min <= sol.H_stack <= geo.H_max):
        report.fail(f"[8] H_stack {sol.H_stack:.2f} not in [{geo.H_min:.2f}, {geo.H_max:.2f}]")

    if not (O_h_min <= sol.O_h <= O_h_max):
        report.fail(f"O_h {sol.O_h:.4f} not in [{O_h_min}, {O_h_max}]")

    if sol.max_line_width > geo.W_max + 0.5:
        report.fail(f"[9] max_line_width {sol.max_line_width:.2f} > W_max {geo.W_max:.2f}")

    if sol.O_w < O_w_min - 0.005:
        report.fail(f"O_w {sol.O_w:.4f} < {O_w_min}")

    if sol.O_w > O_w_max + 0.001:
        report.fail(f"O_w {sol.O_w:.4f} > {O_w_max}")

    if sol.Y_start < geo.active_top - 0.5:
        report.fail(f"[7] Y_start {sol.Y_start:.2f} < TOP {geo.active_top:.2f}")

    if sol.Y_end > geo.active_bottom + 0.5:
        report.fail(f"[7] Y_end {sol.Y_end:.2f} > BOTTOM {geo.active_bottom:.2f}")

    if abs(sol.E_top - sol.E_bottom) > geo.balance_tolerance + 0.5:
        report.fail(
            f"|E_top-E_bottom|={abs(sol.E_top - sol.E_bottom):.2f} > {geo.balance_tolerance:.2f}"
        )

    if abs((sol.Y_end - sol.Y_start) - sol.H_stack) > 0.5:
        report.fail("Y_end - Y_start != H_stack")

    occupancy_max_w = max(
        (w for b in sol.blocks if b.key in WIDTH_OCCUPANCY_KEYS for w in b.line_widths),
        default=0.0,
    )
    if occupancy_max_w > 0 and occupancy_max_w < geo.W_min - 2.0:
        report.fail(f"[9] content max_line_width {occupancy_max_w:.2f} < W_min {geo.W_min:.2f}")

    prev_bottom = sol.Y_start
    for block in sol.blocks:
        if abs(block.font_size - sol.S * HIERARCHY[block.key]) > 0.01:
            report.fail(f"[11] font_size for {block.key} not S × coefficient")

        if block.gap_after > 0:
            expected = max(
                geo.G_min,
                min(geo.G_max, sol.S * GAP_AFTER.get(block.gap_group, 0.0)),
            )
            if abs(block.gap_after - expected) > 0.5:
                report.fail(f"[12] gap for {block.gap_group} not derived from S")

        font = load_font(block.font_size, font_path)
        y = block.y
        step = block.font_size * block.line_height_coef

        for line in block.lines:
            w, _ = measure_text(font, line)
            x_left = geo.C_x - w / 2
            y_bottom = y + step

            if x_left < geo.active_left - 0.5:
                report.fail(f"[6] line exceeds LEFT: '{line[:40]}'")
            if x_left + w > geo.active_right + 0.5:
                report.fail(f"[6] line exceeds RIGHT: '{line[:40]}'")
            if y < geo.active_top - 0.5:
                report.fail(f"[7] line exceeds TOP: '{line[:40]}'")
            if y_bottom > geo.active_bottom + 0.5:
                report.fail(f"[7] line exceeds BOTTOM: '{line[:40]}'")
            if w > geo.W_max + 0.5:
                report.fail(f"[9] line width {w:.2f} > W_max")
            if y < prev_bottom - 0.5 and prev_bottom > sol.Y_start:
                report.fail(f"[10] overlapping blocks at y={y:.2f}")

            y += step

        prev_bottom = block.y + block.block_height + block.gap_after

    return report


def validate_background_unchanged(
    original: Image.Image,
    rendered: Image.Image,
    geo: Geometry,
    y_text_end: float | None = None,
) -> ValidationReport:
    report = ValidationReport()

    if original.size != rendered.size:
        report.fail("[1] Rendered size differs from template")
        return report

    orig = original.convert("RGBA")
    rend = rendered.convert("RGBA")
    w, h = orig.size
    border = int(125 * geo.scale_x)

    for x0, y0, x1, y1 in [
        (0, 0, w, border),
        (0, h - border, w, h),
        (0, 0, border, h),
        (w - border, 0, w, h),
    ]:
        for x in range(x0, x1, 4):
            for y in range(y0, y1, 4):
                if orig.getpixel((x, y)) != rend.getpixel((x, y)):
                    report.fail(f"[2] Border modified at ({x}, {y})")
                    return report

    scan_y0 = int(y_text_end) if y_text_end is not None else int(geo.active_bottom - 40 * geo.scale_y)
    logo_left = int(geo.C_x - 220 * geo.scale_x)
    logo_right = int(geo.C_x + 220 * geo.scale_x)

    for x in range(max(logo_left, border), min(logo_right, w - border), 3):
        for y in range(max(scan_y0, border), h - border, 3):
            op = orig.getpixel((x, y))
            rp = rend.getpixel((x, y))
            is_logo_red = op[0] > 200 and op[1] < 80 and op[2] < 80 and op[3] > 200
            if is_logo_red and op != rp:
                report.fail(f"[4] Footer logo modified at ({x}, {y})")
                return report

    return report
