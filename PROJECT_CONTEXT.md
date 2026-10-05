# Wadiya — Project Context

## What this project is

Wadiya is an independent web discovery platform being built from the ground up.

The goal is to help people discover the web, not replace the web.

## Current architecture

Seeds / Discovery
        ↓
      Crawler
        ↓
     Storage
        ↓
      Indexer
        ↓
    Retrieval
        ↓
     Ranking
        ↓
     Search
        ↓
       API
        ↓
      Web UI

## Phase 0

Phase 0 was completed and frozen at the time of its original verification.

Historical verification snapshot:
- Python tests: 153/153 PASS
- Live HTTP: 45/45 PASS
- Browser: 42/42 PASS
- Total: 340/340 checks PASS

These numbers are historical and must not be interpreted as the current project-wide verification count.

Phase 0 fixes:
- API security headers were fixed for JSON exception responses.
- Browser test timing/CSP handling was stabilized.

Do not modify Phase 0 unless a later phase requires a verified change.

## Phase 1

Original crawler roadmap:

M1 Concurrent crawler workers
M2 URL discovery improvements
M3 Sitemap / feed discovery
M4 Persistent retry/backoff
M5 Recrawl scheduler
M6 Deduplication improvements
M7 Crawl observability
M8 Search quality/ranking
M9 Scale/storage migration

The original roadmap is retained as historical planning context. Current development state is defined in the "Current Development State" section below.

## M1 requirements

M1 should introduce multiple crawler workers while keeping the current architecture.

Requirements:
- One crawler process.
- Keep CrawlLock.
- Initial worker target: about 4 workers.
- Keep the existing SQLite queue.
- Different domains may fetch concurrently.
- The same domain must not be fetched concurrently.
- max_total_pages must remain exact under concurrency.
- A worker failure must not kill the entire crawl.
- Preserve robots.txt handling.
- Preserve crawl-delay handling.
- Preserve retries.
- Preserve redirect validation.
- Preserve SSRF protection.
- Preserve canonical/noindex/nofollow handling.
- Preserve duplicate handling.
- Preserve stale queue recovery.
- Preserve crawl statistics.
- Preserve SQLite integrity.
- Preserve index consistency.

Do not add Redis, Celery, PostgreSQL, asyncio, or distributed infrastructure for M1.

Make the smallest necessary source changes and add focused tests.

## SearchLab reference

An earlier experimental project called SearchLab exists separately.

Useful ideas from it:
- sitemap discovery
- title weighting
- exact phrase signals
- all-term matching

Do not merge SearchLab wholesale.

Wadiya already has the more mature architecture:
SQLite FTS5, BM25 ranking, persistent queue, interfaces, and security controls.

## Future direction

Long-term Wadiya may include:
- broader discovery mesh
- sitemap/feed discovery
- publisher submissions
- publisher notifications
- freshness-aware crawling
- discovery priority
- search-demand-driven discovery
- coverage-gap detection
- change-aware indexing
- web quality signals
- website identity
- local web discovery
- publisher/webmaster tools
- source-first AI answers
- knowledge graph
- eventual distributed crawling/indexing when actually needed

Core principle:

"Wadiya should help people discover the web, not replace the web."

"AI should help the web, not replace the web."

## Working rules

- Audit before changing code.
- One phase at a time.
- One topic at a time.
- Prefer small verified changes.
- Run focused tests after changes.
- Do not make unrelated refactors.
- Do not replace working architecture without evidence.
- Keep the project understandable to another developer or AI assistant.

---

# Permanent Engineering Rules

These rules apply to all future Wadiya development unless a later verified architectural decision explicitly supersedes them.

## 1. Core Product Principles

- Wadiya is a web discovery platform.
- Wadiya should help people discover the web, not replace the web.
- AI should help the web, not replace the web.
- Wadiya must not intentionally become a visual or product clone of Google or another search platform.
- Features should help users complete their task and leave efficiently.
- Avoid unnecessary engagement loops, dark patterns, or features whose primary purpose is to keep users on the site.

## 2. Architecture

- Audit the existing architecture before introducing a new architecture.
- Prefer the smallest change that solves the actual problem.
- Preserve working architectural foundations unless evidence shows that they must change.
- Do not introduce new infrastructure merely because it is popular or convenient.
- Do not replace a working subsystem without a verified reason.
- Keep responsibilities separated between crawler, storage, indexing, retrieval, ranking, API, and UI.
- New features must have a clear owner layer.
- Avoid circular dependencies and unnecessary coupling.
- Keep the project understandable to another developer or AI assistant.

## 3. Data Integrity

