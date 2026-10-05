import os
import tempfile
import shutil
import unittest

from wadiya.config.settings import Settings
from wadiya.storage.base import Document
from wadiya.storage.sqlite_store import SQLiteStorage


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wadiya-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.settings = Settings(db_path=os.path.join(self.tmp, "w.db"),
                                 index_path=os.path.join(self.tmp, "i.db"))
        self.storage = SQLiteStorage(self.settings.db_path)
        self.storage.init()


def make_doc(url="https://example.org/a", canonical=None, title="T", content="hello world",
             domain=None, chash=None, headings="", description=""):
    import hashlib
    from urllib.parse import urlparse
    domain = domain or urlparse(url).netloc
    return Document(id=None, url=url, canonical_url=canonical or url, domain=domain, title=title,
                    description=description, content=content, language="en", status="ok",
                    content_hash=chash or hashlib.sha256(content.encode()).hexdigest(),
                    crawled_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00",
                    headings=headings)
