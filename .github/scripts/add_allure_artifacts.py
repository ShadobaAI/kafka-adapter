#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path


REPORT_CONFIGURATION_NAME = "Адаптер Kafka"
REPORT_TEST_ENGINE = "YAxUnit + Vanessa Automation"


def normalize_version(value):
    return value.strip().removeprefix("v").removeprefix("V")


def report_test_engine_version():
    versions = []
    yaxunit_version = normalize_version(os.environ.get("YAXUNIT_VERSION", ""))
    vanessa_version = normalize_version(os.environ.get("VANESSA_AUTOMATION_VERSION", ""))

    if yaxunit_version:
        versions.append(f"YAxUnit: {yaxunit_version}")
    if vanessa_version:
        versions.append(f"Vanessa Automation: {vanessa_version}")

    return " + ".join(versions)


def coverage_summary(paths):
    if isinstance(paths, Path):
        paths = [paths]

    existing_paths = [path for path in paths if path.is_file()]
    if not existing_paths:
        return None

    modules = {}

    for path in existing_paths:
        current_file_path = None

        for event, elem in ET.iterparse(path, events=("start", "end")):
            tag = elem.tag.rsplit("}", maxsplit=1)[-1]

            if event == "start" and tag == "file":
                file_path = elem.attrib.get("path")
                current_file_path = file_path
                if current_file_path:
                    modules.setdefault(current_file_path, {"covered_lines": set(), "total_lines": set()})
            elif event == "start" and tag == "lineToCover" and current_file_path:
                line_number = elem.attrib.get("lineNumber")
                if line_number:
                    module = modules.setdefault(current_file_path, {"covered_lines": set(), "total_lines": set()})
                    module["total_lines"].add(line_number)
                    if elem.attrib.get("covered") == "true":
                        module["covered_lines"].add(line_number)
            elif event == "end" and tag == "file":
                current_file_path = None
                elem.clear()

    module_summaries = []
    for module_path, module in sorted(modules.items()):
        module_info = coverage_module_info(module_path)
        module_total = len(module["total_lines"])
        module_covered = len(module["covered_lines"])
        module_summaries.append(
            {
                "path": module_path,
                "display_path": module_info["display"],
                "tree_name": module_info["tree_name"],
                "tree_suite": module_info["tree_suite"],
                "tree_sub_suite": module_info["tree_sub_suite"],
                "covered": module_covered,
                "total": module_total,
                "percent": (module_covered / module_total * 100) if module_total else 0,
            }
        )

    total = sum(module["total"] for module in module_summaries)
    covered = sum(module["covered"] for module in module_summaries)
    percent = (covered / total * 100) if total else 0
    return {
        "files": len(modules),
        "covered": covered,
        "total": total,
        "percent": percent,
        "modules": module_summaries,
    }


def coverage_module_info(module_path):
    parts = [part for part in module_path.replace("\\", "/").split("/") if part]

    if parts and parts[0] == "src":
        parts = parts[1:]

    if parts and parts[-1].endswith(".bsl"):
        if parts[-1] == "Module.bsl":
            parts = parts[:-1]
        else:
            parts = [*parts[:-1], parts[-1][:-4]]

    if len(parts) < 2:
        return {
            "display": f"path={module_path}",
            "tree_name": module_path,
            "tree_suite": "Прочее",
            "tree_sub_suite": "",
        }

    if len(parts) >= 4 and parts[2] == "Forms":
        parts = [parts[0], parts[1], *parts[3:]]

    tree_name = "/".join(parts[2:]) if len(parts) > 2 else parts[1]

    return {
        "display": "/".join(parts),
        "tree_name": tree_name,
        "tree_suite": parts[0],
        "tree_sub_suite": parts[1] if len(parts) > 2 else "",
    }


def coverage_module_display_path(module_path):
    return coverage_module_info(module_path)["display"]


def format_coverage_summary(summary):
    lines = [
        (
            f"Итого: покрыто {summary['covered']} из {summary['total']} строк "
            f"({summary['percent']:.2f}%), модулей: {summary['files']}"
        ),
        "",
        "Покрытие по модулям:",
    ]

    for module in summary["modules"]:
        lines.append(
            f"{module['percent']:6.2f}% "
            f"{module['covered']}/{module['total']} "
            f"{module['display_path']}"
        )

    return "\n".join(lines) + "\n"


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


