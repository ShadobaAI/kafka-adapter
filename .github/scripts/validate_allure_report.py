#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--summary", required=False)
    parser.add_argument("--name", default="Allure")
    parser.add_argument("--min-tests", type=int, default=1)
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    result_files = list(results_dir.rglob("*-result.json"))
    if not result_files:
        print(f"{args.name} result files not found: {results_dir}", file=sys.stderr)
        if results_dir.exists():
            for path in sorted(results_dir.rglob("*"))[:100]:
                print(path, file=sys.stderr)
        return 1

    if not args.summary:
        return 0

    summary_path = Path(args.summary)
    if not summary_path.is_file():
        print(f"{args.name} summary not found: {summary_path}", file=sys.stderr)
        return 1

    data = json.loads(summary_path.read_text(encoding="utf-8"))
    total = data.get("stats", {}).get("total")
    if not isinstance(total, int) or total < args.min_tests:
        print(
            f"{args.name} report contains {total!r} tests, expected at least {args.min_tests}: {summary_path}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
