#!/usr/bin/env python3
"""
Run vacancy samples through the full pipeline and produce a PASS / REVIEW / FAIL report.

Tests: parser, phones, position, language, telegram, whatsapp, missing fields.
"""

import asyncio
import json
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from generate import generate_all
from language import detect_dominant_language
from normalize import normalize_vacancy
from phones import _extract_from_raw, normalize_phone_internal
from position import is_unknown_position

SAMPLE_FILES = [
    ROOT / "samples" / "vacancies_20.json",
    ROOT / "samples" / "vacancies_edge_20.json",
]
REPORT_DIR = ROOT / "reports"


def load_samples() -> list:
    items = []
    for path in SAMPLE_FILES:
        if path.exists():
            items.extend(json.loads(path.read_text(encoding="utf-8")))
    return items


def phones_in_raw(raw: str) -> list:
    return _extract_from_raw(raw)


def classify_sample(sample: dict, result, generated) -> dict:
    """Return verdict PASS|REVIEW|FAIL and detailed check results."""
    raw = sample["raw_text"]
    checks = {}
    fail_reasons = []
    review_reasons = []

    structured = result.structured
    validation = result.validation
    completeness = result.completeness
    quality = result.quality

    # 1. Parser — core fields extracted when present in raw
    raw_has_phone = bool(phones_in_raw(raw))
    parsed_has_phone = bool(structured.phones)
    checks["parser_phones"] = (not raw_has_phone) or parsed_has_phone
    if raw_has_phone and not parsed_has_phone:
        review_reasons.append("Parser: phone in raw but not in structured JSON")

    checks["parser_company"] = bool(structured.company.strip()) or "компания" not in raw.lower()
    if not checks["parser_company"] and re.search(r"«.+»|тoo|too|компания", raw, re.I):
        review_reasons.append("Parser: company likely in raw but missing")

    # 2. Phone extraction — valid 11-digit internal
    phone_ok = True
    if structured.phones:
        for p in structured.phones:
            internal, err = normalize_phone_internal(p)
            if err:
                phone_ok = False
                fail_reasons.append(f"Phone invalid: {p!r} ({err})")
    elif raw_has_phone:
        phone_ok = False
        fail_reasons.append("Phone in raw text but missing/invalid after pipeline")
    checks["phone_extraction"] = phone_ok and not validation.phone_error
    if validation.phone_error:
        fail_reasons.append("PHONE_ERROR flag set")

    # 3. Position detection
    title = (structured.vacancy_title or "").strip()
    checks["position"] = not is_unknown_position(title) or sample.get("expect_unknown")
    if is_unknown_position(title):
        review_reasons.append(f"Position UNKNOWN_POSITION: {title!r}")
    if validation.unknown_position:
        review_reasons.append("Validation: unknown_position flag")

    # 4. Language preservation
    checks["language"] = quality.language_preserved and not validation.language_error
    if validation.language_error:
        fail_reasons.append("LANGUAGE_ERROR: output language mismatch")
    elif not quality.language_preserved:
        review_reasons.append("QC: language_preserved=false")

    dominant = detect_dominant_language(raw)

    # 5. Telegram output
    tg = generated.telegram_text if generated else ""
    checks["telegram"] = bool(tg.strip())
    if not checks["telegram"]:
        fail_reasons.append("Telegram output empty")
    elif raw_has_phone and structured.phones and "📞" not in tg:
        review_reasons.append("Telegram: phone section missing")

    # 6. WhatsApp output
    wa = generated.whatsapp_text if generated else ""
    checks["whatsapp"] = bool(wa.strip()) and "*" in wa
    if not checks["whatsapp"]:
        fail_reasons.append("WhatsApp output empty or missing bold formatting")

    # 7. Missing fields detection
    checks["missing_fields"] = bool(completeness.missing is not None)
    if completeness.missing:
        review_reasons.append(f"Missing fields: {', '.join(completeness.missing)}")

    # Additional flags
    if validation.discrimination_flag:
        review_reasons.append("DISCRIMINATION flagged")
    if validation.critical_data_missing:
        review_reasons.append("CRITICAL_DATA_MISSING")
    if quality.information_lost:
        review_reasons.append("QC: information_lost")
    if quality.information_invented:
        review_reasons.append("QC: information_invented")
    if completeness.status == "INCOMPLETE":
        fail_reasons.append(f"Completeness INCOMPLETE ({completeness.score}/100)")
    elif completeness.status == "REVIEW":
        review_reasons.append(f"Completeness REVIEW ({completeness.score}/100)")
    if result.review_required:
        review_reasons.append("review_required=true")
    if not result.can_approve:
        review_reasons.append("can_approve=false")

    # Verdict
    if fail_reasons:
        verdict = "FAIL"
    elif review_reasons or completeness.status == "REVIEW" or result.review_required:
        verdict = "REVIEW"
    elif all(checks.values()):
        verdict = "PASS"
    else:
        verdict = "REVIEW"
        review_reasons.append("One or more checks incomplete")

    return {
        "verdict": verdict,
        "checks": checks,
        "fail_reasons": fail_reasons,
        "review_reasons": review_reasons,
        "dominant_language": dominant,
        "completeness_score": completeness.score,
        "completeness_status": completeness.status,
        "confidence": quality.confidence,
        "can_approve": result.can_approve,
    }