def add_result(results_dir, name, suite, status, message, attachments, extra_labels=None):
    now = int(time.time() * 1000)
    labels = [
        {"name": "suite", "value": suite},
        {"name": "framework", "value": "ci"},
    ]
    if extra_labels:
        labels.extend(extra_labels)

    label_identity = "/".join(
        f"{label['name']}={label['value']}"
        for label in labels
        if label.get("name") in {"parentSuite", "suite", "subSuite", "testType"}
    )
    full_name = f"{label_identity}/{name}" if label_identity else name

    result = {
        "uuid": str(uuid.uuid4()),
        "historyId": str(uuid.uuid5(uuid.NAMESPACE_URL, full_name)),
        "name": name,
        "fullName": full_name,
        "status": status,
        "statusDetails": {"message": message},
        "stage": "finished",
        "labels": labels,
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


def normalize_result_groups(results_dir, configuration_version, test_engine_version):
    for path in results_dir.glob("*-result.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        labels = data.setdefault("labels", [])
        changed = False

        if get_label(labels, "parentSuite") == "Unit tests":
            set_label(labels, "parentSuite", "Unit-тесты")
            changed = True
        elif get_label(labels, "framework") == "YAxUnit" and not get_label(labels, "parentSuite"):
            set_label(labels, "parentSuite", "Unit-тесты")
            changed = True

        if not get_label(labels, "parentSuite") and (
            get_label(labels, "package") == "features" or get_label(labels, "host")
        ):
            set_label(labels, "parentSuite", "UI-тесты")
            if not get_label(labels, "suite"):
                set_label(labels, "suite", "Сценарии")
            changed = True

        if configuration_version:
            set_label(labels, "ВерсияКонфигурации", configuration_version)
            changed = True

        set_label(labels, "Конфигурация", REPORT_CONFIGURATION_NAME)
        set_label(labels, "ТестовыйДвижок", REPORT_TEST_ENGINE)
        if test_engine_version:
            set_label(labels, "ВерсияТестовогоДвижка", test_engine_version)
        changed = True

        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_coverage_report(results_dir, title, configuration_version, test_engine_version, source_dir):
    coverage_path = source_dir / "genericCoverage.xml"
    summary = coverage_summary(coverage_path)

    if summary:
        message = (
            f"Покрыто {summary['covered']} из {summary['total']} строк "
            f"({summary['percent']:.2f}%), файлов: {summary['files']}"
        )
        summary_text = format_coverage_summary(summary)
        status = "passed"
    else:
        message = f"Файл покрытия не найден: {coverage_path}"
        summary_text = message + "\n"
        status = "broken"

    summary_path = results_dir / f"{uuid.uuid4()}-coverage-summary.txt"
    summary_path.write_text(summary_text, encoding="utf-8")

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

    diagnostic_labels = [
        {"name": "Конфигурация", "value": REPORT_CONFIGURATION_NAME},
        {"name": "ТестовыйДвижок", "value": REPORT_TEST_ENGINE},
    ]
    if configuration_version:
        diagnostic_labels.append({"name": "ВерсияКонфигурации", "value": configuration_version})
    if test_engine_version:
        diagnostic_labels.append({"name": "ВерсияТестовогоДвижка", "value": test_engine_version})

    add_result(
        results_dir,
        f"Итого {summary['percent']:.2f}%" if summary else "Итого",
        title,
        status,
        message,
        attachments,
        extra_labels=[
            {"name": "parentSuite", "value": title},
            *diagnostic_labels,
        ],
    )

    if not summary:
        return

    for module in summary["modules"]:
        module_message = (
            f"Покрыто {module['covered']} из {module['total']} строк "
            f"({module['percent']:.2f}%). {title}: {module['display_path']}"
        )
        module_labels = [
            {"name": "parentSuite", "value": title},
            {"name": "testType", "value": title},
            *diagnostic_labels,
        ]
        if module["tree_sub_suite"]:
            module_labels.append({"name": "subSuite", "value": module["tree_sub_suite"]})

        add_result(
            results_dir,
            f"{module['tree_name']} ({module['percent']:.2f}%, {module['covered']}/{module['total']})",
            module["tree_suite"],
            "passed",
            module_message,
            [],
            extra_labels=module_labels,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--unit-dir", required=True)
    parser.add_argument("--ui-dir", required=True)
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    configuration_version = os.environ.get("RELEASE_TAG", "").strip()
    test_engine_version = report_test_engine_version()

    normalize_result_groups(results_dir, configuration_version, test_engine_version)
    add_coverage_report(results_dir, "Покрытие unit-тестами", configuration_version, test_engine_version, Path(args.unit_dir))
    add_coverage_report(results_dir, "Покрытие UI-тестами", configuration_version, test_engine_version, Path(args.ui_dir))


if __name__ == "__main__":
    main()
