# Wadiya — Product Vision

## What Wadiya Is

Wadiya is an independent web search and discovery project.

Wadiya is NOT intended to be a clone of Google, Bing, DuckDuckGo, or any other existing search engine.

We study the strongest ideas from search engines, web directories, discovery systems, publisher tools, and emerging search technologies. We take what is useful, reject what does not fit, and build a different approach of our own.

## Core Principle

> Wadiya should help people discover the web, not replace the web.

The web already contains websites, information, businesses, communities, documents, services, and many other resources.

Wadiya should help people discover useful resources, understand where information comes from, and reach the original source.

Wadiya should therefore favor:

- useful source discovery
- original websites
- source attribution
- exploration and comparison
- discovery of smaller or less-visible websites
- better publisher discoverability

## What Wadiya Is Not

Wadiya should not become:

- a Google clone
- a Bing clone
- a simple directory clone
- a ChatGPT clone
- an AI answer engine that hides the original web
- a system designed mainly to keep users inside Wadiya

Learning from existing products is encouraged.

Copying them is not the goal.

## Learn From the Best

Wadiya can learn from:

- web crawling
- search indexes
- relevance ranking
- link discovery
- XML sitemaps
- RSS/Atom feeds
- publisher submissions
- publisher notifications
- freshness detection
- duplicate detection
- local discovery
- search suggestions
- query understanding
- structured data
- source attribution
- user-assisted discovery
- AI-assisted search
- knowledge graphs

The question should not be:

> How do we copy this feature?

The question should be:

> What problem does this solve, and can Wadiya solve that problem in a better or different way?

## Discovery Philosophy

Traditional search depends heavily on crawlers finding links and revisiting known websites.

Wadiya should eventually build a broader discovery network.

Potential discovery sources include:

1. Links discovered while crawling
2. XML sitemaps
3. RSS/Atom feeds
4. Website submissions
5. Publisher notifications
6. Known URLs
7. User suggestions
8. Search-demand signals
9. Directories and structured sources
10. Other legitimate web discovery mechanisms

The goal is to discover useful parts of the web, including pages and websites that may otherwise receive little visibility.

## Search Is More Than Ranking

Wadiya should not think of search as only:

    query
      ↓
    find documents
      ↓
    rank documents
      ↓
    show results

The larger system should eventually be:

    Discover
      ↓
    Crawl
      ↓
    Extract
      ↓
    Understand
      ↓
    Store
      ↓
    Index
      ↓
    Rank
      ↓
    Present
      ↓
    Learn from demand and freshness
      ↓
    Discover again

Search quality depends on the quality of discovery and indexing behind it.

## Publisher and Source Philosophy

Websites and publishers should be important participants in the Wadiya ecosystem.

Long-term possibilities include:

- Wadiya Submit
- Wadiya Notify
- publisher/webmaster tools
- crawl controls
- publisher identity
- source profiles
- indexing status
- freshness information
- publisher controls
- discovery analytics

The objective is not only to crawl the web.

The objective is to build a healthier relationship between the search engine and the web it indexes.

## AI Philosophy

AI may become an important part of Wadiya.

> AI should help the web, not replace the web.

AI may help with:

- query understanding
- search intent
- ranking signals
- classification
- source understanding
- summarization
- duplicate detection
- freshness detection
- discovery prioritization
- knowledge extraction
- search assistance

Users should still be able to understand where information came from and reach the original source whenever appropriate.

Wadiya should not become a black box that absorbs the web and hides the web.

## Engineering Philosophy

Do not build complexity simply because large search engines use it.

Wadiya should grow according to actual requirements.

Prefer:

    simple
      ↓
    correct
      ↓
    observable
      ↓
    reliable
      ↓
    better discovery
      ↓
    better search quality
      ↓
    greater scale

Every major architectural decision should solve a real problem.

## Development Rule

Each milestone should:

1. Have a clearly defined purpose.
2. Preserve existing working behavior.
3. Add only the necessary complexity.
4. Be tested before moving forward.
5. Avoid unrelated refactoring.
6. Keep replaceable interfaces where practical.
7. Prefer understandable architecture over premature scale.

## Roadmap

### Phase 0 — Core Search Foundation
COMPLETE

### Phase 1 — Search Infrastructure

- M1 — Concurrent crawler workers
- M2 — URL discovery improvements
- M3 — Sitemap / feed discovery
- M4 — Persistent retry / backoff
- M5 — Recrawl scheduler
- M6 — Deduplication improvements
- M7 — Crawl observability
- M8 — Search quality / ranking
- M9 — Scale / storage migration

### Phase 2 — Search Quality

Improve relevance, freshness, diversity, authority, source quality, and usefulness.

### Phase 3 — Open Web Ecosystem

Build stronger discovery and publisher participation mechanisms.

### Phase 4 — Intelligent Search

Introduce intelligent and AI-assisted discovery while preserving source-first principles.

### Phase 5 — Scale

Scale crawling, indexing, storage, and serving according to real demand.

### Phase 6 — Wadiya ↔ NEXORA

Potential future integration between Wadiya and NEXORA.

This should not affect the current Wadiya architecture prematurely.

## Decision Rule for Future Developers

Before adding a major feature, ask:

1. Does this improve web discovery?
2. Does this improve search usefulness?
3. Does this help users reach original sources?
4. Does this help publishers or the web ecosystem?
5. Are we building this for Wadiya, or merely copying another search engine?
6. Is the complexity justified by an actual requirement?

If a feature exists only because another search engine has it, that is not enough justification.

## The Wadiya Goal

The goal is not:

> Build another Google.

The goal is:

> Build a new kind of independent web discovery and search system by learning from what already works, rejecting what does not fit, and creating ideas of our own.

Wadiya should make the web easier to discover while keeping the web itself visible, useful, and connected to its original sources.
