import unittest

from wadiya.ranking.evaluation import mean_reciprocal_rank, precision_at_k
from tests.test_search_stack import SearchStackCase


class RankingEvaluationTests(unittest.TestCase):
    def test_precision_at_k(self):
        self.assertEqual(precision_at_k(["a", "b", "c"], {"a", "c"}, 3), 2 / 3)
        self.assertEqual(precision_at_k(["a", "b"], {"a"}, 1), 1.0)
        self.assertEqual(precision_at_k([], {"a"}, 10), 0.0)

    def test_mean_reciprocal_rank(self):
        self.assertEqual(
            mean_reciprocal_rank(
                [["a", "b"], ["x", "b"], ["x", "y"]],
                [{"a"}, {"b"}, {"z"}],
            ),
            (1.0 + 0.5 + 0.0) / 3,
        )
        self.assertEqual(mean_reciprocal_rank([], []), 0.0)


class RankingEvaluationIntegrationTests(SearchStackCase):
    def test_search_evaluation_metrics(self):
        docs = {
            "python": self.add(
                url="https://e.org/python",
                title="Python programming",
                content="python programming language",
            ),
            "sqlite": self.add(
                url="https://e.org/sqlite",
                title="SQLite database",
                content="sqlite database storage",
            ),
            "fastapi": self.add(
                url="https://e.org/fastapi",
                title="FastAPI web framework",
                content="fastapi python web",
            ),
        }
        self.build()

        cases = [
            ("python", {docs["python"], docs["fastapi"]}),
            ("sqlite", {docs["sqlite"]}),
            ("fastapi", {docs["fastapi"]}),
        ]

        ranked_lists = []
        relevant_sets = []

        for query, relevant in cases:
            result = self.svc.search(query)
            ids = [
                self.indexer.search(
                    __import__("wadiya.query.parser", fromlist=["parse_query"]).parse_query(query),
                    10,
                ).hits[i].doc_id
                for i in range(min(len(result["results"]), 10))
            ]
            ranked_lists.append(ids)
            relevant_sets.append(relevant)

        self.assertGreaterEqual(
            precision_at_k(ranked_lists[0], relevant_sets[0], 10), 0.1
        )
        self.assertGreater(mean_reciprocal_rank(ranked_lists, relevant_sets), 0.0)


if __name__ == "__main__":
    unittest.main()
