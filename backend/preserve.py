"""Ensure rewritten full outputs retain every substantive line from the source."""

from __future__ import annotations

import re

from language import detect_dominant_language

MIN_LINE_LEN = 4
WORD_RE = re.compile(r"[\w\u0400-\u04FF]+", re.UNICODE)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _words(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text) if len(w) > 2]


def _line_preserved(line: str, corpus: str) -> bool:
    line_n = _normalize(line)
    corpus_n = _normalize(corpus)
    if not line_n:
        return True
    if line_n in corpus_n:
        return True
    words = _words(line)
    if not words:
        return True
    hits = sum(1 for w in words if w in corpus_n)
    return hits / len(words) >= 0.55


def _is_critical_line(line: str) -> bool:
    if re.search(r"\d{8,}", line):
        return True
    if "@" in line or "instagram" in line.lower():
        return True
    return False


def _missing_lines(source: str, corpus: str) -> list[str]:
    missing: list[str] = []
    seen: set[str] = set()
    for raw in source.splitlines():
        line = raw.strip()
        if len(line) < MIN_LINE_LEN and not _is_critical_line(line):
            continue
        key = _normalize(line)
        if key in seen:
            continue
        seen.add(key)
        if not _line_preserved(line, corpus):
            missing.append(line)
    return missing


def _append_block(text: str, missing: list[str], label: str) -> str:
    if not missing:
        return text
    block = "\n".join(f"• {line}" if not line.startswith(("•", "-", "*")) else line for line in missing)
    base = (text or "").rstrip()
    header = f"\n\n{label}\n"
    return f"{base}{header}{block}".strip()


def preserve_full_outputs(
    source: str,
    clean_full_text: str,
    telegram_text: str,
    whatsapp_text: str,
) -> tuple[str, str, str]:
    """
    Append any source lines not found in full outputs.
    poster_text is intentionally excluded — it may show key fields only.
    """
    source = (source or "").strip()
    if not source:
        return clean_full_text, telegram_text, whatsapp_text

    clean = clean_full_text or ""
    tg = telegram_text or ""
    wa = whatsapp_text or ""
    combined = "\n".join([clean, tg, wa])

    missing = _missing_lines(source, combined)
    if not missing:
        return clean, tg, wa

    lang = detect_dominant_language(source)
    label = "Бастапқы мәтіннен (сақталған):" if lang == "kazakh" else "Из исходного текста (сохранено):"

    clean = _append_block(clean, missing, label)
    tg = _append_block(tg, missing, label)
    wa = _append_block(wa, missing, label)
    return clean, tg, wa