- Never invent, fabricate, or infer stored metrics as if they were real.
- UI must only display backend data that actually exists and is verified.
- If a requested metric does not exist, either implement the required backend support first or clearly omit/mark the metric as unavailable.
- Preserve database integrity during migrations and schema changes.
- Do not silently discard existing data.
- Verify lifecycle behavior for new stored data: creation, update, failure, retry, deletion/deactivation where applicable.
- Database changes require focused tests and regression verification.

## 4. Security

- Treat all crawler content as untrusted input.
- Treat URLs, titles, descriptions, page content, domains, query strings, and external metadata as untrusted.
- Preserve SSRF protection and redirect validation.
- Preserve DNS rebinding protection.
- Preserve robots and crawl-policy enforcement.
- Preserve input validation and safe URL handling.
- Never render untrusted crawler content as trusted HTML.
- Escape or safely encode untrusted content before displaying it.
- Preserve CSP and other security headers.
- Never weaken an existing security control merely to make a feature easier to implement.
- Security-sensitive changes require targeted security tests.

## 5. API Contracts

- API behavior must be explicit and predictable.
- Validate external input at the API boundary.
- Use appropriate HTTP status codes.
- Keep response structures stable unless a deliberate contract change is required.
- UI must not assume backend capabilities that do not exist.
- When an API changes, update the relevant tests and consumers.
- Do not hide backend failures behind fake successful UI states.

## 6. UI and Design System

- Establish and maintain a shared design system before adding large amounts of page-specific styling.
- Design tokens should cover, where applicable:
  - colors
  - typography
  - spacing
  - borders
  - radius
  - shadows
  - focus states
  - responsive breakpoints
  - motion
- Establish shared layout patterns before creating one-off page layouts.
- Prefer reusable UI primitives over duplicated styling.
- Shared components should be used consistently across pages.
- Feature-specific components may extend shared foundations but should not create unnecessary competing design systems.
- New pages must fit the established Wadiya visual identity.
- Do not copy Google's visual language, layout, or interaction patterns unnecessarily.
- UI hierarchy must make the user's primary task obvious.
- Avoid visual complexity that does not improve discovery or task completion.
- Do not solve a local styling problem by creating a conflicting global style.

## 7. Layout

- Establish shared rules for page containers, headers, main content areas, sections, lists, forms, and navigation.
- Design for desktop, laptop, tablet, and mobile from the beginning.
- Do not treat mobile responsiveness as a late-stage patch.
- Prevent horizontal overflow and broken layouts at supported viewport sizes.
- Shared layout behavior should be centralized where practical.

## 8. Accessibility

- Use semantic HTML where appropriate.
- Maintain keyboard accessibility.
- Maintain visible focus states.
- Use accessible labels for controls.
- Maintain appropriate heading hierarchy.
- Preserve meaningful status and error announcements.
- Do not rely on color alone to communicate meaning.
- Test important user journeys with keyboard and browser automation.

## 9. Performance

- Avoid unnecessary network requests.
- Avoid unnecessary JavaScript and client-side work.
- Avoid rendering or fetching data that the user does not need.
- Keep crawler, database, search, API, and UI operations measurable where practical.
- Performance regressions should be investigated rather than hidden.

## 10. Testing

Every meaningful change follows this workflow:

AUDIT
→ IDENTIFY PROBLEM
→ FIX
→ TARGETED TEST
→ VERIFY
→ CONTINUE

Rules:

- Audit before changing code.
- Make the smallest necessary change.
- Run focused tests immediately after the change.
- Verify the actual behavior, not only that the code compiles.
- Run relevant regression tests after subsystem changes.
- Do not knowingly move past a discovered blocker.
- A known problem must be fixed or explicitly documented before continuing.
- Browser testing is required for important UI behavior.
- Automated tests must not be treated as a substitute for practical browser inspection.
- Real/test websites should be used where crawler/discovery behavior requires practical verification.

## 11. Browser and UI Verification

Important user journeys should be verified through the real running application.

At minimum, the project should be able to verify:

Home
→ Search / Discovery
→ Results
→ Website Discovery
→ Website Information
→ Discovered Pages / Content

The Wadiya development/test environment should support practical inspection of:

- URL input
- discovery start
- crawl status
- queue state
- discovered pages
- indexed pages
- errors
- elapsed time
- logs
- resulting website information

Do not declare a UI feature complete solely because a static inspection or unit test passes.

## 12. Error Handling

- Errors must be understandable to the user or developer who needs to act on them.
- Do not silently swallow important failures.
- Do not expose sensitive internal information through public errors.
- Failed operations should leave the system in a recoverable state where possible.
- Retry behavior must be deliberate rather than accidental.
- Error states need UI verification when they are user-facing.

## 13. Logging and Observability

- Important crawler, storage, indexing, search, API, and administrative operations should be observable.
- Do not log secrets, credentials, session tokens, or unnecessary sensitive information.
- Operational metrics must come from real system state.
- If a feature requires observability, add the required backend support rather than creating placeholder numbers.

