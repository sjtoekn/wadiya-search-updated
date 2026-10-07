# Wadiya Project Renewal Notes

This document is a continuing project journal for major renewal, architectural decisions,
new capabilities, important fixes, verification results, and development principles.

The purpose of this file is to preserve project direction and important reasoning so that
development can continue correctly even when the active development session changes.

---

# 2026-10-07 — Project Renewal / Adding New Capabilities

## 1. Project Direction

Wadiya.com is being developed as an independent web discovery and search platform.

The central product idea remains:

> Wadiya should help people discover the web, not replace the web.

The project should remain independent in its product identity, architecture, implementation,
visual language, and user experience.

Wadiya must not become a visual or product clone of Google, another search engine,
a social network, or another existing platform.

The goal is to build Wadiya using our own implementation and engineering decisions,
based on standard engineering principles, public technical standards, security practices,
and original product thinking.

We should not copy implementation details, proprietary designs, proprietary code,
private data, or protected product assets from other projects.

---

## 2. Important Development Principle Agreed Today

We agreed that project development should be documented continuously.

Important discussions, architectural decisions, new capabilities, significant fixes,
verification results, and changes in project direction should be recorded in Markdown
documentation inside the project.

This is especially important because the active development session may eventually
change or reach a limitation. A future development session should be able to read the
project notes and understand:

- what was decided
- why it was decided
- what has already been completed
- what was tested
- what remains incomplete
- what must not be changed
- what the next safe action should be

The documentation is therefore part of the engineering process, not merely optional
documentation.

---

## 3. Development Method

The agreed working method is:

AUDIT
→ IDENTIFY THE PROBLEM
→ MAKE THE SMALLEST NECESSARY CHANGE
→ RUN TARGETED TESTS
→ VERIFY
→ CONTINUE

We should not make speculative changes simply because a change appears attractive.

Before changing an existing subsystem:

1. Read the current implementation.
2. Understand the existing architecture and contracts.
3. Identify the actual problem.
4. Change only what is necessary.
5. Run the smallest relevant test set.
6. Verify the result.
7. Record important changes.
8. Continue to the next blocker.

Unrelated refactoring should be avoided during focused work.

---

## 4. Current Search Verification Checkpoint

The focused search/query verification completed successfully before this note was created.

Command:

    python -m unittest tests.test_query tests.test_search_stack -v

Result:

    Ran 35 tests in 0.435s
    OK

This represents:

- Query tests: 7/7 passed
- Search stack tests: 28/28 passed
- Combined: 35/35 passed

This is an important baseline checkpoint.

The search system currently has verified behavior around query parsing,
search execution, result handling, snippets, response shape, site filtering,
and privacy-conscious query logging covered by this focused test set.

---

## 5. Important Search Engineering Decisions

### Site operator

The production site filter supports matching:

- the exact domain
- www variants
- subdomains

The implementation must not be weakened merely to satisfy a test.

A previous test issue was caused by test fixture content hashes being identical,
which interacted with production content deduplication.

The correct solution was to make the test fixtures represent distinct documents.

Production content deduplication must remain intact.

### Query logging

Query logging is privacy-conscious.

Stored query logs use a SHA-256 hash of the normalized query rather than retaining
the raw query text.

The search service also uses configurable sampling for query logging.

Logging failures must not break search requests.

### Response shape

Optional response fields such as `corrected_query` should only be returned when
the value is actually present.

The API response contract should remain stable and intentional.

---

## 6. Security and Independence

Security must remain part of every future feature.

Important existing principles include:

- SSRF protection
- redirect validation
- DNS rebinding protection
- robots handling
- parameterized SQL
- no untrusted HTML rendering
- secure authentication/session handling
- privacy-conscious query logging
- input validation
- controlled API behavior

Security must not be traded away for convenience or for making a test pass.

Similarly, the project must remain independent from other unrelated projects.

Do not mix Wadiya work with NEXORA, Canda-1, HUB-01, or other project contexts.

---

## 7. Current Product Journey

The intended public discovery journey is:

Home
→ Search / Discover
→ Search Results
→ Website Discovery
→ Website Information
→ Discovered Pages / Content

The product identity remains centered around discovery.

The home concept is:

Title:
    Wadiya.com — discover the web.

Primary message:
    Discover the web

Supporting idea:
    Find websites, topics, places, businesses, and pages worth exploring.

The interface should remain calm, clean, welcoming, polished, and useful without
becoming a copy of an existing search engine.

White surfaces/search areas over a pleasant background can be used where appropriate,
while maintaining Wadiya's own visual identity.

