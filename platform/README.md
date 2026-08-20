# IPO Dekho Platform

Production-oriented IPO ingestion and discovery platform for NSE Mainboard, NSE SME, BSE Mainboard and BSE SME.

## Run locally

Requirements: Docker Desktop with Compose.

```bash
docker compose -f platform/compose.yaml up --build
docker compose -f platform/compose.yaml --profile jobs run --rm ingest
```

Open:

- Website: <http://localhost:3000>
- API documentation: <http://localhost:8080/docs>
- Health: <http://localhost:8080/health/ready>

The ingestion command is deliberately separate from the long-running API. Re-running it is idempotent: canonical issues and source listings are updated, while exchange-timestamped intraday subscription observations are retained without duplicating an unchanged snapshot.

## Development without Docker

```bash
cd platform/backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
python scripts/migrate.py
uvicorn app.main:app --reload
```

```bash
cd platform/frontend
npm install
npm run dev
```

Copy the corresponding `.env.example` file before starting each service.

## Repository map

- `backend/app/ingestion`: source-specific clients, normalization, reconciliation and persistence
- `backend/app/api.py`: public read-only FastAPI contract
- `backend/app/models.py`: normalized PostgreSQL schema
- `frontend/src/app`: server-rendered Next.js website
- `infra`: Cloud Run, Cloud SQL, Scheduler and monitoring deployment guidance

## Operational behavior

- NSE uses a warm page request before JSON feeds to establish exchange cookies.
- Historical NSE fetches are divided into 92-day windows.
- NSE and BSE discovery feeds are collected separately, then due IPOs are enriched from official per-issue detail feeds.
- Upcoming IPOs refresh every six hours, open IPOs every five minutes, closed IPOs daily until listing, and listed IPOs finalize after seven days.
- A source returning fewer than `SOURCE_MINIMUM_ROWS` fails validation and cannot erase data.
- Missing listings are only marked stale after three successful omissions; they are never automatically deleted.
- When configured, raw batches are gzip-compressed into `RAW_SNAPSHOT_BUCKET`.
- One exchange can fail without rolling back fresh data from the other, but the job exits unsuccessfully to trigger monitoring.

## Data-use note

Review NSE and BSE website terms before production deployment. The adapters are rate-limited, use official public sources, and do not bypass CAPTCHAs or access controls. IPO Dekho is informational and must not be presented as investment advice.
