"""Canvas geometry — exact 1080×1080 spec, scaled to native template pixels."""

from __future__ import annotations

from dataclasses import dataclass

REF_W = 1080
REF_H = 1080

REF_ACTIVE_LEFT = 130
REF_ACTIVE_TOP = 110
REF_ACTIVE_RIGHT = 955
REF_ACTIVE_BOTTOM = 1020


@dataclass(frozen=True)
class Geometry:
    """All layout math runs in pixel space mapped from the 1080×1080 spec."""

    canvas_w: int
    canvas_h: int
    scale_x: float
    scale_y: float
    active_left: float
    active_top: float
    active_right: float
    active_bottom: float
    A_w: float
    A_h: float
    A_area: float
    C_x: float
    C_y: float
    W_max: float
    W_ideal: float
    W_min: float
    H_min: float
    H_ideal: float
    H_max: float
    G_min: float
    G_max: float
    balance_tolerance: float
    footer_logo_top: float | None = None

    @classmethod
    def from_canvas(cls, width: int, height: int) -> Geometry:
        sx = width / REF_W
        sy = height / REF_H

        left = REF_ACTIVE_LEFT * sx
        top = REF_ACTIVE_TOP * sy
        right = REF_ACTIVE_RIGHT * sx
        bottom = REF_ACTIVE_BOTTOM * sy

        a_w = right - left
        a_h = bottom - top

        return cls(
            canvas_w=width,
            canvas_h=height,
            scale_x=sx,
            scale_y=sy,
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
        )

    @classmethod
    def spec_reference(cls) -> Geometry:
        """Reference geometry at exactly 1080×1080."""
        return cls.from_canvas(REF_W, REF_H)
