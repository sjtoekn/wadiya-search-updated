"""Continuous crawl/discovery scheduler.

Runs the existing crawler in repeated cycles so automatically discovered
websites can continuously enter the crawl/index pipeline.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .crawler import Crawler


@dataclass
class SchedulerCycle:
    number: int
    stats: object
    indexed: int


class ContinuousCrawler:
    def __init__(
        self,
        settings,
        storage,
        indexer,
        fetcher,
        robots,
        *,
        books_indexer=None,
        sleep=time.sleep,
    ):
        self.settings = settings
        self.storage = storage
        self.indexer = indexer
        self.fetcher = fetcher
        self.robots = robots
        self.books_indexer = books_indexer
        self._sleep = sleep

    def run(
        self,
        seeds,
        *,
        fresh: bool = False,
        interval: float = 60.0,
        max_cycles: int | None = None,
    ):
        """Run crawl/index cycles until interrupted.

        ``fresh`` only applies to the first cycle. Subsequent cycles reuse
        the existing queue and newly discovered sites.
        """
        cycle = 0

        while max_cycles is None or cycle < max_cycles:
            cycle += 1

            cycle_seeds = seeds if cycle == 1 else []

            requeued = self.storage.requeue_due_urls()
            if requeued:
                print(
                    "requeued due URLs:",
                    requeued,
                    flush=True,
                )

            stats = Crawler(
                self.settings,
                self.storage,
                self.fetcher,
                self.robots,
            ).run(
                cycle_seeds,
                fresh=fresh if cycle == 1 else False,
            )

            indexed = 0
            if self.indexer is not None:
                from ..pipeline import index_pending

                indexed = index_pending(
                    self.storage,
                    self.indexer,
                )

            if self.books_indexer is not None:
                from ..pipeline import sync_books_index

                sync_books_index(
                    self.storage,
                    self.books_indexer,
                )

            yield SchedulerCycle(
                number=cycle,
                stats=stats,
                indexed=indexed,
            )

            if max_cycles is not None and cycle >= max_cycles:
                break

            self._sleep(max(0.0, float(interval)))
