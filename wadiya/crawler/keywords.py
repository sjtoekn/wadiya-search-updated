"""Deterministic keyword extraction from already-extracted page evidence."""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from ..unicode_text import tokenize

_STOPWORDS = frozenset(
    """
    a an and are as at be been being but by can could did do does for from had
    has have he her here hers him his how i if in into is it its itself just me
    my no not of on or our ours she should so than that the their theirs them
    then there these they this those to too was we were what when where which
    who why will with you your yours
    about after all also am any because before both each few get got
    more most other over own same some such very
    the le la les un une des de du et est en dans pour par avec sur au aux
    ce ces cette il elle ils elles nous vous je tu son sa ses leur leurs
    que qui quoi où ou
    """.split()
)

_MIN_TOKEN_LEN = 2
_MAX_TOKEN_LEN = 48
_DEFAULT_LIMIT = 12
_MAX_REPETITION_CREDIT = 4


def _tokens(text: str) -> list[str]:
    return [
        token.casefold()
        for token in tokenize(text or "")
        if _MIN_TOKEN_LEN <= len(token) <= _MAX_TOKEN_LEN
        and token.casefold() not in _STOPWORDS
    ]


def _score_field(text: str, weight: float) -> Counter[str]:
    counts = Counter(_tokens(text))
    scores: Counter[str] = Counter()

    for token, count in counts.items():
        repetition = min(count - 1, _MAX_REPETITION_CREDIT)
        scores[token] = weight + repetition * 0.25

    return scores


def _phrases(text: str) -> Iterable[str]:
    tokens = _tokens(text)

    for left, right in zip(tokens, tokens[1:]):
        if left != right:
            yield f"{left} {right}"


def extract_keywords(
    *,
    title: str = "",
    headings: str | Iterable[str] = "",
    description: str = "",
    content: str = "",
    limit: int = _DEFAULT_LIMIT,
) -> list[str]:
    """Return deterministic, evidence-backed keywords.

    Evidence priority is title > headings > description > body.
    Repetition is deliberately bounded so body keyword stuffing cannot
    overpower stronger metadata evidence.
    """

    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        return []

    if isinstance(headings, str):
        heading_values = [headings]
    else:
        heading_values = list(headings or [])

    # For each term keep the strongest source where it appears.
    evidence: dict[str, tuple[int, float]] = {}

    fields = [
        (title, 4, 8.0),
        *[(heading, 3, 5.0) for heading in heading_values],
        (description, 2, 3.0),
        (content, 1, 1.0),
    ]

    for text, level, weight in fields:
        for token, score in _score_field(text, weight).items():
            previous = evidence.get(token)

            if previous is None:
                evidence[token] = (level, score)
            else:
                old_level, old_score = previous

                if level > old_level:
                    evidence[token] = (level, score)
                elif level == old_level:
                    evidence[token] = (old_level, max(old_score, score))

    terms = [
        (level, score, token)
        for token, (level, score) in evidence.items()
    ]

    # Stronger evidence first. Deterministic alphabetical tie-break.
    terms.sort(key=lambda item: (-item[0], -item[1], item[2]))

    # Strong metadata phrases are supplemental candidates.
    phrases: list[tuple[int, float, str]] = []

    for text, level, weight in [
        (title, 4, 4.0),
        *[(heading, 3, 2.5) for heading in heading_values],
        (description, 2, 1.5),
    ]:
        counts = Counter(_phrases(text))

        for phrase, count in counts.items():
            score = weight + min(count - 1, 2) * 0.25
            if score >= 4.0:
                phrases.append((level, score, phrase))

    phrases.sort(key=lambda item: (-item[0], -item[1], item[2]))

    # Individual terms are primary. Phrases are added after them, while
    # retaining the evidence hierarchy.
    candidates = terms + phrases
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))

    result: list[str] = []
    seen = set()

    for _, _, keyword in candidates:
        if keyword in seen:
            continue

        seen.add(keyword)
        result.append(keyword)

        if len(result) >= limit:
            break

    return result
