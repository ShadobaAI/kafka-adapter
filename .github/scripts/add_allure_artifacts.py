#!/usr/bin/env python3
import argparse
import json
import shutil
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path


def coverage_summary(path):
    if not path.is_file():
        return None

    total = 0
    covered = 0
    files = set()

    for _, elem in ET.iterparse(path, events=("start",)):
        if elem.tag == "file":
            file_path = elem.attrib.get("path")
            if file_path:
                files.add(file_path)
        elif elem.tag == "lineToCover":
            total += 1
            if elem.attrib.get("covered") == "true":
                covered += 1

    percent = (covered / total * 100) if total else 0
    return {
        "files": len(files),
        "covered": covered,
        "total": total,
        "percent": percent,
    }


def copy_attachment(results_dir, path, name, mime_type):
    if not path.is_file():
        return None

    suffix = path.suffix or ".txt"
    source = f"{uuid.uuid4()}-attachment{suffix}"
    shutil.copyfile(path, results_dir / source)
    return {
        "name": name,
        "source": source,
        "type": mime_type,
    }


def add_result(results_dir, name, suite, status, message, attachments):
    now = int(time.time() * 1000)
    result = {
        "uuid": str(uuid.uuid4()),
        "historyId": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{suite}/{name}")),
        "name": name,
        "fullName": f"{suite}.{name}",
        "status": status,
        "statusDetails": {"message": message},
        "stage": "finished",
        "labels": [
            {"name": "suite", "value": suite},
            {"name": "framework", "value": "ci"},
        ],
        "attachments": [item for item in attachments if item],
        "start": now,
        "stop": now,
    }
    (results_dir / f"{result['uuid']}-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_label(labels, name):
    for label in labels:
        if label.get("name") == name:
            return label.get("value")
    return None


def set_label(labels, name, value):
    for label in labels:
        if label.get("name") == name:
            label["value"] = value
            return
    labels.append({"name": name, "value": value})


def normalize_result_groups(results_dir):
    for path in results_dir.glob("*-result.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        labels = data.setdefault("labels", [])
        changed = False

        if get_label(labels, "parentSuite") == "Unit tests":
            set_label(labels, "parentSuite", "Модульные тесты")
            changed = True
        elif get_label(labels, "framework") == "YAxUnit" and not get_label(labels, "parentSuite"):
            set_label(labels, "parentSuite", "Модульные тесты")
            changed = True

        if not get_label(labels, "parentSuite") and (
            get_label(labels, "package") == "features" or get_label(labels, "host")
        ):
            set_label(labels, "parentSuite", "UI-тесты")
            if not get_label(labels, "suite"):
                set_label(labels, "suite", "Сценарии")
            changed = True

        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_diagnostics(results_dir, title, source_dir):
    coverage_path = source_dir / "genericCoverage.xml"
    summary = coverage_summary(coverage_path)

    if summary:
        message = (
            f"Покрыто {summary['covered']} из {summary['total']} строк "
            f"({summary['percent']:.2f}%), файлов: {summary['files']}"
        )
        status = "passed"
    else:
        message = f"Файл покрытия не найден: {coverage_path}"
        status = "broken"

    summary_path = results_dir / f"{uuid.uuid4()}-coverage-summary.txt"
    summary_path.write_text(message + "\n", encoding="utf-8")

    attachments = [
        {
            "name": "coverage-summary.txt",
            "source": summary_path.name,
            "type": "text/plain",
        },
        copy_attachment(results_dir, coverage_path, "genericCoverage.xml", "application/xml"),
    ]

    for file_name in (
        "coverage41c.log",
        "dbgs.log",
        "unit.log",
        "vrunner.log",
        "1cv8c.log",
        "1cv8c-command.log",
        "ibsrv.log",
        "exit-code.txt",
    ):
        attachments.append(copy_attachment(results_dir, source_dir / file_name, file_name, "text/plain"))

    add_result(results_dir, f"Покрытие {title}", "Покрытие", status, message, attachments)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--unit-dir", required=True)
    parser.add_argument("--ui-dir", required=True)
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    normalize_result_groups(results_dir)
    add_diagnostics(results_dir, "unit-тестов", Path(args.unit_dir))
    add_diagnostics(results_dir, "UI-тестов", Path(args.ui_dir))


if __name__ == "__main__":
    main()