## 14. Dependencies

- Do not add a dependency for a trivial problem that can be solved safely with the existing stack.
- Before adding a dependency, verify that it is actually necessary.
- Keep dependency versions controlled.
- Avoid introducing infrastructure dependencies that conflict with the current architecture.
- Dependency changes require appropriate regression testing.

## 15. Documentation

- Architecture decisions should be documented.
- Important operational rules should be documented.
- New major subsystems should have enough documentation for another developer or AI assistant to understand them.
- Documentation must not knowingly describe obsolete behavior as current behavior.
- When architecture changes materially, update the relevant project context and documentation.

## 16. Git and Change Control

- Check `git status` before making substantial changes.
- Do not overwrite unrelated uncommitted work.
- Do not reset, clean, or delete files unless explicitly required and verified safe.
- Keep changes scoped to the current task.
- Avoid unrelated refactors during feature work.
- Review the final diff before committing.
- A commit should represent a coherent verified change.
- Do not commit generated secrets, local credentials, databases, browser binaries, or other machine-specific artifacts unless explicitly intended.

## 17. Backup and Recovery

- Before modifying an important project-context or configuration document, create a recoverable backup when appropriate.
- Never assume a destructive operation is reversible.
- Preserve existing working code until the replacement has been verified.
- Prefer additive or reversible changes when uncertainty exists.

## 18. AI-Assisted Development Rules

Any AI assistant working on Wadiya must:

- Read the relevant existing code before proposing changes.
- Understand the current architecture before replacing or creating subsystems.
- Never invent APIs, database fields, metrics, or capabilities.
- Never claim that an unverified change works.
- Never silently delete working functionality.
- Never make unrelated changes to solve a local problem.
- Explain important architectural consequences before major changes.
- Preserve existing security controls.
- Prefer small, testable changes.
- Run or request the appropriate verification after changes.
- Stop and surface a blocker when continuing would knowingly build on a broken foundation.
- Update documentation when a permanent architectural rule or behavior changes.

## 19. Feature Development Order

For a substantial new feature, prefer:

1. Product requirement
2. Architecture audit
3. Data/API contract
4. Security and validation design
5. Design-system impact
6. Shared component foundation
7. Backend implementation
8. UI implementation
9. Focused automated tests
10. Browser verification
11. Regression testing
12. Documentation
13. Final diff/status review

Do not repeatedly build individual pages first and postpone the shared foundation until the project is mostly complete.

## 20. Wadiya Discovery Platform Rules

Wadiya's discovery experience should evolve around:

Home
→ Search / Discovery
→ Results
→ Website Discovery
→ Website Information
→ Discovered Pages / Content

A dedicated website Discovery experience may expose real information such as:

- website identity
- discovered page count
- discovered pages
- crawl timestamps
- indexing state where actually supported
- technical information where actually stored
- discovery history where actually stored
- other verified discovery information

Do not expose unsupported analytics or pretend that crawler data represents website-owner analytics.

## 21. Maintenance Rule

Before declaring a phase or feature complete, verify:

- architecture
- security
- data integrity
- API behavior
- UI behavior
- accessibility
- responsive behavior
- automated tests
- browser tests
- regression tests
- documentation
- Git/change scope

A feature is not considered complete merely because its main screen renders.

## 22. Permanent Decision Rule

When a new requirement conflicts with an existing rule:

1. Identify the conflict.
2. Explain the architectural consequence.
3. Determine whether the existing rule is still valid.
4. Deliberately update the rule if necessary.
5. Document the decision.
6. Then implement the change.

Never allow project rules to become accidental contradictions.

---

# Current Development State

This section is a point-in-time status snapshot and does not override the permanent rules above.

Verified crawler audit status currently reaches Item 15 (Crawl Scheduling).

The current UI/Discovery work is part of the active development phase. The Website Discovery backend and initial browser rendering have been implemented and manually verified against crawled data.

Current development must continue using:

AUDIT
→ IDENTIFY PROBLEM
→ FIX
→ TARGETED TEST
→ VERIFY
→ CONTINUE

The project must not return to the next crawler audit item until the active UI/Discovery phase has no known blocker and the required regression verification has been completed.

---

# Project Completion Standard

Wadiya should be considered production-ready only when the relevant subsystem has been verified across:

- correct architecture
- secure input handling
- data integrity
- API contracts
- user-facing behavior
- accessibility
- responsive layouts
- automated tests
- browser/E2E tests
- regression tests
- operational observability
- documentation
- deployment readiness

Passing tests alone is not sufficient.

The final standard is:

**Correct + Secure + Understandable + Testable + Observable + Maintainable + Usable**
