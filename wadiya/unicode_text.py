"""Unicode-aware word/token helpers for search and indexing."""
from __future__ import annotations

import unicodedata


ZWJ = "\u200d"


def is_word_char(ch: str) -> bool:
    if ch == ZWJ:
        return True
    return unicodedata.category(ch)[0] in {"L", "N", "M"}


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []

    for ch in text or "":
        cat = unicodedata.category(ch)

        if cat[0] in {"L", "N"}:
            current.append(ch)
            continue

        if cat[0] == "M":
            if current:
                current.append(ch)
            continue

        if ch == ZWJ:
            if current:
                current.append(ch)
            continue

        if current:
            if current[-1] == ZWJ:
                current.pop()
            if current:
                tokens.append("".join(current))
            current = []

    if current:
        if current[-1] == ZWJ:
            current.pop()
        if current:
            tokens.append("".join(current))

    return tokens


def token_spans(text: str):
    start = None
    last_word = False

    for i, ch in enumerate(text or ""):
        cat = unicodedata.category(ch)
        word = cat[0] in {"L", "N"}
        mark = cat[0] == "M"
        zwj = ch == ZWJ

        if word:
            if start is None:
                start = i
            last_word = True
            continue

        if mark or (zwj and last_word):
            if start is not None:
                last_word = last_word or mark
            continue

        if start is not None:
            end = i
            if end > start and text[end - 1] == ZWJ:
                end -= 1
            if end > start:
                yield start, end, text[start:end]
            start = None
            last_word = False

    if start is not None:
        end = len(text)
        if end > start and text[end - 1] == ZWJ:
            end -= 1
        if end > start:
            yield start, end, text[start:end]


def is_word_text(text: str) -> bool:
    chars = [ch for ch in text or "" if ch != ZWJ]
    return bool(chars) and all(
        unicodedata.category(ch)[0] in {"L", "N", "M"} for ch in chars
    )
