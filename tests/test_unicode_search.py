from wadiya.unicode_text import tokenize, is_word_text
from wadiya.query.parser import parse_query
from wadiya.crawler.keywords import extract_keywords
from wadiya.search.snippets import make_snippet
from wadiya.indexer.fts5 import FTS5Indexer


def test_sinhala_combining_marks_stay_one_token():
    assert tokenize("සිංහල") == ["සිංහල"]
    assert parse_query("සිංහල").terms == ("සිංහල",)


def test_sinhala_phrase_stays_two_words():
    assert tokenize("ශ්‍රී ලංකාව") == ["ශ්‍රී", "ලංකාව"]
    assert parse_query("ශ්‍රී ලංකාව").terms == ("ශ්‍රී", "ලංකාව")


def test_tamil_combining_marks_stay_one_token():
    assert tokenize("தமிழ்") == ["தமிழ்"]
    assert parse_query("தமிழ்").terms == ("தமிழ்",)


def test_zwj_is_kept_inside_word():
    value = "සිංහල‍භාෂාව"
    assert tokenize(value) == [value]
    assert is_word_text(value)


def test_keywords_keep_sinhala_and_tamil():
    assert "සිංහල" in extract_keywords(title="සිංහල")
    assert "தமிழ்" in extract_keywords(title="தமிழ்")


def test_snippet_matches_sinhala():
    assert "සිංහල" in make_snippet("මෙය සිංහල භාෂාවකි.", ["සිංහල"])


def test_snippet_matches_tamil():
    assert "தமிழ்" in make_snippet("இது தமிழ் மொழி.", ["தமிழ்"])


def test_typo_distance_accepts_unicode_words():
    assert FTS5Indexer._typo_distance_one("සිංහල", "සිංහල")
    assert FTS5Indexer._typo_distance_one("தமிழ்", "தமிழ்")
