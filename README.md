# IPO Dekho

IPO discovery platform with a FastAPI/PostgreSQL backend and a Next.js frontend.

## Project layout

- `platform/backend` — FastAPI API, ingestion jobs, Alembic migrations
- `platform/frontend` — Next.js website
- `platform/compose.yaml` — local PostgreSQL, API, frontend, and ingestion services

Local development instructions are in [`platform/README.md`](platform/README.md).

## Production deployment

The backend is prepared for Railway project `46b87785-dd77-4293-b1f7-e14df5dcaf73`, and the frontend is prepared for Vercel. Both platforms should be connected to this GitHub repository so pushes to `main` deploy automatically.

### Railway

Add a PostgreSQL database to the Railway project, then create three services from this repository.

#### API service

Set these service settings:

- Root Directory: `/platform/backend`
- Config File Path: `/platform/backend/railway.toml`
- Generate a public Railway domain

Set these variables:

```dotenv
DATABASE_URL=${{Postgres.DATABASE_URL}}
ENVIRONMENT=production
CORS_ORIGINS=https://YOUR_VERCEL_DOMAIN
INTERNAL_API_TOKEN=GENERATE_A_LONG_RANDOM_VALUE
REVALIDATION_URL=https://YOUR_VERCEL_DOMAIN/api/revalidate
REVALIDATION_SECRET=USE_THE_SAME_RANDOM_VALUE_AS_VERCEL
```

The API container runs migrations before each deployment and exposes `/health/live` and `/health/ready` health endpoints.

#### Ingestion cron service

Create a second service from the same repository and set:

- Root Directory: `/platform/backend`
- Config File Path: `/platform/backend/railway.ingest.toml`
- No public domain is required

Use the same `DATABASE_URL`, `ENVIRONMENT`, `REVALIDATION_URL`, and `REVALIDATION_SECRET` variables. It runs `ipo-ingest` every five minutes; the application itself skips detail requests until each IPO is due for refresh.

To run the complete RHP pipeline automatically for every upcoming and open IPO, add these variables
to the ingestion cron service (the API service does not need these credentials):

```dotenv
R2_BUCKET=ipo
R2_ENDPOINT_URL=https://YOUR_CLOUDFLARE_ACCOUNT_ID.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=YOUR_R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY=YOUR_R2_SECRET_ACCESS_KEY
RHP_ALLOWED_HOSTS=nseindia.com,bseindia.com
GEMINI_SAFE_PDF_BYTES=47185920
GEMINI_MAX_PDF_PAGES=1000
RHP_CHUNK_MAX_BYTES=41943040
RHP_CHUNK_MAX_PAGES=300
GEMINI_API_KEY=YOUR_SERVER_SIDE_GEMINI_KEY
RHP_PRIMARY_MODEL=gemini-3.5-flash-lite
RHP_PROMPT_VERSION=rhp-v1.7
RHP_SCHEMA_VERSION=rhp-v1.1
RHP_EXTRACTION_BATCH_SIZE=5
RHP_EXTRACTION_MAX_ATTEMPTS=3
GEMINI_FILE_TIMEOUT_SECONDS=300
GEMINI_FILE_POLL_SECONDS=2
GEMINI_REQUEST_TIMEOUT_SECONDS=180
```

Create an R2 S3 API token with **Object Read & Write** access scoped only to the `ipo` bucket.
Keep the bucket private: the current website continues to link to the official exchange URL, while
R2 retains the canonical copy so a versioned extraction can be reproduced after Gemini's temporary
file expires. No CORS rule, public `r2.dev` URL, custom domain, or Worker is required.

The ingestion job accepts either a direct PDF or a ZIP used by an exchange as transport. For ZIP
responses it extracts one RHP PDF into a temporary file, uploads only that PDF, and removes both
temporary files. R2 keys use `rhp/{year}/{ipo_id}/{sha256}.pdf`; ZIP files are never stored.
Each stored PDF is inspected for page count, encryption, and parse errors. Documents at or below
45 MiB and 1,000 pages are marked `DIRECT`. Oversized documents are structurally optimized and,
when still over the direct limits, split into chunks of at most 40 MiB and 300 pages. Processing
files remain private in R2 and retain their original PDF page ranges for extraction provenance.

#### Optional dedicated RHP extraction cron service

