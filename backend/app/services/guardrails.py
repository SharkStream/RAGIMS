"""Input guardrails (N4): prompt-injection sanitization + PII redaction.

Pure functions over text — no I/O, no state. Applied to chat queries and to
retrieved chunk texts before they enter the LLM prompt.

Injection defense is layered (N1 system rules + <ctx> wrapping are layers 1-2);
this module is layer 3: known instruction patterns are neutralized and
zero-width/control characters are stripped so they cannot split keywords or
hide directives from the sanitizer itself.

PII redaction covers the common Chinese-context identifiers (mobile, ID card,
email, bank card). Off by default — enable where compliance requires it.
"""

from __future__ import annotations

import re

from app.core.config import settings
from app.core.metrics import record_request  # noqa: F401  (module conventions)

#: Instruction-shaped patterns that must not survive into LLM context.
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore (all |any |the )?(previous|prior|above) (instructions|prompts|rules)",
        r"disregard (all |any |the )?(previous|prior|above) (instructions|prompts|rules)",
        r"(忽略|无视|不要理会)(以上|上面|之前|先前)?的?(所有)?(指令|提示|规则)",
        r"你现在是|从现在开始你是|act as (an?|the) ",
        r"(system|assistant)\s*(prompt|message)\s*[：:=]",
        r"</?ctx[^>]*>",  # forged citation wrappers
    )
)

#: Zero-width / bidi control characters (invisible injection carriers).
_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")

_PII_RULES: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pattern))
    for label, pattern in (
        ("手机号", r"(?<!\d)1[3-9]\d{9}(?!\d)"),
        ("身份证", r"(?<!\d)\d{17}[\dXx](?!\d)"),
        ("邮箱", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        ("银行卡", r"(?<!\d)\d{16,19}(?!\d)"),
    )
)


def sanitize_injection(text: str) -> tuple[str, bool]:
    """Neutralize injection patterns + invisible chars. Returns (text, hit)."""
    cleaned = _ZERO_WIDTH_RE.sub("", text)
    hit = False
    for pattern in _INJECTION_PATTERNS:
        cleaned, n = pattern.subn("[已过滤的指令]", cleaned)
        if n:
            hit = True
    return cleaned, hit


def redact_pii(text: str) -> tuple[str, int]:
    """Replace PII matches with labeled placeholders. Returns (text, hits)."""
    hits = 0
    for label, pattern in _PII_RULES:
        text, n = pattern.subn(f"[{label}已脱敏]", text)
        hits += n
    return text, hits


def guard_chunk_text(text: str) -> str:
    """Apply configured guards to a retrieved chunk (chat context path)."""
    g = settings.guardrails
    if g.pii_redact:
        text, _ = redact_pii(text)
    if g.sanitize_injection:
        text, _ = sanitize_injection(text)
    return text


def guard_query(text: str) -> str:
    """Apply configured guards to the user query (PII only by default)."""
    if settings.guardrails.pii_redact:
        text, _ = redact_pii(text)
    return text
