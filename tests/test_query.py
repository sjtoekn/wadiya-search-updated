import unittest

from wadiya.query.parser import QueryError, parse_query


class QueryTests(unittest.TestCase):
    def test_normalization_and_tokenization(self):
        q = parse_query("  Hello,   WORLD!!  ")
        self.assertEqual((q.normalized, q.terms), ("hello, world!!", ("hello", "world")))

    def test_repeated_terms(self):
        q = parse_query("wadi wadi River wadi")
        self.assertEqual(q.terms, ("wadi", "river"))
        self.assertEqual(dict(q.term_counts), {"wadi": 3, "river": 1})

    def test_phrases(self):
        q = parse_query('"dry riverbed" flood "x" "  "')
        self.assertEqual(q.phrases, (("dry", "riverbed"),))
        self.assertEqual(set(q.terms), {"flood", "x"})      # one-word "phrase" -> ordinary term
        self.assertEqual(set(q.all_terms), {"flood", "x", "dry", "riverbed"})
        self.assertEqual(parse_query('"unbalanced quote here').terms, ("unbalanced", "quote", "here"))

    def test_unicode_and_control_chars(self):
        self.assertEqual(parse_query("Ｃａｆé\x00 NAÏVE").terms, ("café", "naïve"))   # NFKC + casefold
        self.assertEqual(parse_query("日本語 検索").terms, ("日本語", "検索"))

    def test_invalid(self):
        for bad in ["", "   ", "!!! ??? ...", "___", None, 123, "x" * 201]:
            with self.assertRaises(QueryError, msg=repr(bad)):
                parse_query(bad)

    def test_limits(self):
        q = parse_query(" ".join(f"w{i}" for i in range(60)), max_length=1000, max_terms=32)
        self.assertEqual(len(q.terms), 32)
        self.assertEqual(parse_query("a " + "z" * 100).terms, ("a",))       # absurd tokens dropped

    def test_fts_syntax_is_inert(self):
        q = parse_query('title:foo OR NEAR(a b) -x * "y z" AND')
        self.assertTrue(all(t.isalnum() for t in q.all_terms))


if __name__ == "__main__":
    unittest.main()
