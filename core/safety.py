from __future__ import annotations
import json
import re
from typing import List, Tuple

PII_PATTERNS = [
    (re.compile(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b"), "[REDACTED_SSN]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:\+?\d{1,3}[- ]?)?(?:\(?\d{2,4}\)?[- ]?)?\d{3,4}[- ]?\d{3,4}\b"), "[REDACTED_PHONE]"),
]

def redact_pii(text: str) -> str:
    redacted = text or ""
    for rx, repl in PII_PATTERNS:
        redacted = rx.sub(repl, redacted)
    return redacted

def safe_json_dumps(obj) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return json.dumps({"error": "non-serializable"}, ensure_ascii=False)

def clamp_text(text: str, max_chars: int) -> str:
    t = str(text or "")
    return t[:max_chars] + ("…" if len(t) > max_chars else "")

def detect_prompt_injection(text: str, blocked_regex: List[str]) -> Tuple[bool, List[str]]:
    hits = []
    for pat in blocked_regex or []:
        try:
            if re.search(pat, text or ""):
                hits.append(pat)
        except re.error:
            continue
    return (len(hits) > 0), hits

def context_firewall(text: str, blocked_regex: List[str]) -> Tuple[str, List[str]]:
    removed = []
    out_lines = []
    for line in (text or "").splitlines():
        inj, _ = detect_prompt_injection(line, blocked_regex)
        if inj:
            removed.append(line)
            continue
        out_lines.append(line)
    return ("\n".join(out_lines)).strip(), removed