---

## 8. Website Discovery Principles

Website Discovery should expose information that Wadiya actually knows.

Examples include:

- website identity
- discovered page count
- discovered pages
- crawl timestamps
- indexing state when supported
- stored technical information when actually available
- discovery history when actually stored

Wadiya must not pretend that crawler data is website-owner analytics.

Do not invent metrics, APIs, crawl information, or website statistics.

Only display verified information that is actually supported by the system.

---

## 9. Adding New Capabilities

The project is entering a stage where additional capabilities are being added.

Recent areas include:

- multilingual / Unicode support
- Unicode-aware search testing
- user authentication
- login
- registration
- profile functionality
- Website Discovery
- search and query improvements
- continued security and API work

These areas must be audited before additional layers are built on top of them.

A feature being present in the source tree does not automatically mean that it is
complete or production-ready.

Each capability should be verified through:

1. source audit
2. API/contract audit
3. security review
4. focused tests
5. browser/UI verification where applicable
6. regression testing
7. documentation

---

## 10. Git Checkpoint Rule

From this point forward, every significant completed change should have a clear
Git checkpoint.

A significant change includes, for example:

- an important bug fix
- a completed feature
- a security fix
- a meaningful architecture change
- a completed UI/UX section
- a search/ranking change
- an authentication change
- a major API contract change
- a verified milestone

The corresponding project note should mention the checkpoint and explain what it
represents.

Git commits should be small and meaningful.

Do not use broad commits that mix unrelated work.

Before committing:

1. Review `git status`.
2. Review the relevant diff.
3. Stage only the intended files.
4. Commit with a clear message.
5. Record the checkpoint in the project notes when it is significant.

Never use `git reset --hard`, `git clean`, mass deletion, or destructive commands
to solve a development problem unless there is an explicit and verified reason to do so.

Existing uncommitted work must be preserved.

---

## 11. Important Rule for Future Development Sessions

If the active development session changes, the next developer/assistant should first
read:

- `PROJECT_CONTEXT.md`
- `README.md`
- `docs/PROJECT-RENEWAL-NOTES.md`

Then inspect the current Git status before making changes.

Do not assume that an old task is still the current priority.

Do not restart completed work without evidence.

Do not continue an old audit if a newer active product blocker exists.

---

## 12. Current Next Direction

The current priority remains the active UI / Discovery work and its verification.

Before returning to older crawler audit work, the active UI / Discovery phase should
have no known blocker and should have appropriate regression verification.

The next development action should therefore be based on an audit of the current
implementation rather than on assumptions.

Recommended sequence:

1. Audit current UI / Discovery implementation.
2. Audit its backend/API contracts.
3. Audit recent Unicode/multilingual additions.
4. Audit recent authentication additions.
5. Identify the highest-priority real blocker.
6. Fix only that blocker.
7. Run focused tests.
8. Perform browser verification where applicable.
9. Record the result.
10. Create a Git checkpoint for the significant completed change.

---

## 13. Project Quality Standard

The target production standard remains:

Correct
+ Secure
+ Understandable
+ Testable
+ Observable
+ Maintainable
+ Usable

A feature is not considered complete merely because it renders or because one test
passes.

It should be understandable, secure, verified, and consistent with the architecture.

---

## 14. Session Handoff Principle

This document exists so that important project knowledge survives beyond a single
development session.

If the current assistant/session becomes unavailable, the next session should be able
to continue from these notes without guessing.

When a significant new decision is made, update this document.

When a significant milestone is completed, record:

- date
- what changed
- why it changed
- verification performed
- relevant tests
- Git checkpoint/commit
- next recommended action

---

# End of 2026-10-07 Entry

## 2026-10-07 — Discovery UI Contract Fix Verified

The Website Discovery runtime path was audited end-to-end using real local discovery data.

Verified:
- `/api/discovery?domain=github.com` returns HTTP 200 with real discovery data.
- `/discovery?domain=github.com` returns HTTP 200.
- Browser rendering successfully displays discovered page count, page title, URL, description, language, and crawl timestamp.
- Browser console errors: 0.
- Browser page errors: 0.

A frontend/API contract mismatch was identified:
- Backend returns `first_crawled` and `last_crawled`.
- `discovery.js` was incorrectly reading `first_crawled_at` and `last_crawled_at`.
- The frontend was corrected to use the actual API contract.

The fix was limited to `wadiya/web/discovery.js` and was browser-verified.

Checkpoint rule:
- Commit this verified Discovery UI correction separately.
- Do not include unrelated existing working-tree changes in this checkpoint.
