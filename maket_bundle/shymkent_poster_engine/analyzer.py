"""Content measurement — computed before rendering."""

from __future__ import annotations

from dataclasses import dataclass

from .blocks import BlockSequence, build_block_sequence
from .constants import HIERARCHY, LINE_HEIGHT_BY_BLOCK
from .parser import PosterMode, VacancyData


LARGE_KEYS = {"vacancy_title", "multi_title"}
MEDIUM_KEYS = {"company", "position_list", "salary", "requirements_heading", "responsibilities_heading", "conditions_heading"}
SMALL_KEYS = {"requirements_items", "responsibilities_items", "conditions_items"}
CONTACT_KEYS = {"phone", "address", "instagram"}


@dataclass
class ContentMetrics:
    C_total: int = 0
    W_total: int = 0
    L_total: int = 0
    P_total: int = 0
    N_large: int = 0
    N_medium: int = 0
    N_small: int = 0
    N_contact: int = 0
    N_positions: int = 0
    L_max: int = 0


def _word_count(text: str) -> int:
    return len(text.split()) if text.strip() else 0


def measure_content(data: VacancyData, wrapped_line_counts: list[int] | None = None) -> ContentMetrics:
    """Measure content from parsed blocks (pre-render)."""
    seq = build_block_sequence(data)
    texts = [b.text for b in seq.blocks]

    C_total = sum(len(t) for t in texts)
    W_total = sum(_word_count(t) for t in texts)
    P_total = len(seq.blocks)

    if wrapped_line_counts is not None:
        L_total = sum(wrapped_line_counts)
    else:
        L_total = P_total

    N_large = sum(1 for b in seq.blocks if b.key in LARGE_KEYS)
    N_medium = sum(1 for b in seq.blocks if b.key in MEDIUM_KEYS)
    N_small = sum(1 for b in seq.blocks if b.key in SMALL_KEYS)
    N_contact = sum(1 for b in seq.blocks if b.key in CONTACT_KEYS)

    N_positions = len(data.positions) if data.mode == PosterMode.MULTI else (
        1 if data.vacancy_title else 0
    )

    L_max = max((len(t) for t in texts), default=0)

    return ContentMetrics(
        C_total=C_total,
        W_total=W_total,
        L_total=L_total,
        P_total=P_total,
        N_large=N_large,
        N_medium=N_medium,
        N_small=N_small,
        N_contact=N_contact,
        N_positions=N_positions,
        L_max=L_max,
    )


def hierarchy_coefficient(block_key: str) -> float:
    return HIERARCHY[block_key]


def line_height_coefficient(block_key: str) -> float:
    return LINE_HEIGHT_BY_BLOCK[block_key]
