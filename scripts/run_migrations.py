import os
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"


def load_env() -> None:
    if not ENV_PATH.exists():
        return
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def apply_migrations() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    migrations_dir = ROOT / "database" / "migrations"
    if not migrations_dir.exists():
        raise SystemExit(f"Migrations directory not found: {migrations_dir}")

    conn = psycopg.connect(database_url, connect_timeout=20)
    try:
        for path in sorted(migrations_dir.glob("*.sql")):
            print(f"Applying migration: {path.name}")
            conn.execute(path.read_text(encoding="utf-8"))
            conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    load_env()
    apply_migrations()
