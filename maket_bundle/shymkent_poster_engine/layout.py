"""Mathematical layout solver — binary search on S."""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import ImageFont

from .blocks import BlockSequence, build_block_sequence, is_last_in_gap_group
from .constants import (
    BINARY_SEARCH_ITERATIONS,
    GAP_AFTER,
    HIERARCHY,
    LINE_HEIGHT_BY_BLOCK,
    O_w_min,
    O_w_max,
    S_high,
    S_low,
)
from .fonts import load_font, measure_text
from .geometry import Geometry
from .parser import VacancyData


@dataclass
class ResolvedBlock:
    key: str
    text: str
    gap_group: str
    font_size: float
    line_height_coef: float
    lines: list[str] = field(default_factory=list)
    line_widths: list[float] = field(default_factory=list)
    block_height: float = 0.0
    gap_after: float = 0.0
    y: float = 0.0


@dataclass
class LayoutSolution:
    S: float
    geometry: Geometry
    blocks: list[ResolvedBlock]
    H_text: float
    H_stack: float
    Y_start: float
    Y_end: float
    E_top: float
    E_bottom: float
    O_h: float
    O_w: float
    max_line_width: float
    wrap_width: float


def _wrap_line(text: str, font, max_width: float) -> list[str]:
    words = text.split()
    if not words:
        return [text] if text else []

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if measure_text(font, candidate)[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)

    result: list[str] = []
    for line in lines:
        if measure_text(font, line)[0] <= max_width:
            result.append(line)
            continue
        chunk = ""
        for ch in line:
            test = chunk + ch
            if measure_text(font, test)[0] <= max_width:
                chunk = test
            else:
                if chunk:
                    result.append(chunk)
                chunk = ch
        if chunk:
            result.append(chunk)
    return result if result else [text]


def _block_height(line_count: int, font_size: float, lh_coef: float) -> float:
    return line_count * font_size * lh_coef


def _gap_for_group(group: str, S: float, geo: Geometry) -> float:
    raw = S * GAP_AFTER.get(group, 0.0)
    return max(geo.G_min, min(geo.G_max, raw))


def _compute_layout(
    data: VacancyData,
    S: float,
    font_path: str,
    geo: Geometry,
    wrap_width: float,
) -> LayoutSolution:
    seq: BlockSequence = build_block_sequence(data)
    resolved: list[ResolvedBlock] = []
    H_text = 0.0
    total_gaps = 0.0
    max_line_width = 0.0

    for idx, block in enumerate(seq.blocks):
        fs = S * HIERARCHY[block.key]
        lh = LINE_HEIGHT_BY_BLOCK[block.key]
        font = load_font(fs, font_path)

        lines = _wrap_line(block.text, font, wrap_width)
        line_widths = [measure_text(font, ln)[0] for ln in lines]
        max_line_width = max(max_line_width, max(line_widths, default=0.0))

        bh = _block_height(len(lines), fs, lh)
        H_text += bh

        gap = 0.0
        if is_last_in_gap_group(seq.blocks, idx) and block.gap_group != "instagram":
            gap = _gap_for_group(block.gap_group, S, geo)
            total_gaps += gap

        resolved.append(ResolvedBlock(
            key=block.key,
            text=block.text,
            gap_group=block.gap_group,
            font_size=fs,
            line_height_coef=lh,
            lines=lines,
            line_widths=line_widths,
            block_height=bh,
            gap_after=gap,
        ))

    H_stack = H_text + total_gaps
    Y_start = geo.active_top + (geo.A_h - H_stack) / 2
    Y_end = Y_start + H_stack
    E_top = Y_start - geo.active_top
    E_bottom = geo.active_bottom - Y_end

    y = Y_start
    for block in resolved:
        block.y = y
        y += block.block_height + block.gap_after

    return LayoutSolution(
        S=S,
        geometry=geo,
        blocks=resolved,
        H_text=H_text,
        H_stack=H_stack,
        Y_start=Y_start,
        Y_end=Y_end,
        E_top=E_top,
        E_bottom=E_bottom,
        O_h=H_stack / geo.A_h,
        O_w=max_line_width / geo.A_w,
        max_line_width=max_line_width,
        wrap_width=wrap_width,
    )


def _height_distance(sol: LayoutSolution, geo: Geometry) -> float:
    return abs(sol.H_stack - geo.H_ideal)


def _max_valid_s_layout(
    data: VacancyData,
    font_path: str,
    geo: Geometry,
    wrap_width: float,
    s_lo: float,
    s_hi: float,
) -> LayoutSolution:
    """Find largest S where H_min <= H_stack <= H_max (30 iterations)."""
    lo, hi = s_lo, s_hi
    best: LayoutSolution | None = None

    for _ in range(BINARY_SEARCH_ITERATIONS):
        mid = (lo + hi) / 2
        sol = _compute_layout(data, mid, font_path, geo, wrap_width)

        if sol.H_stack > geo.H_max:
            hi = mid
        elif sol.H_stack < geo.H_min:
            lo = mid
        else:
            best = sol
            lo = mid

    if best is not None:
        return best

    mid = (s_lo + s_hi) / 2
    return _compute_layout(data, mid, font_path, geo, wrap_width)


def solve_layout(data: VacancyData, font_path: str, geo: Geometry) -> LayoutSolution:
    wrap_width = geo.W_max
    s_lo = S_low * geo.scale_y
    s_hi = S_high * geo.scale_y

    for _ in range(5):
        best_valid = _max_valid_s_layout(data, font_path, geo, wrap_width, s_lo, s_hi)

        if best_valid.O_w < O_w_min and wrap_width < geo.W_max:
            wrap_width = min(geo.W_max, wrap_width + geo.A_w * 0.02)
            continue
        if best_valid.O_w > O_w_max and wrap_width > geo.W_min:
            wrap_width = max(geo.W_min, wrap_width - geo.A_w * 0.02)
            continue
        return best_valid

    return best_valid
