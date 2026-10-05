import os

from tests.mock_site import MockSite
from wadiya.config.settings import Settings
from wadiya.crawler.crawler import Crawler
from wadiya.crawler.fetcher import Fetcher
from wadiya.crawler.robots import RobotsChecker


def page(title, body, extra_head="", links=()):
    anchors = " ".join(f'<a href="{l}">link</a>' for l in links)
    return ("text/html; charset=utf-8",
            f"<html lang='en'><head><title>{title}</title>{extra_head}</head><body><main><h1>{title}</h1>"
            f"<p>{body}</p>{anchors}</main></body></html>", {})


def site_routes():
    r = {"/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /private\nCrawl-delay: 0\n", {})}
    # (status, ctype, body, headers) tuples
    r["/"] = (200, *page("Wadiya Home", "Welcome to the home page of the test site about deserts and rivers.",
                         links=["/a", "/b", "/private/secret", "/noindex", "/dup", "/missing", "/file.pdf",
                                "/redir", "https://elsewhere.invalid/x", "/a?utm_source=news"]))
    r["/a"] = (200, *page("Wadi guide", "A wadi is a dry riverbed that floods after heavy rain in arid regions.",
                          '<link rel="canonical" href="/a">', ["/deep"]))
    r["/b"] = (200, *page("Oasis facts", "An oasis is a fertile spot in a desert where water is found."))
    r["/deep"] = (200, *page("Deep page", "Reachable only at depth two from the home page via the wadi guide."))
    r["/private/secret"] = (200, *page("Secret", "SECRETCONTENT should never be crawled."))
    r["/noindex"] = (200, *page("Hidden", "NOINDEXCONTENT must not be stored.", '<meta name="robots" content="noindex">'))
    r["/dup"] = (200, *page("Wadi guide", "A wadi is a dry riverbed that floods after heavy rain in arid regions.", links=["/deep"]))
    r["/redir"] = (301, None, "", {"Location": "http://localhost:{base_port}/offsite"})
    return r


class Env:
    """Wires a crawler against a MockSite with the (test-only) private-network policy."""
    def __init__(self, tmp_settings, site, **overrides):
        base = dict(allow_private_networks=True, allowed_ports=None, default_crawl_delay=0.0,
                    retry_backoff=0.0, max_retries=0, request_timeout=3.0)
        base.update(overrides)
        self.settings = Settings(**{**tmp_settings.__dict__, **base})
        self.fetcher = Fetcher(self.settings, sleep=lambda s: None)
        self.robots = RobotsChecker(self.fetcher, self.settings.robots_token)
        self.site = site

    def crawler(self, storage, **kw):
        return Crawler(self.settings, storage, self.fetcher, self.robots, **kw)
