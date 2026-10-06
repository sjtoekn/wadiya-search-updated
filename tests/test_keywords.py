import unittest

from wadiya.crawler.keywords import extract_keywords


class KeywordExtractionTests(unittest.TestCase):
    def test_title_and_headings_have_stronger_evidence_than_body(self):
        keywords = extract_keywords(
            title="Canadian Travel Guide",
            headings=["Travel in Canada", "Canadian destinations"],
            description="A practical travel guide.",
            content=(
                "travel travel travel travel travel travel "
                "unrelated unrelated unrelated"
            ),
            limit=8,
        )

        self.assertIn("canadian", keywords)
        self.assertIn("travel", keywords)

        if "unrelated" in keywords:
            self.assertLess(keywords.index("canadian"), keywords.index("unrelated"))

    def test_stopwords_are_removed(self):
        keywords = extract_keywords(
            title="The Best Hotels in Canada",
            description="Find the best hotels for your trip.",
            limit=10,
        )

        self.assertNotIn("the", keywords)
        self.assertNotIn("in", keywords)
        self.assertNotIn("for", keywords)
        self.assertIn("hotels", keywords)
        self.assertIn("canada", keywords)

    def test_keywords_are_evidence_only(self):
        keywords = extract_keywords(
            title="Wadi Rivers",
            headings=["Flash Floods"],
            description="Dry riverbeds after rain.",
            content="Wadis are found in arid regions.",
            limit=20,
        )

        allowed = {
            "wadi",
            "rivers",
            "flash",
            "floods",
            "dry",
            "riverbeds",
            "after",
            "rain",
            "wadis",
            "found",
            "arid",
            "regions",
            "wadi rivers",
            "flash floods",
            "dry riverbeds",
            "arid regions",
        }

        self.assertTrue(set(keywords).issubset(allowed))

    def test_repetition_does_not_overwhelm_title_signal(self):
        keywords = extract_keywords(
            title="Canadian Tourism",
            content=("spam " * 200) + ("tourism " * 5),
            limit=5,
        )

        self.assertEqual(keywords[0], "canadian")
        self.assertIn("tourism", keywords)

    def test_headings_accept_list(self):
        keywords = extract_keywords(
            title="",
            headings=["Python Programming", "Web Development"],
            description="",
            content="",
            limit=10,
        )

        self.assertIn("python", keywords)
        self.assertIn("programming", keywords)
        self.assertIn("web", keywords)
        self.assertIn("development", keywords)

    def test_phrases_can_be_returned_from_strong_evidence(self):
        keywords = extract_keywords(
            title="Canadian Travel Guide",
            headings=["Canadian Travel Guide"],
            description="A Canadian travel guide.",
            content="travel guide travel guide",
            limit=10,
        )

        self.assertIn("canadian travel", keywords)
        self.assertIn("travel guide", keywords)

    def test_empty_and_invalid_limits_are_safe(self):
        self.assertEqual(extract_keywords(limit=0), [])
        self.assertEqual(extract_keywords(limit=-1), [])
        self.assertEqual(extract_keywords(limit="10"), [])

    def test_deterministic_order(self):
        args = dict(
            title="Canada Travel",
            headings=["Travel Canada", "Hotels"],
            description="Travel hotels in Canada.",
            content="Canada travel hotels.",
            limit=10,
        )

        self.assertEqual(extract_keywords(**args), extract_keywords(**args))


if __name__ == "__main__":
    unittest.main()
