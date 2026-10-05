"""Snippet generation (independent of ranking and of the index engine)."""
from __future__ import annotations

import re

_MAX_MATCHES = 400


def _stem(term: str) -> str:
    return term if len(term) <= 4 else term[: max(4, len(term) - 2)]   # crude: matches plurals / -ing / -ed


def make_snippet(text: str, terms, max_len: int = 220, fallback: str = "") -> str:
    text = " ".join((text or "").split())
    fallback = " ".join((fallback or "").split())
    pats = [re.compile(r"\b" + re.escape(_stem(t)), re.I) for t in terms if t]
    positions = []
    for i, p in enumerate(pats):
        for m in p.finditer(text):
            positions.append((m.start(), i))
            if len(positions) >= _MAX_MATCHES:
                break
    if not positions:
        return _clip(fallback or text, max_len)
    positions.sort()

    best_start, best_score = 0, -1
    for pos, _ in positions[:200]:
        start = max(0, pos - 40)
        score = len({i for p, i in positions if start <= p < start + max_len})
        if score > best_score:
            best_start, best_score = start, score
    start, end = best_start, min(len(text), best_start + max_len)
    if start > 0:
        sp = text.find(" ", start)
        start = sp + 1 if 0 <= sp - start < 25 else start
    if end < len(text):
        sp = text.rfind(" ", start, end)
        end = sp if sp > start else end
    return ("… " if start > 0 else "") + text[start:end].strip() + (" …" if end < len(text) else "")


def _clip(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    cut = s.rfind(" ", 0, n)
    return s[: cut if cut > 0 else n].rstrip() + " …"
