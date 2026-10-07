from wadiya.unicode_text import tokenize, is_word_text
from wadiya.query.parser import parse_query
from wadiya.crawler.keywords import extract_keywords
from wadiya.search.snippets import make_snippet


CASES = [
    ("සිංහල", "මෙය සිංහල භාෂාවකි."),
    ("தமிழ்", "இது தமிழ் மொழி."),
    ("हिन्दी", "यह हिन्दी भाषा है."),
    ("বাংলা", "এটি বাংলা ভাষা."),
    ("తెలుగు", "ఇది తెలుగు భాష."),
    ("ಕನ್ನಡ", "ಇದು ಕನ್ನಡ ಭಾಷೆ."),
    ("മലയാളം", "ഇത് മലയാളം ഭാഷയാണ്."),
    ("ไทย", "นี่คือภาษาไทย."),
    ("العربية", "هذه هي اللغة العربية."),
    ("中文", "这是中文语言."),
    ("日本語", "これは日本語です."),
    ("한국어", "이것은 한국어입니다."),
    ("русский", "Это русский язык."),
    ("Français", "Ceci est français."),
    ("Español", "Esto es español."),
    ("Deutsch", "Das ist Deutsch."),
]


def test_all_scripts_tokenize_as_words():
    for word, _ in CASES:
        assert tokenize(word) == [word], word
        assert is_word_text(word), word


def test_all_scripts_parse_as_search_terms():
    for word, _ in CASES:
        assert parse_query(word).terms == (word.casefold(),), word


def test_all_scripts_extract_keywords():
    for word, _ in CASES:
        assert word.casefold() in extract_keywords(title=word), word


def test_all_scripts_snippets_match():
    for word, text in CASES:
        result = make_snippet(text, [word])
        assert word.casefold() in result.casefold(), word
