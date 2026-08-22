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

Add a PostgreSQL database to the Railway project, then create two services from this repository.

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

To archive RHPs for upcoming and open IPOs, add these variables to the ingestion cron service (the API service
does not need the R2 credentials):

```dotenv
R2_BUCKET=ipo
R2_ENDPOINT_URL=https://YOUR_CLOUDFLARE_ACCOUNT_ID.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=YOUR_R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY=YOUR_R2_SECRET_ACCESS_KEY
RHP_ALLOWED_HOSTS=nseindia.com,bseindia.com
```

Create an R2 S3 API token with **Object Read & Write** access scoped only to the `ipo` bucket.
Keep the bucket private: the current website continues to link to the official exchange URL, while
R2 holds the temporary canonical copy for backend processing. After a Gemini extraction is
successfully committed to the database, its worker must call the R2 cleanup operation. No CORS
rule, public `r2.dev` URL, custom
domain, or Worker is required for this ingestion stage.

The ingestion job accepts either a direct PDF or a ZIP used by an exchange as transport. For ZIP
responses it extracts one RHP PDF into a temporary file, uploads only that PDF, and removes both
temporary files. R2 keys use `rhp/{year}/{ipo_id}/{sha256}.pdf`; ZIP files are never stored.

### Vercel

Import this GitHub repository as a Vercel project and set its Root Directory to `platform/frontend`. Set the following variables for Production and Preview:

```dotenv
API_BASE_URL=https://YOUR_RAILWAY_API_DOMAIN
NEXT_PUBLIC_SITE_URL=https://YOUR_VERCEL_DOMAIN
REVALIDATION_SECRET=USE_THE_SAME_RANDOM_VALUE_AS_RAILWAY
```

After the first Vercel deployment, replace `YOUR_VERCEL_DOMAIN` in Railway's variables with the real production URL and redeploy the Railway services. Preview deployments use the production API through server-side requests; add a preview origin to `CORS_ORIGINS` only if browser-side API calls are introduced later.
