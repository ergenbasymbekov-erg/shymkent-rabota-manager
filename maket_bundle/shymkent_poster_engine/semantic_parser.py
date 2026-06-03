"""AI recruiter parser — semantic decomposition via LLM. Raw text never reaches layout engine."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .confidence import apply_confidence_gate
from .language import Language, section_labels
from .line_coverage import enforce_line_coverage
from .schema import SEMANTIC_PARSER_SYSTEM


class SemanticParseError(Exception):
    pass


def _api_config() -> tuple[str, str, str]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SemanticParseError(
            "OPENAI_API_KEY required for AI recruiter. Set: export OPENAI_API_KEY=sk-..."
        )
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    return api_key, base_url, model


def _call_llm(raw_text: str) -> dict:
    """LLM recruiter — global understanding then semantic decomposition."""
    api_key, base_url, model = _api_config()

    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SEMANTIC_PARSER_SYSTEM},
            {
                "role": "user",
                "content": (
                    "Review this WhatsApp vacancy like a senior HR recruiter.\n\n"
                    "STEP 1: Write 'understanding' — business, role, location, relationships.\n"
                    "STEP 2: Decompose meaning into separate fields (NOT sentence copying).\n"
                    "STEP 3: Score confidence for every field.\n\n"
                    "Example decomposition:\n"
                    '"Тошико Суши Шымкент жеткізу орталығына курьер қажет"\n'
                    "→ company: Тошико Суши | vacancy: Курьер | address_notes: Шымкент жеткізу орталығы\n\n"
                    f"---\n{raw_text.strip()}\n---"
                ),
            },
        ],
    }

    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SemanticParseError(f"AI recruiter HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SemanticParseError(f"AI recruiter network error: {exc}") from exc

    return json.loads(body["choices"][0]["message"]["content"])


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _merge_unsorted(existing: list[str], additions: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in existing + additions:
        text = str(item).strip()
        if text and text not in seen:
            merged.append(text)
            seen.add(text)
    return merged


def normalize_recruiter_json(data: dict) -> dict:
    """Apply confidence gate and shape LLM recruiter output for manager preview."""
    gated, field_confidence, low_conf = apply_confidence_gate(data)

    language = str(gated.get("language", "MIXED")).upper()
    if language not in {l.value for l in Language}:
        language = Language.MIXED.value

    mode = str(gated.get("mode", "SINGLE")).upper()
    vacancies = _as_str_list(gated.get("vacancies"))
    if mode not in ("SINGLE", "MULTI"):
        mode = "MULTI" if len(vacancies) >= 2 else "SINGLE"

    labels = section_labels(Language(language))
    vacancy = str(gated.get("vacancy", "")).strip()
    if mode == "MULTI" and not vacancy:
        vacancy = labels["multi_title"]

    phones = _as_str_list(gated.get("phones"))
    understanding = data.get("understanding") if isinstance(data.get("understanding"), dict) else {}
    line_map = data.get("line_map") if isinstance(data.get("line_map"), list) else []
    llm_unsorted = _as_str_list(data.get("unsorted_review"))

    return {
        "language": language,
        "mode": mode,
        "company": str(gated.get("company", "")).strip(),
        "vacancy": vacancy,
        "vacancies": vacancies,
        "salary": str(gated.get("salary", "")).strip(),
        "requirements_heading": str(gated.get("requirements_heading", "")).strip() or labels["requirements"],
        "requirements": _as_str_list(gated.get("requirements")),
        "responsibilities_heading": str(gated.get("responsibilities_heading", "")).strip() or labels["responsibilities"],
        "responsibilities": _as_str_list(gated.get("responsibilities")),
        "conditions_heading": str(gated.get("conditions_heading", "")).strip() or labels["conditions"],
        "conditions": _as_str_list(gated.get("conditions")),
        "phones": phones,
        "phone": phones[0] if phones else "",
        "address": str(gated.get("address", "")).strip(),
        "address_notes": str(gated.get("address_notes", "")).strip(),
        "instagram": str(gated.get("instagram", "")).strip(),
        "notes": str(gated.get("notes", "")).strip(),
        "unsorted_review": _merge_unsorted(llm_unsorted, low_conf),
        "line_map": line_map,
        "understanding": understanding,
        "field_confidence": field_confidence,
        "needs_review": bool(low_conf or llm_unsorted),
    }


def parse_vacancy_semantic(raw_text: str) -> dict:
    """
    AI recruiter: understand → decompose → confidence gate → preview JSON.
    Layout engine never sees raw text.
    """
    text = raw_text.strip()
    if not text:
        raise SemanticParseError("Empty vacancy text")

    llm_result = _call_llm(text)
    preview = normalize_recruiter_json(llm_result)
    preview = enforce_line_coverage(text, preview)

    if not preview["company"] and not preview["vacancy"] and not preview["vacancies"]:
        if not preview["unsorted_review"]:
            raise SemanticParseError(
                "AI recruiter could not decompose vacancy — complete form manually."
            )

    return preview
