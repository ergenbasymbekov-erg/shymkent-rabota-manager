#!/usr/bin/env python3
"""Test poster extraction + PNG for single, multi, and salary+phone cases."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from poster_bridge import generate_poster_from_poster_text
from poster_text_adapter import poster_text_to_debug

CASES = [
    (
        "single_position",
        """Тошико Суши
Курьер
87082196801""",
    ),
    (
        "multi_positions",
        """Salon Beauty
Мастер шугаринга
Hair-стилист
Лешмейкер
Барбер
87081234567""",
    ),
    (
        "salary_and_phone",
        """Ali Doner
Официант
Мастер-повар
от 250000 тенге
87081234567
alidoner_kz""",
    ),
    (
        "bad_labels_sanitized",
        """Poster text:
Vacancy titles:
Курьер
Phone: 87081234567
Salary: 200000
Instagram: @shymkent_rabota_job
undefined""",
    ),
]


def main():
    out_dir = ROOT / "posters" / "test_fix"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for name, poster_text in CASES:
        debug = poster_text_to_debug(poster_text)
        path, preview, err, full_debug = generate_poster_from_poster_text(poster_text)
        row = {
            "case": name,
            "render_summary": debug["render_summary"],
            "error": err,
            "png": str(path) if path else None,
        }
        results.append(row)
        print("=" * 60)
        print(name)
        print(json.dumps(full_debug, ensure_ascii=False, indent=2))
        if path:
            dest = out_dir / f"{name}.png"
            dest.write_bytes(path.read_bytes())
            print(f"PNG: {dest}")

    print("\nSUMMARY")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
