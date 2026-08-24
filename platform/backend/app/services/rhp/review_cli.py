import argparse
import json

from app.services.rhp.approval import approve_extraction_run, review_extraction_run


def _resolution(value: str) -> dict[str, str]:
    try:
        issue_code, disposition, note = value.split("=", 2)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "resolution must be ISSUE_CODE=DISPOSITION=note"
        ) from exc
    return {"issue_code": issue_code, "disposition": disposition, "note": note}


def main() -> None:
    parser = argparse.ArgumentParser(description="Review and approve RHP extraction runs")
    commands = parser.add_subparsers(dest="command", required=True)
    review = commands.add_parser("review")
    review.add_argument("--run-id", type=int, required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--resolution", action="append", type=_resolution, required=True)
    approve = commands.add_parser("approve")
    approve.add_argument("--run-id", type=int, required=True)
    approve.add_argument("--approver", required=True)
    args = parser.parse_args()
    if args.command == "review":
        review_extraction_run(args.run_id, reviewer=args.reviewer, resolutions=args.resolution)
    else:
        approve_extraction_run(args.run_id, approver=args.approver)
    final_status = "REVIEWED" if args.command == "review" else "APPROVED"
    print(json.dumps({"run_id": args.run_id, "status": final_status}))


if __name__ == "__main__":
    main()
