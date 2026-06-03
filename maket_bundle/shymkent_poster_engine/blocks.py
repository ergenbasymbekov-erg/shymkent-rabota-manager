"""Block model — only non-empty approved fields are rendered."""

from __future__ import annotations

from dataclasses import dataclass, field

from .language import Language
from .parser import PosterMode, VacancyData


@dataclass
class LayoutBlock:
    key: str
    text: str
    gap_group: str


@dataclass
class BlockSequence:
    blocks: list[LayoutBlock] = field(default_factory=list)


def _non_empty(text: str) -> bool:
    return bool(text and text.strip())


def build_block_sequence(data: VacancyData) -> BlockSequence:
    """
    Instagram poster blocks — attention-focused layout only.
    Order: vacancy titles → salary → phone → company → instagram.
    No requirements, responsibilities, conditions, or address on poster.
    """
    seq = BlockSequence()

    if data.mode == PosterMode.MULTI:
        for pos in data.positions:
            if _non_empty(pos):
                text = pos.strip().lstrip("•").strip()
                seq.blocks.append(LayoutBlock("position_list", text, "position_list"))
    elif _non_empty(data.vacancy_title):
        seq.blocks.append(LayoutBlock("vacancy_title", data.vacancy_title.strip(), "vacancy_title"))

    if _non_empty(data.salary):
        seq.blocks.append(LayoutBlock("salary", data.salary.strip(), "salary"))

    if _non_empty(data.phone):
        seq.blocks.append(LayoutBlock("phone", data.phone.strip(), "phone"))

    if _non_empty(data.company):
        seq.blocks.append(LayoutBlock("company", data.company.strip(), "company"))

    if _non_empty(data.instagram):
        ig = data.instagram.strip().lstrip("@")
        if ig and ig.lower() not in ("shymkent_rabota_job", "shymkentrabota"):
            seq.blocks.append(LayoutBlock("instagram", ig, "instagram"))

    return seq


def is_last_in_gap_group(blocks: list[LayoutBlock], index: int) -> bool:
    group = blocks[index].gap_group
    for j in range(index + 1, len(blocks)):
        if blocks[j].gap_group == group:
            return False
    return True