The ingestion cron automatically archives, prepares, queues, and extracts an active IPO RHP only
when that RHP is first stored. Empty five-minute discovery runs do not invoke Gemini, and the
document hash prevents duplicate paid extraction. For higher throughput or scheduled retries, you
can also create a dedicated extraction service from the same repository and set:

- Root Directory: `/platform/backend`
- Config File Path: `/platform/backend/railway.extract.toml`
- No public domain is required

Give it the same database, R2, and Gemini variables. PostgreSQL row locking makes it safe to run
alongside the ingestion cron.

`GEMINI_API_KEY` belongs only on this backend worker and must never use a `NEXT_PUBLIC_` prefix.
The worker claims jobs with PostgreSQL row locks, uploads one prepared PDF to Gemini, stores the
raw structured response and usage metadata, validates it, and writes canonical reported metrics.
It then calculates the v2 investor metrics in Python: sales and PAT CAGR, PAT margin,
debt/equity, OCF/PAT cash conversion, receivables/revenue, its year-on-year trend, and annual
revenue growth. Calculated rows are stored separately with `source=CALCULATED`; they never replace
issuer-reported facts and never use a source value quarantined as ambiguous.
Its identity is the document SHA-256 plus model, prompt version, and schema version, so completed
work is not paid for twice. Temporary Gemini files are deleted after each attempt.

Gemini extraction uses four focused JSON passes over the same temporary file: company, financials,
offer/promoters/customers, and material risks. Each pass is validated with Pydantic before the
results are merged. Partial valid passes are retained for retries, and rate-limit retries honor
Gemini's requested delay. Missing disclosures remain `NOT_FOUND` or `NOT_APPLICABLE` and are not
treated as extraction failures. A claimed numeric value whose focused citation does not support it
is retained in the raw audit record but omitted from canonical output as `AMBIGUOUS`.

Existing unapproved Gemini runs can be backfilled without another model call:

```powershell
ipo-extract --refresh-calculated-metrics
```

Warning-bearing runs use an explicit human approval workflow. Each warning needs an ordered
disposition and audit note before the run can move from `READY_WITH_WARNINGS` to `REVIEWED`, and
only a reviewed run can move to `APPROVED`:

```powershell
ipo-review review --run-id 123 --reviewer reviewer-name `
  --resolution "MODEL_WARNING=ACCEPTED=Checked against the cited RHP page."
ipo-review approve --run-id 123 --approver approver-name
```

The same workflow is available at `/review`. The page is protected with HTTP Basic authentication,
keeps the backend token server-side, and provides ordered dispositions, audit notes, raw JSON
inspection, and final approval. Configure these frontend-only server variables:

```dotenv
INTERNAL_API_TOKEN=USE_THE_SAME_PRIVATE_TOKEN_AS_RAILWAY
REVIEW_DASHBOARD_USER=editor
REVIEW_DASHBOARD_PASSWORD=USE_A_LONG_RANDOM_PASSWORD
```

Malformed Gemini JSON is conservatively syntax-repaired before Pydantic validation. Any repaired
pass is marked with a warning, so it cannot be published without appearing in this review queue.

The current worker intentionally accepts only RHPs represented by one `ORIGINAL` or `OPTIMIZED`
processing file. Documents split into `CHUNK` files remain unqueued until candidate reconciliation
is implemented. Run one batch locally with `ipo-extract --limit 5` after applying migrations and
setting the backend credentials.

### Vercel

Import this GitHub repository as a Vercel project and set its Root Directory to `platform/frontend`. Set the following variables for Production and Preview:

```dotenv
API_BASE_URL=https://YOUR_RAILWAY_API_DOMAIN
NEXT_PUBLIC_SITE_URL=https://YOUR_VERCEL_DOMAIN
REVALIDATION_SECRET=USE_THE_SAME_RANDOM_VALUE_AS_RAILWAY
INTERNAL_API_TOKEN=USE_THE_SAME_PRIVATE_TOKEN_AS_RAILWAY
REVIEW_DASHBOARD_USER=editor
REVIEW_DASHBOARD_PASSWORD=USE_A_LONG_RANDOM_PASSWORD
```

After the first Vercel deployment, replace `YOUR_VERCEL_DOMAIN` in Railway's variables with the real production URL and redeploy the Railway services. Preview deployments use the production API through server-side requests; add a preview origin to `CORS_ORIGINS` only if browser-side API calls are introduced later.
