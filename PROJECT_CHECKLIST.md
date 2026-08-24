# IPO Dekho — Project Progress Checklist

Last reviewed: 24 August 2026

Use `[x]` for completed work and `[ ]` for work that is still pending. Update this file in the same commit as the work it tracks so the checklist stays reliable.

## Product and frontend

- [x] Home page with open, upcoming, and recently listed IPOs
- [x] Searchable and filterable IPO directory
- [x] Individual IPO detail pages
- [x] IPO dates, price band, lot size, issue size, and exchange details
- [x] Live subscription breakdown by investor category
- [x] Subscription momentum chart and calculation notes
- [x] Source trail and filed-document links
- [x] IPO calendar
- [x] Methodology, About, not-found, sitemap, and robots pages
- [x] Responsive layouts for desktop and mobile
- [ ] Complete a final cross-browser visual review
- [ ] Complete a keyboard-navigation and screen-reader review
- [ ] Run a production Lighthouse audit and resolve important findings

## Backend and data

- [x] FastAPI read API and health endpoints
- [x] PostgreSQL models and Alembic migrations
- [x] NSE and BSE ingestion adapters
- [x] Mainboard and SME issue normalization
- [x] Persisted IPO allotment, refund, and share-credit dates with automatic backfill
- [x] Idempotent ingestion and immutable subscription history
- [x] Stale-source safeguards and raw snapshot support
- [x] Canonical RHP PDF archiving to Cloudflare R2 (without ZIP retention)
- [x] PDF inspection, structural optimization, byte-aware splitting, and original-page mapping
- [x] Versioned Gemini extraction jobs/runs with raw JSON, usage, retries, and canonical metrics
- [x] Single-file Gemini extraction worker for original and optimized RHPs
- [x] Validate the Gemini happy path against five real ordinary RHPs
- [x] Auditable RHP warning review and approval workflow
- [ ] Reconcile split-PDF chunk candidates into one extraction
- [x] Automated backend tests for adapters, normalization, master data, and history
- [ ] Validate live NSE and BSE output against exchange pages
- [ ] Test a complete IPO lifecycle from upcoming through listing
- [ ] Document and test database backup restoration

## Quality gates

- [x] Frontend TypeScript check passes
- [x] Frontend ESLint check passes
- [x] Frontend production build passes
- [ ] Run the complete backend test suite in the production-like environment
- [ ] Add end-to-end tests for the main visitor journeys
- [ ] Add automated accessibility checks
- [ ] Add dependency and container vulnerability scanning
- [ ] Define acceptable API response-time and page-load targets

## Deployment and operations

- [x] Dockerfiles and local Compose configuration
- [x] Cloud Build configuration and infrastructure guidance
- [x] Separate API and ingestion-job deployment configuration
- [ ] Create and verify the production database
- [ ] Apply all migrations in production
- [ ] Configure production environment variables and secrets
- [ ] Configure the ingestion schedule
- [ ] Configure uptime, ingestion-failure, and stale-data alerts
- [ ] Configure logs, retention, and operational dashboards
- [ ] Configure the production domain, HTTPS, and redirects
- [ ] Perform a rollback drill

## Launch readiness

- [ ] Review NSE and BSE data-use terms
- [ ] Review the investment-risk disclaimer and privacy requirements
- [ ] Verify metadata, canonical URLs, sitemap, and robots behavior in production
- [ ] Add analytics and error tracking if required
- [ ] Conduct final content and data-accuracy review
- [ ] Obtain launch approval
- [ ] Launch production
- [ ] Complete a post-launch smoke test

## Notes and decisions

- Add dated notes here when a checklist item is blocked or requires a product decision.
- Keep secrets, credentials, and private URLs out of this file.
