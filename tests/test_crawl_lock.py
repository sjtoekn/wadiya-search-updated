import os
import signal
import subprocess
import sys
import time
import unittest

from tests.crawler_fixtures import Env, site_routes
from tests.helpers import TempDirCase
from tests.mock_site import MockSite
from wadiya.crawler.lock import CrawlAlreadyRunning, CrawlLock
from wadiya.crawler.seeds import Seed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOLDER = ("import sys,time;from wadiya.crawler.lock import CrawlLock;l=CrawlLock(sys.argv[1]);l.__enter__();"
          "print('READY',flush=True);time.sleep(60)")


class CrawlLockTests(TempDirCase):
    def lockpath(self):
        return self.settings.db_path + ".crawl.lock"

    def test_second_lock_in_same_process_is_refused_then_released(self):
        with CrawlLock(self.lockpath()):
            with self.assertRaises(CrawlAlreadyRunning) as cm:
                CrawlLock(self.lockpath()).__enter__()
            self.assertIn(str(os.getpid()), str(cm.exception))             # tells you who holds it
        with CrawlLock(self.lockpath()):                                     # free again after normal exit
            pass

    def test_lock_released_when_the_crawl_raises(self):
        with self.assertRaises(KeyError):
            with CrawlLock(self.lockpath()):
                raise KeyError("boom")
        with CrawlLock(self.lockpath()):
            pass

    def test_crawler_refuses_to_run_and_touches_nothing_while_locked(self):
        with MockSite(site_routes()) as site:
            env = Env(self.settings, site)
            with CrawlLock(env.settings.db_path + ".crawl.lock"):
                with self.assertRaises(CrawlAlreadyRunning):
                    env.crawler(self.storage).run([Seed(site.base + "/")])
            self.assertEqual(site.hits, [])                                  # no request was made
            self.assertIsNone(self.storage.last_run())                        # no crawl_runs row
            self.assertEqual(self.storage.queue_size(), 0)                    # queue untouched (no seed enqueued)
            stats = env.crawler(self.storage).run([Seed(site.base + "/")])    # and it works once the lock is free
            self.assertGreater(stats.stored, 0)

    def test_second_process_cannot_crawl_and_kill9_leaves_no_stale_lock(self):
        env = {**os.environ, "PYTHONPATH": ROOT}
        holder = subprocess.Popen([sys.executable, "-c", HOLDER, self.lockpath()], cwd=ROOT, env=env,
                                  stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), "READY")
            seeds = os.path.join(self.tmp, "seeds.yaml")
            with open(seeds, "w") as f:
                f.write("seeds:\n  - url: https://example.org/\n")
            cli_env = {**env, "WADIYA_DB_PATH": self.settings.db_path, "WADIYA_INDEX_PATH": self.settings.index_path}
            r = subprocess.run([sys.executable, "-m", "wadiya", "crawl", "--seeds", seeds], cwd=ROOT, env=cli_env,
                               capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 3, r.stderr)
            self.assertIn("already running", r.stderr)
            self.assertIn(str(holder.pid), r.stderr)
            with self.assertRaises(CrawlAlreadyRunning):
                CrawlLock(self.lockpath()).__enter__()
            holder.send_signal(signal.SIGKILL)                               # crash, no cleanup code runs
            holder.wait(timeout=10)
            with CrawlLock(self.lockpath()):                                 # OS dropped the lock: nothing stale
                pass
        finally:
            if holder.poll() is None:
                holder.kill()
            holder.stdout.close()


if __name__ == "__main__":
    unittest.main()
