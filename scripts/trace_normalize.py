#!/usr/bin/env python3
"""Run one normalize and print pipeline debug trace to stdout."""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


async def main() -> None:
    raw = sys.stdin.read() if not sys.argv[1:] else Path(sys.argv[1]).read_text(encoding="utf-8")
    if not raw.strip():
        print("Usage: trace_normalize.py [vacancy.txt]  OR  cat vacancy.txt | trace_normalize.py")
        sys.exit(1)

    from normalize import normalize_vacancy

    result = await normalize_vacancy(raw)
    pd = result.pipeline_debug

    print("\n" + "=" * 72)
    print("PIPELINE DEBUG SUMMARY")
    print("=" * 72)
    print(pd.summary)
    print(f"positions_lost_at: {pd.positions_lost_at or '—'}")
    print(f"title_lost_at:     {pd.title_lost_at or '—'}")
    print(f"ui_state:          {json.dumps(pd.ui_state, ensure_ascii=False)}")

    print("\nSTAGES:")
    for s in pd.stages:
        flag = " <<< LOST" if s.stage == pd.positions_lost_at else ""
        print(f"  {s.stage:30} | {s.module:38} | title={s.vacancy_title!r:22} positions={s.positions!r}{flag}")
        if s.note:
            print(f"    note: {s.note}")

    print("\nFINAL structured:")
    print(json.dumps(result.structured.model_dump(), ensure_ascii=False, indent=2))
    print("\nquality.missing_fields:", result.quality.missing_fields)


if __name__ == "__main__":
    asyncio.run(main())
