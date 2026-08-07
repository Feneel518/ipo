# IPO Dekho

Monorepo for the IPO Dekho web application and background worker.

## Layout

- `web/` — web application (intentionally empty for now)
- `worker/` — Python worker with a FastAPI HTTP surface

The two legacy source directories currently at the workspace root are preserved
unchanged and ignored by Git pending a deliberate migration into the worker.

## Run the worker locally

```powershell
cd worker
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item ..\.env.example .env
uvicorn app.main:app --reload
```

The service exposes `GET /health/live` and `GET /health/ready`. API docs are at
`/docs` outside production.

Set `DATABASE_URL` to the pooled Postgres connection string supplied by Neon or
Supabase. Secrets belong in local environment files or the deployment platform's
secret manager, never in version control.
