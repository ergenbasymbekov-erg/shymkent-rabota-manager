#!/usr/bin/env python3
"""Run one GPT parse test and print analysis."""

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

SAMPLE = json.loads((ROOT / "samples" / "vacancies_20.json").read_text())[0]
RAW = SAMPLE["raw_text"]
BASE = "http://127.0.0.1:8790"

FIELDS = [
    "language", "company", "vacancy_title", "salary", "address",
    "address_notes", "instagram", "notes",
]
LISTS = ["positions", "requirements", "responsibilities", "conditions", "phones", "unsorted_review"]


def is_empty(data, key):
    v = data.get(key)
    if isinstance(v, list):
        return len(v) == 0
    return not (v or "").strip()


def analyze(data: dict) -> dict:
    missing = [k for k in FIELDS if is_empty(data, k)]
    missing += [k for k in LISTS if is_empty(data, k)]

    filled = len(FIELDS) + len(LISTS) - len(missing)
    total = len(FIELDS) + len(LISTS)
    base = filled / total

    # Penalize unsorted lines and empty core fields
    unsorted = len(data.get("unsorted_review") or [])
    core_missing = sum(1 for k in ("company", "vacancy_title", "phones") if is_empty(data, k))
    confidence = max(0, min(100, round((base * 100) - unsorted * 5 - core_missing * 10)))

    return {
        "confidence_score": confidence,
        "missing_fields": missing,
        "unsorted_count": unsorted,
        "vacancy_type": data.get("vacancy_type"),
    }


def main():
    req = urllib.request.Request(
        f"{BASE}/api/parse",
        data=json.dumps({"raw_text": RAW}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read())

    data = result["data"]
    analysis = analyze(data)

    print("=== RAW TEXT ===")
    print(RAW)
    print("\n=== EXTRACTED JSON ===")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    print("\n=== ANALYSIS ===")
    print(json.dumps(analysis, ensure_ascii=False, indent=2))
    print(f"\nmode={result.get('mode')} model={result.get('model')}")


if __name__ == "__main__":
    main()