async def run_one(sample: dict) -> dict:
    entry = {
        "id": sample["id"],
        "title": sample["title"],
        "raw_text": sample["raw_text"],
        "verdict": "FAIL",
        "error": None,
        "structured": None,
        "parsed": None,
        "generated": None,
        "analysis": None,
    }
    try:
        result = await normalize_vacancy(sample["raw_text"])
        generated = generate_all(result.structured)
        analysis = classify_sample(sample, result, generated)
        entry["verdict"] = analysis["verdict"]
        entry["structured"] = result.structured.model_dump()
        entry["parsed"] = result.parsed.model_dump()
        entry["generated"] = generated.model_dump()
        entry["analysis"] = analysis
        entry["after"] = result.after
        entry["validation"] = result.validation.model_dump()
        entry["completeness"] = result.completeness.model_dump()
        entry["quality"] = {
            "confidence": result.quality.confidence,
            "language_preserved": result.quality.language_preserved,
            "information_lost": result.quality.information_lost,
            "missing_fields": result.quality.missing_fields,
            "warnings": result.quality.warnings,
        }
    except Exception as e:
        entry["error"] = str(e)
        entry["traceback"] = traceback.format_exc()
        entry["analysis"] = {
            "verdict": "FAIL",
            "fail_reasons": [f"Pipeline exception: {e}"],
            "review_reasons": [],
            "checks": {},
        }
    return entry


def render_markdown(results: list) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    counts = {"PASS": 0, "REVIEW": 0, "FAIL": 0}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    lines = [
        "# Vacancy Pipeline Batch Test Report",
        "",
        f"**Generated:** {ts}  ",
        f"**Samples:** {len(results)}  ",
        "",
        "## Summary",
        "",
        "| Verdict | Count |",
        "|---------|-------|",
        f"| PASS | {counts['PASS']} |",
        f"| REVIEW | {counts['REVIEW']} |",
        f"| FAIL | {counts['FAIL']} |",
        "",
        "## Check Matrix",
        "",
        "| ID | Title | Verdict | Phone | Position | Lang | TG | WA | Score |",
        "|----|-------|---------|-------|----------|------|----|----|-------|",
    ]

    for r in results:
        a = r.get("analysis") or {}
        c = a.get("checks") or {}
        score = a.get("completeness_score", "—")
        def yn(k):
            return "✓" if c.get(k) else "✗"
        lines.append(
            f"| {r['id']} | {r['title'][:30]} | **{r['verdict']}** | "
            f"{yn('phone_extraction')} | {yn('position')} | {yn('language')} | "
            f"{yn('telegram')} | {yn('whatsapp')} | {score} |"
        )

    failed = [r for r in results if r["verdict"] in ("FAIL", "REVIEW")]
    if failed:
        lines.extend(["", "## FAIL / REVIEW Details", ""])
        for r in failed:
            a = r.get("analysis") or {}
            reasons = a.get("fail_reasons", []) + a.get("review_reasons", [])
            lines.extend([
                f"### [{r['verdict']}] #{r['id']} — {r['title']}",
                "",
                "**Error reasons:**",
                "",
            ])
            for reason in reasons or [r.get("error") or "Unknown"]:
                lines.append(f"- {reason}")
            lines.extend([
                "",
                "**Raw text:**",
                "",
                "```",
                r["raw_text"],
                "```",
                "",
                "**Structured JSON:**",
                "",
                "```json",
                json.dumps(r.get("structured") or {}, ensure_ascii=False, indent=2),
                "```",
                "",
            ])
            if r.get("generated"):
                lines.extend([
                    "**Telegram (preview):**",
                    "",
                    "```",
                    (r["generated"].get("telegram_text") or "")[:500],
                    "```",
                    "",
                ])

    passed = [r for r in results if r["verdict"] == "PASS"]
    if passed:
        lines.extend(["", "## PASS Samples", ""])
        for r in passed:
            lines.append(f"- #{r['id']} {r['title']} (score {r.get('analysis', {}).get('completeness_score', '?')}/100)")

    return "\n".join(lines)


async def main():
    from parser import gpt_configured

    if not gpt_configured():
        print("ERROR: OPENAI_API_KEY not set in .env")
        sys.exit(1)

    samples = load_samples()
    print(f"Running {len(samples)} samples through full pipeline…")

    results = []
    for i, sample in enumerate(samples, 1):
        print(f"  [{i}/{len(samples)}] #{sample['id']} {sample['title']}…", flush=True)
        entry = await run_one(sample)
        results.append(entry)
        print(f"    → {entry['verdict']}", flush=True)

    REPORT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = REPORT_DIR / f"pipeline_report_{stamp}.json"
    md_path = REPORT_DIR / f"pipeline_report_{stamp}.md"

    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(results), encoding="utf-8")

    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    print("\n=== DONE ===")
    print(f"PASS:   {counts.get('PASS', 0)}")
    print(f"REVIEW: {counts.get('REVIEW', 0)}")
    print(f"FAIL:   {counts.get('FAIL', 0)}")
    print(f"\nReport: {md_path}")
    print(f"JSON:   {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
