#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Публикация краткого отчета unit/UI тестов в GitHub Step Summary."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from xml.etree import ElementTree


def append_summary(text: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        print(text)
        return

    with Path(summary_path).open("a", encoding="utf-8") as summary:
        summary.write(text)
        if not text.endswith("\n"):
            summary.write("\n")


def read_junit(path: Path) -> str:
    if not path.is_file():
        return f"### Unit tests\n\nJUnit file not found: `{path}`.\n"

    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError as error:
        return f"### Unit tests\n\nCannot parse JUnit file `{path}`: {error}.\n"
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))

    tests = sum(int(suite.get("tests", "0") or 0) for suite in suites)
    failures = sum(int(suite.get("failures", "0") or 0) for suite in suites)
    errors = sum(int(suite.get("errors", "0") or 0) for suite in suites)
    skipped = sum(int(suite.get("skipped", "0") or 0) for suite in suites)
    passed = tests - failures - errors - skipped

    failed_cases: list[str] = []
    for case in root.iter("testcase"):
        if case.find("failure") is None and case.find("error") is None:
            continue
        classname = case.get("classname", "")
        name = case.get("name", "")
        failed_cases.append(f"- `{classname}.{name}`".replace("`.", "`"))

    lines = [
        "### Unit tests",
        "",
        "| Total | Passed | Failed | Errors | Skipped |",
        "| ---: | ---: | ---: | ---: | ---: |",
        f"| {tests} | {passed} | {failures} | {errors} | {skipped} |",
        "",
    ]
    if failed_cases:
        lines.append("Failed cases:")
        lines.extend(failed_cases[:20])
        lines.append("")

    return "\n".join(lines)


def read_allure(results_dir: Path) -> str:
    if not results_dir.is_dir():
        return f"### UI tests\n\nAllure results directory not found: `{results_dir}`.\n"

    counts = {"passed": 0, "failed": 0, "broken": 0, "skipped": 0, "unknown": 0}
    failed_cases: list[str] = []

    for result_file in sorted(results_dir.glob("*-result.json")):
        try:
            data = json.loads(result_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        status = data.get("status") or "unknown"
        counts[status if status in counts else "unknown"] += 1

        if status in {"failed", "broken"}:
            name = data.get("fullName") or data.get("name") or result_file.name
            failed_cases.append(f"- `{name}`")

    total = sum(counts.values())
    lines = [
        "### UI tests",
        "",
        "| Total | Passed | Failed | Broken | Skipped | Unknown |",
        "| ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| {total} | {counts['passed']} | {counts['failed']} | {counts['broken']} | {counts['skipped']} | {counts['unknown']} |",
        "",
    ]
    if failed_cases:
        lines.append("Failed or broken scenarios:")
        lines.extend(failed_cases[:20])
        lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit-junit", type=Path)
    parser.add_argument("--ui-allure", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    parts: list[str] = []

    if args.unit_junit is not None:
        parts.append(read_junit(args.unit_junit))
    if args.ui_allure is not None:
        parts.append(read_allure(args.ui_allure))

    append_summary("\n".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
