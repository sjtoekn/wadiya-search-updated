"""Query interpretation only: normalization, tokenization, phrases and search operators."""
from __future__ import annotations

import re
import unicodedata

from ..unicode_text import tokenize
from dataclasses import dataclass

_PHRASE = re.compile(r'"([^"]*)"')
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_OPERATOR = re.compile(r"(?<!\S)(-?)(site|intitle|filetype):([^\s]+)", re.I)
MAX_TOKEN_LEN = 64


class QueryError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedQuery:
    raw: str
    normalized: str
    terms: tuple
    phrases: tuple
    term_counts: tuple
    excluded_terms: tuple = ()
    sites: tuple = ()
    title_terms: tuple = ()
    filetypes: tuple = ()

    @property
    def is_empty(self) -> bool:
        return not self.terms and not self.phrases and not self.title_terms

    @property
    def all_terms(self) -> tuple:
        out = list(self.terms)
        for p in self.phrases:
            out += [t for t in p if t not in out]
        out += [t for t in self.title_terms if t not in out]
        return tuple(out)


def normalize(raw: str) -> str:
    s = unicodedata.normalize("NFKC", raw).casefold()
    return " ".join(_CTRL.sub(" ", s).split())


def _tokens(text: str) -> list:
    return [t for t in tokenize(text) if len(t) <= MAX_TOKEN_LEN]


def parse_query(raw, max_length: int = 200, max_terms: int = 32) -> ParsedQuery:
    if not isinstance(raw, str):
        raise QueryError("query must be text")
    if len(raw) > max_length:
        raise QueryError(f"query too long (max {max_length} characters)")

    norm = normalize(raw)
    if not norm:
        raise QueryError("empty query")

    phrases, terms, counts = [], [], {}
    excluded, sites, title_terms, filetypes = [], [], [], []

    def add_term(t):
        counts[t] = counts.get(t, 0) + 1
        if t not in terms:
            terms.append(t)

    def add_unique(target, value):
        if value and value not in target:
            target.append(value)

    # Operators are recognized only at token boundaries. Their values are
    # normalized and tokenized, so raw FTS syntax can never pass through.
    operator_spans = []
    for m in _OPERATOR.finditer(norm):
        sign, kind, value = m.groups()
        kind = kind.casefold()
        value_tokens = _tokens(value)

        if not value_tokens:
            continue

        operator_spans.append(m.span())

        if kind == "site":
            if sign:
                raise QueryError("site: does not support exclusion")
            site = value.casefold().strip().lstrip(".")
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", site):
                raise QueryError("invalid site operator")
            add_unique(sites, site)

        elif kind == "intitle":
            target = excluded if sign else title_terms
            for token in value_tokens:
                add_unique(target, token)

        elif kind == "filetype":
            if sign:
                raise QueryError("filetype: does not support exclusion")
            add_unique(filetypes, value_tokens[0].lstrip("."))

    # Remove recognized operator text before ordinary parsing.
    stripped = list(norm)
    for start, end in operator_spans:
        for i in range(start, end):
            stripped[i] = " "
    remaining = "".join(stripped)

    # Explicitly excluded terms: -word
    for m in re.finditer(r"(?<!\S)-([^\s]+)", remaining):
        for token in _tokens(m.group(1)):
            add_unique(excluded, token)

    remaining = re.sub(r"(?<!\S)-([^\s]+)", " ", remaining)

    # Quoted phrases.
    for m in _PHRASE.finditer(remaining):
        toks = tuple(_tokens(m.group(1)))
        if len(toks) >= 2:
            if toks not in phrases:
                phrases.append(toks)
        elif len(toks) == 1:
            add_term(toks[0])

    # Ordinary terms.
    for t in _tokens(_PHRASE.sub(" ", remaining).replace('"', " ")):
        add_term(t)

    q = ParsedQuery(
        raw=raw,
        normalized=norm,
        terms=tuple(terms[:max_terms]),
        phrases=tuple(phrases[:8]),
        term_counts=tuple((t, counts[t]) for t in terms[:max_terms]),
        excluded_terms=tuple(excluded[:max_terms]),
        sites=tuple(sites[:8]),
        title_terms=tuple(title_terms[:max_terms]),
        filetypes=tuple(filetypes[:8]),
    )

    if q.is_empty and not q.excluded_terms and not q.sites and not q.filetypes:
        raise QueryError("query has no searchable terms")

    return q
