#!/usr/bin/env python3
"""Offline UNKNOWN_POSITION trace — no GPT required if you pass parsed/editor JSON."""

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from schema import EditorFields, StructuredData, VacancyJSON  # noqa: E402
from unknown_trace import build_unknown_trace, scan_raw_positions  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Trace UNKNOWN_POSITION through pipeline stages")
    p.add_argument("raw_file", nargs="?", help="Raw vacancy text file")
    p.add_argument("--parsed", help="Parser JSON file (optional)")
    p.add_argument("--editor", help="Editor fields JSON file (optional)")
    p.add_argument("--dominant", default="kazakh", choices=("kazakh", "russian"))
    args = p.parse_args()

    if args.raw_file:
        raw = Path(args.raw_file).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()

    parsed = VacancyJSON(**json.loads(Path(args.parsed).read_text())) if args.parsed else VacancyJSON()
    editor = EditorFields(**json.loads(Path(args.editor).read_text())) if args.editor else EditorFields()

    print("RAW SCAN:", scan_raw_positions(raw))
    print()

    trace = build_unknown_trace(
        raw_text=raw,
        parsed=parsed,
        editor_fields=editor,
        after_validate_positions=editor.positions,
        vacancy_type="SINGLE_POSITION",
        vacancy_title=editor.vacancy_title or parsed.vacancy_title,
        positions_after_resolve=editor.positions,
        policy_fields={"positions": editor.positions, "vacancy_title": editor.vacancy_title},
        editorial_fields={"positions": editor.positions, "vacancy_title": editor.vacancy_title},
        structured=StructuredData(
            vacancy_title=editor.vacancy_title or parsed.vacancy_title,
            positions=editor.positions,
        ),
        validation_unknown=not editor.positions,
        dominant=args.dominant,
    )

    if trace.is_unknown:
        print("UNKNOWN_POSITION")
        print(f"  unknown_reason:          {trace.unknown_reason}")
        print(f"  assigned_by_module:      {trace.assigned_by_module}")
        print(f"  lost_at_stage:           {trace.lost_at_stage}")
        print(f"  positions_before_unknown: {trace.positions_before_unknown}")
        print(f"  detail:                  {trace.detail}")
        print()

    print("PIPELINE:")
    print(f"{'STAGE':<22} {'MODULE':<40} {'positions[]':<25} {'raw':<25} vacancy_title")
    for s in trace.pipeline:
        pv = ", ".join(s.positions) or "—"
        pr = ", ".join(s.positions_raw) or "—"
        mark = " ← LOST" if s.stage == trace.lost_at_stage else ""
        print(f"{s.stage:<22} {s.module:<40} {pv:<25} {pr:<25} {s.vacancy_title or '—'}{mark}")


if __name__ == "__main__":
    main()
