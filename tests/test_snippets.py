import unittest

from wadiya.search.snippets import make_snippet

TEXT = ("Intro filler " * 30) + "A wadi is a dry riverbed that floods after rain. " + ("More filler " * 40)


class SnippetTests(unittest.TestCase):
    def test_centres_on_match(self):
        s = make_snippet(TEXT, ["riverbed", "wadi"], max_len=120)
        self.assertIn("dry riverbed", s)
        self.assertTrue(s.startswith("…") and s.endswith("…"))
        self.assertLessEqual(len(s), 130)

    def test_fallbacks(self):
        self.assertEqual(make_snippet("nothing relevant here", ["zzz"], fallback="Meta description"), "Meta description")
        self.assertTrue(make_snippet("word " * 200, ["zzz"], max_len=50).endswith("…"))
        self.assertEqual(make_snippet("", ["a"]), "")

    def test_prefers_window_with_more_terms(self):
        text = "alpha " + "x " * 200 + "alpha beta gamma together here " + "y " * 200
        s = make_snippet(text, ["alpha", "beta", "gamma"], max_len=80)
        self.assertIn("beta", s)


if __name__ == "__main__":
    unittest.main()
