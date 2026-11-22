#!/usr/bin/env python3
"""Convert Zayktop data (read-only) into a Wadiya database. Run without --apply first."""
import argparse
import hashlib
import os
import sqlite3
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

# Edit this if Wadiya uses different status names for the urls table.
def map_status(s):
    s = (s or "").lower()
    if s in ("done", "ok", "fetched", "crawled", "success"):
        return "done"
    if s in ("failed", "error", "dead", "gone"):
        return "failed"
    return "pending"

def iso(ts=None):
    try:
        if ts:
            return datetime.fromtimestamp(float(ts), timezone.utc).isoformat()
    except Exception:
        pass
    return datetime.now(timezone.utc).isoformat()

def ro(path):
    c = sqlite3.connect("file:%s?immutable=1" % os.path.abspath(path), uri=True)
    c.row_factory = sqlite3.Row
    return c

def domain_of(u):
    try:
        return (urlsplit(u).hostname or "").lower()
    except Exception:
        return ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zay", required=True)
    ap.add_argument("--crawler", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    src = ro(a.zay)
    fr = ro(a.crawler)

    n_pages = src.execute("SELECT count(*) FROM pages").fetchone()[0]
    n_imgs = src.execute("SELECT count(*) FROM images").fetchone()[0]
    kinds = fr.execute("SELECT kind, count(*) FROM frontier GROUP BY 1").fetchall()
    stats = fr.execute("SELECT status, count(*) FROM frontier WHERE kind='page' GROUP BY 1").fetchall()
    print("pages:", n_pages, "images:", n_imgs)
    print("frontier kinds:", [(r[0], r[1]) for r in kinds])
    print("frontier page statuses -> mapped:")
    for r in stats:
        print("  %-12s %8d -> %s" % (r[0], r[1], map_status(r[0])))

    if not a.apply:
        print("\nDry run only. Add --apply to write.")
        return

    dst = sqlite3.connect(a.out)
    have = {r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("documents", "document_images", "urls"):
        if t not in have:
            sys.exit("Missing table %s in %s. Run: python -m wadiya init" % (t, a.out))
    if dst.execute("SELECT count(*) FROM documents").fetchone()[0] > 0:
        sys.exit("Target documents table is not empty. Stopping to avoid mixing data.")

    now = iso()
    ins = skipped = 0
    q = ("SELECT p.url, p.title, p.text, m.lang, m.content_hash, m.canonical, "
         "m.description, m.parsed_at FROM pages p LEFT JOIN page_meta m ON m.url = p.url")
    sql = ("INSERT INTO documents (url, canonical_url, domain, title, description, headings, "
           "content, language, status, content_hash, crawled_at, updated_at, indexed_at, "
           "fail_count, nosnippet) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")
    for r in src.execute(q):
        url = r["url"]
        text = r["text"] or ""
        h = r["content_hash"] or hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()
        ts = iso(r["parsed_at"])
        canon = r["canonical"] or url
        for c in (canon, url):
            try:
                dst.execute(sql, (url, c, domain_of(url), r["title"] or "", r["description"] or "",
                                  "", text, r["lang"], "ok", h, ts, ts, None, 0, 0))
                ins += 1
                break
            except sqlite3.IntegrityError:
                if c == url:
                    skipped += 1
    dst.commit()
    print("documents inserted:", ins, "skipped (duplicates):", skipped)

    ids = {r[1]: r[0] for r in dst.execute("SELECT id, url FROM documents")}
    pos = {}
    img_ok = img_orphan = 0
    for r in src.execute("SELECT url, page_url, alt FROM images ORDER BY id"):
        did = ids.get(r["page_url"])
        if did is None:
            img_orphan += 1
            continue
        pos[did] = pos.get(did, 0) + 1
        dst.execute("INSERT OR IGNORE INTO document_images (document_id, image_url, source_page_url, "
                    "source_domain, alt_text, title, position, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (did, r["url"], r["page_url"], domain_of(r["page_url"]), r["alt"] or "", "", pos[did], now))
        img_ok += 1
    dst.commit()
    print("images inserted:", img_ok, "orphan (page missing):", img_orphan)

    n = 0
    cur = fr.execute("SELECT url, host, depth, status, attempts, discovered, last_fetched "
                     "FROM frontier WHERE kind='page'")
    while True:
        rows = cur.fetchmany(5000)
        if not rows:
            break
        dst.executemany(
            "INSERT OR IGNORE INTO urls (url, domain, depth, status, attempts, added_at, last_attempt_at) "
            "VALUES (?,?,?,?,?,?,?)",
            [(x["url"], x["host"] or domain_of(x["url"]), x["depth"] or 0, map_status(x["status"]),
              x["attempts"] or 0, iso(x["discovered"]), iso(x["last_fetched"]) if x["last_fetched"] else None)
             for x in rows])
        n += len(rows)
    dst.commit()
    print("urls processed:", n)
    print("DONE. Now run: python -m wadiya reindex")

main()
