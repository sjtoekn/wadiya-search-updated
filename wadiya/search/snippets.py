"""Snippet generation (independent of ranking and of the index engine)."""
from __future__ import annotations

import re

from ..unicode_text import token_spans

_MAX_MATCHES = 400


def _stem(term: str) -> str:
    return term if len(term) <= 4 else term[: max(4, len(term) - 2)]   # crude: matches plurals / -ing / -ed


def make_snippet(text: str, terms, max_len: int = 220, fallback: str = "") -> str:
    text = " ".join((text or "").split())
    fallback = " ".join((fallback or "").split())
    stems = [_stem(t).casefold() for t in terms if t]
    positions = []
    for start, end, token in token_spans(text):
        folded = token.casefold()
        for i, stem in enumerate(stems):
            if folded.startswith(stem):
                positions.append((start, i))
                if len(positions) >= _MAX_MATCHES:
                    break
        if len(positions) >= _MAX_MATCHES:
            break
    if not positions:
        return _clip(fallback or text, max_len)
    positions.sort()

    best_start, best_score = 0, -1
    wanted = set(range(len(stems)))

    # Prefer the smallest window containing every query term.
    wanted = set(range(len(stems)))
    recent = positions[:200]

    left = 0
    counts = {}
    covered = 0

    for right, (pos, term_index) in enumerate(recent):
        counts[term_index] = counts.get(term_index, 0) + 1
        if counts[term_index] == 1:
            covered += 1

        while covered == len(wanted) and left <= right:
            left_pos = recent[left][0]
            span = pos - left_pos

            if span < max_len:
                best_start = max(0, left_pos - (max_len - span) // 2)
                best_score = len(wanted)
            elif best_score < len(wanted):
                best_start = max(0, left_pos - 40)
                best_score = len(wanted) - 1

            left_term = recent[left][1]
            counts[left_term] -= 1
            if counts[left_term] == 0:
                covered -= 1
            left += 1

    if best_score < len(wanted):
        for pos, _ in recent:
            start = max(0, pos - 40)
            window = {
                i for p, i in positions
                if start <= p < start + max_len
            }
            if len(window) > best_score:
                best_start, best_score = start, len(window)

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
