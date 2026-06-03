"""Mathematical constraint poster engine — orchestrator."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .analyzer import ContentMetrics, measure_content
from .constants import FONT_CANDIDATES
from .geometry import Geometry
from .layout import LayoutSolution, solve_layout
from .parser import VacancyData
from .renderer import render_poster, render_preview
from .template_analysis import detect_footer_logo_top, effective_text_geometry
from .validator import ValidationReport, validate_background_unchanged, validate_solution
from .workflow import vacancy_from_preview


@dataclass
class PosterResult:
    output_path: Path
    vacancy: VacancyData
    metrics: ContentMetrics
    layout: LayoutSolution
    validation: ValidationReport
    template_hash: str
    geometry: Geometry


def _template_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _resolve_font(custom: str | None = None) -> str:
    if custom:
        return custom
    home = Path.home()
    for candidate in FONT_CANDIDATES:
        path = Path(candidate.replace("~", str(home))).expanduser()
        if path.exists():
            return str(path.resolve())
    raise FileNotFoundError("Montserrat ExtraBold or Arial Bold required.")


def generate_poster_from_json(
    template_path: str | Path,
    approved_json: dict,
    output_path: str | Path,
    *,
    font_path: str | None = None,
) -> PosterResult:
    """Generate poster from manager-approved structured JSON only."""
    vacancy = vacancy_from_preview(approved_json)
    return generate_poster_from_data(template_path, vacancy, output_path, font_path=font_path)


def generate_poster_from_data(
    template_path: str | Path,
    vacancy: VacancyData,
    output_path: str | Path,
    *,
    font_path: str | None = None,
) -> PosterResult:
    """Generate poster from approved VacancyData. Layout engine never sees raw text."""
    template_path = Path(template_path)
    output_path = Path(output_path)
    font = _resolve_font(font_path)

    original = Image.open(template_path).convert("RGBA")
    base_geo = Geometry.from_canvas(*original.size)
    logo_top = detect_footer_logo_top(original, base_geo)
    geo = effective_text_geometry(base_geo, logo_top)
    template_hash = _template_fingerprint(template_path)

    layout = solve_layout(vacancy, font, geo)
    metrics = measure_content(vacancy, [len(b.lines) for b in layout.blocks])

    layout_val = validate_solution(layout, font, geo)
    preview = render_preview(original, layout, font)
    bg_val = validate_background_unchanged(original, preview, geo, layout.Y_end)

    validation = ValidationReport()
    validation.errors.extend(layout_val.errors)
    validation.errors.extend(bg_val.errors)
    validation.valid = layout_val.valid and bg_val.valid

    if not validation.valid:
        raise ValueError(
            "Validation failed — poster not exported:\n" + "\n".join(validation.errors)
        )

    render_poster(original, layout, font, output_path)

    return PosterResult(
        output_path=output_path,
        vacancy=vacancy,
        metrics=metrics,
        layout=layout,
        validation=validation,
        template_hash=template_hash,
        geometry=geo,
    )


def print_analysis(result: PosterResult) -> None:
    v, s, g = result.vacancy, result.layout, result.geometry

    print("=" * 56)
    print("SHYMKENT_RABOTA_JOB — MATHEMATICAL CONSTRAINT ENGINE")
    print("=" * 56)
    print(f"MODE:              {v.mode.value}")
    print(f"LANGUAGE:          {v.language.value if v.language else 'MIXED'}")
    print(f"Canvas:            {g.canvas_w} × {g.canvas_h}")
    print(f"S:                 {s.S:.4f}")
    print(f"H_stack:           {s.H_stack:.2f} px")
    print(f"O_h / O_w:         {s.O_h:.4f} / {s.O_w:.4f}")
    print(f"Output:            {result.output_path}")
    print(f"Validation:        {'PASS' if result.validation.valid else 'FAIL'}")
    print("=" * 56)
