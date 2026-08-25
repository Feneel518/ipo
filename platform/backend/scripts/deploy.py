"""Apply schema migrations and refresh deterministic RHP metrics before API rollout."""

from alembic import command
from alembic.config import Config

from app.services.rhp.extraction import refresh_calculated_metrics


def main() -> None:
    command.upgrade(Config("alembic.ini"), "head")
    refreshed_runs, calculated_rows = refresh_calculated_metrics()
    print(
        "rhp_calculated_metrics_refreshed "
        f"runs={refreshed_runs} rows={calculated_rows}"
    )


if __name__ == "__main__":
    main()
