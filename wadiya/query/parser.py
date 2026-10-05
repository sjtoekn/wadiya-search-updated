"""Query interpretation only: normalization, tokenization, phrases. Knows nothing about FTS syntax."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_PHRASE = re.compile(r'"([^"]*)"')
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
MAX_TOKEN_LEN = 64


class QueryError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedQuery:
    raw: str
    normalized: str
    terms: tuple          # unique single terms, in first-seen order
    phrases: tuple        # tuple of token-tuples (2+ tokens each)
    term_counts: tuple    # ((term, occurrences), ...) -- repeated-term information

    @property
    def is_empty(self) -> bool:
        return not self.terms and not self.phrases

    @property
    def all_terms(self) -> tuple:
        """Every distinct token (for snippet building / highlighting)."""
        out = list(self.terms)
        for p in self.phrases:
            out += [t for t in p if t not in out]
        return tuple(out)


def normalize(raw: str) -> str:
    s = unicodedata.normalize("NFKC", raw).casefold()
    return " ".join(_CTRL.sub(" ", s).split())


def _tokens(text: str) -> list:
    return [t for t in _TOKEN.findall(text) if len(t) <= MAX_TOKEN_LEN]


def parse_query(raw, max_length: int = 200, max_terms: int = 32) -> ParsedQuery:
    if not isinstance(raw, str):
        raise QueryError("query must be text")
    if len(raw) > max_length:
        raise QueryError(f"query too long (max {max_length} characters)")
    norm = normalize(raw)
    if not norm:
        raise QueryError("empty query")

    phrases, terms, counts = [], [], {}

    def add_term(t):
        counts[t] = counts.get(t, 0) + 1
        if t not in terms:
            terms.append(t)

    for m in _PHRASE.finditer(norm):          # "quoted phrases"
        toks = tuple(_tokens(m.group(1)))
        if len(toks) >= 2:
            if toks not in phrases:
                phrases.append(toks)
        elif len(toks) == 1:                    # a one-word "phrase" is an ordinary term
            add_term(toks[0])
    for t in _tokens(_PHRASE.sub(" ", norm).replace('"', " ")):
        add_term(t)                             # repeated terms are counted but searched once

    q = ParsedQuery(raw=raw, normalized=norm, terms=tuple(terms[:max_terms]), phrases=tuple(phrases[:8]),
                    term_counts=tuple((t, counts[t]) for t in terms[:max_terms]))
    if q.is_empty:
        raise QueryError("query has no searchable terms")
    return q
