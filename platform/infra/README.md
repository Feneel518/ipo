# Google Cloud deployment

The target topology is two Cloud Run services (`ipo-api`, `ipo-web`), one Cloud Run Job (`ipo-ingest`), Cloud SQL PostgreSQL, Cloud Storage, Secret Manager and Cloud Scheduler.

## Prerequisites

Set these shell variables before using the commands:

```bash
export PROJECT_ID="your-project"
export REGION="asia-south1"
export SQL_INSTANCE="ipo-dekho-postgres"
export SQL_CONNECTION="$PROJECT_ID:$REGION:$SQL_INSTANCE"
export REPOSITORY="ipo-dekho"
export RELEASE="$(git rev-parse --short HEAD)"
gcloud config set project "$PROJECT_ID"
```

Enable `run.googleapis.com`, `sqladmin.googleapis.com`, `cloudscheduler.googleapis.com`, `secretmanager.googleapis.com`, `storage.googleapis.com`, `artifactregistry.googleapis.com`, `cloudbuild.googleapis.com` and `monitoring.googleapis.com`.

Create the Cloud SQL database with automated backups and point-in-time recovery, a private IP/network attachment, an `ipodekho` database/user, an Artifact Registry Docker repository, and a versioned raw-snapshot bucket with an appropriate lifecycle rule. Store `DATABASE_URL`, `INTERNAL_API_TOKEN` and `REVALIDATION_SECRET` in Secret Manager. For Cloud SQL Unix sockets, the SQLAlchemy URL has the form:

```text
postgresql+psycopg://USER:PASSWORD@/ipodekho?host=/cloudsql/PROJECT:REGION:INSTANCE
```

## Build and deploy

```bash
gcloud builds submit --config platform/infra/cloudbuild.yaml --substitutions=_REGION="$REGION",_REPOSITORY="$REPOSITORY",_TAG="$RELEASE"
BACKEND_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/backend:$RELEASE"
FRONTEND_IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/frontend:$RELEASE"

gcloud run jobs deploy ipo-migrate --image "$BACKEND_IMAGE" --region "$REGION" --command python --args scripts/migrate.py --set-cloudsql-instances "$SQL_CONNECTION" --set-secrets DATABASE_URL=DATABASE_URL:latest
gcloud run jobs execute ipo-migrate --region "$REGION" --wait

gcloud run deploy ipo-api --image "$BACKEND_IMAGE" --region "$REGION" --allow-unauthenticated --set-cloudsql-instances "$SQL_CONNECTION" --set-secrets DATABASE_URL=DATABASE_URL:latest,INTERNAL_API_TOKEN=INTERNAL_API_TOKEN:latest
API_URL="$(gcloud run services describe ipo-api --region "$REGION" --format='value(status.url)')"

gcloud run deploy ipo-web --image "$FRONTEND_IMAGE" --region "$REGION" --allow-unauthenticated --set-env-vars API_BASE_URL="$API_URL" --set-secrets REVALIDATION_SECRET=REVALIDATION_SECRET:latest
WEB_URL="$(gcloud run services describe ipo-web --region "$REGION" --format='value(status.url)')"

gcloud run jobs deploy ipo-ingest --image "$BACKEND_IMAGE" --region "$REGION" --command ipo-ingest --max-retries 2 --task-timeout 30m --set-cloudsql-instances "$SQL_CONNECTION" --set-secrets DATABASE_URL=DATABASE_URL:latest,REVALIDATION_SECRET=REVALIDATION_SECRET:latest --set-env-vars RAW_SNAPSHOT_BUCKET="ipo-dekho-raw-$PROJECT_ID",REVALIDATION_URL="$WEB_URL/api/revalidate"
```

## Five-minute scheduler

Create a dedicated scheduler service account with `roles/run.invoker`, then invoke the Cloud Run Job every five minutes. The ingestion service applies the lifecycle-specific refresh cadence per IPO.

```bash
gcloud scheduler jobs create http ipo-ingest-five-minute --location "$REGION" --schedule "*/5 * * * *" --time-zone "Asia/Kolkata" --uri "https://run.googleapis.com/v2/projects/$PROJECT_ID/locations/$REGION/jobs/ipo-ingest:run" --http-method POST --oauth-service-account-email "ipo-scheduler@$PROJECT_ID.iam.gserviceaccount.com"
```

Create Cloud Monitoring log-based metrics and email policies for job failure, `ingestion_failed`, `frontend_revalidation_failed`, suspicious row counts and three consecutive source failures. Add uptime checks for `/health/live`, `/health/ready` and the web homepage. Restrict Cloud SQL access to service identities and configure the public API behind Cloud Armor/CDN when traffic requires it.
