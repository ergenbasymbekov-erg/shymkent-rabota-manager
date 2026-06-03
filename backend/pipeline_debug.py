"""
Temporary pipeline debugger — trace where positions[] / vacancy_title are lost.

Enable with env PIPELINE_DEBUG=1 (default on during investigation).
Does NOT modify extraction logic — observation only.
"""

import json
import logging
import os
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("pipeline_debug")

PIPELINE_DEBUG = os.environ.get("PIPELINE_DEBUG", "1").strip() not in ("0", "false", "no")


class PositionStageSnapshot(BaseModel):
    stage: str = ""
    module: str = ""
    vacancy_title: str = ""
    positions: list[str] = Field(default_factory=list)
    position_groups_count: int = 0
    note: str = ""
    raw_gpt: Optional[Any] = None


class PipelineDebugTrace(BaseModel):
    enabled: bool = False
    stages: list[PositionStageSnapshot] = Field(default_factory=list)
    positions_lost_at: str = ""
    title_lost_at: str = ""
    summary: str = ""
    ui_state: dict = Field(default_factory=dict)


class PipelineDebugger:
    """Collect position snapshots through normalize pipeline."""

    def __init__(self, enabled: bool = PIPELINE_DEBUG):
        self.enabled = enabled
        self.stages: list[PositionStageSnapshot] = []

    def snap(
        self,
        stage: str,
        module: str,
        data: dict,
        note: str = "",
        raw_gpt: Any = None,
    ) -> None:
        if not self.enabled:
            return
        positions = list(data.get("positions") or [])
        groups = data.get("position_groups") or []
        snap = PositionStageSnapshot(
            stage=stage,
            module=module,
            vacancy_title=(data.get("vacancy_title") or "").strip(),
            positions=positions,
            position_groups_count=len(groups) if isinstance(groups, list) else 0,
            note=note,
            raw_gpt=raw_gpt,
        )
        self.stages.append(snap)
        logger.warning(
            "[PIPELINE_DEBUG] %s | %s | title=%r positions=%s groups=%s %s",
            stage,
            module,
            snap.vacancy_title,
            snap.positions,
            snap.position_groups_count,
            note,
        )
        print(
            f"[PIPELINE_DEBUG] {stage:28} | {module:40} | "
            f"title={snap.vacancy_title!r:25} positions={snap.positions!r}"
            + (f" | {note}" if note else ""),
            flush=True,
        )

    def build(
        self,
        ui_state: Optional[dict] = None,
        quality_missing_fields: Optional[list] = None,
        structured_positions: Optional[list] = None,
        structured_title: str = "",
    ) -> PipelineDebugTrace:
        if not self.enabled:
            return PipelineDebugTrace(enabled=False)

        lost_at = ""
        title_lost_at = ""
        prev_pos: Optional[list] = None
        prev_title = None

        for s in self.stages:
            if prev_pos is not None and len(prev_pos) > 0 and len(s.positions) == 0:
                lost_at = s.stage
            if prev_title and prev_title.strip() and not (s.vacancy_title or "").strip():
                title_lost_at = s.stage
            prev_pos = list(s.positions)
            prev_title = s.vacancy_title

        summary_parts = []
        if lost_at:
            summary_parts.append(f"positions[] cleared at stage: {lost_at}")
        if title_lost_at:
            summary_parts.append(f"vacancy_title cleared at stage: {title_lost_at}")
        if quality_missing_fields:
            summary_parts.append(
                f"quality.missing_fields (GPT QC): {quality_missing_fields}"
            )
        if structured_positions is not None:
            summary_parts.append(
                f"final structured.positions={structured_positions!r} "
                f"structured.vacancy_title={structured_title!r}"
            )
        if quality_missing_fields and structured_positions:
            if "positions" in quality_missing_fields and structured_positions:
                summary_parts.append(
                    "NOTE: positions exist in structured but quality GPT still flagged missing — "
                    "UI 'Missing fields' comes from quality.missing_fields, not structured emptiness"
                )
            if "vacancy_title" in quality_missing_fields and structured_title:
                summary_parts.append(
                    "NOTE: vacancy_title exists in structured but quality GPT flagged missing"
                )

        return PipelineDebugTrace(
            enabled=True,
            stages=self.stages,
            positions_lost_at=lost_at,
            title_lost_at=title_lost_at,
            summary=" | ".join(summary_parts) if summary_parts else "No position loss detected",
            ui_state=ui_state or {},
        )


def snap_from_model(debugger: Optional[PipelineDebugger], stage: str, module: str, model, note: str = ""):
    if not debugger or not debugger.enabled:
        return
    if hasattr(model, "model_dump"):
        d = model.model_dump()
    elif isinstance(model, dict):
        d = model
    else:
        d = {}
    debugger.snap(stage, module, d, note=note)
