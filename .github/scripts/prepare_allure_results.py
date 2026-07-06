#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import re
import shutil
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path


UNIT_TEST_ENGINE = "YAxUnit"
UI_TEST_ENGINE = "Vanessa Automation"
UNIT_SCOPE = "unit"
UI_SCOPE = "ui"
LABEL_CONFIGURATION = "Конфигурация"
LABEL_CONFIGURATION_VERSION = "ВерсияКонфигурации"
LABEL_TEST_ENGINE = "ТестовыйДвижок"
LABEL_TEST_ENGINE_VERSION = "ВерсияТестовогоДвижка"
UNIT_PARENT_SUITE = "Unit-тесты"
UI_PARENT_SUITE = "UI-тесты"
UNIT_COVERAGE_SUITE = "Покрытие unit-тестами"
UI_COVERAGE_SUITE = "Покрытие UI-тестами"
ALLURE_METADATA_FILES = ("environment.properties",)
TEST_ENGINES = {
    UNIT_SCOPE: UNIT_TEST_ENGINE,
    UI_SCOPE: UI_TEST_ENGINE,
}


def normalize_version(value):
    value = value.strip()
    if len(value) > 1 and value[0] in {"v", "V"} and value[1].isdigit():
        return value[1:]
    return value


def test_engine_versions():
    return {
        UNIT_SCOPE: normalize_version(os.environ.get("YAXUNIT_VERSION", "")),
        UI_SCOPE: normalize_version(os.environ.get("VANESSA_AUTOMATION_VERSION", "")),
    }


def test_engine_info(scope, versions):
    return TEST_ENGINES.get(scope, ""), versions.get(scope, "")


def property_escape(value):
    escaped = []
    for char in value:
        code = ord(char)
        if char == "\\":
            escaped.append("\\\\")
        elif char == "\n":
            escaped.append("\\n")
        elif char == "\r":
            escaped.append("\\r")
        elif char == "\t":
            escaped.append("\\t")
        elif char == " ":
            escaped.append("\\ ")
        elif char in {"=", ":", "#", "!"}:
            escaped.append(f"\\{char}")
        elif code < 0x20 or code > 0x7E:
            escaped.append(f"\\u{code:04x}")
        else:
            escaped.append(char)

    return "".join(escaped)


def property_unescape(value):
    result = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\" or index + 1 >= len(value):
            result.append(char)
            index += 1
            continue

        escape = value[index + 1]
        if escape == "u" and index + 5 < len(value):
            code = value[index + 2:index + 6]
            if re.fullmatch(r"[0-9a-fA-F]{4}", code):
                result.append(chr(int(code, 16)))
                index += 6
                continue
        elif escape == "n":
            result.append("\n")
            index += 2
            continue
        elif escape == "r":
            result.append("\r")
            index += 2
            continue
        elif escape == "t":
            result.append("\t")
            index += 2
            continue

        result.append(escape)
        index += 2

    return "".join(result)


def property_line_parts(line):
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char in {"=", ":"}:
            return line[:index].rstrip(), line[index + 1:].lstrip()

    return None, None


def environment_property(path, name):
    if not path.is_file():
        return ""

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "!")):
            continue

        key, value = property_line_parts(line)
        if key is None:
            continue
        if property_unescape(key) == name:
            return property_unescape(value).strip()

    return ""


def dbgs_platform_version(path):
    if not path.is_file():
        return ""

    match = re.search(r"\((\d+(?:\.\d+)+)\)", path.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else ""


def coverage_summary(path):
    if not path.is_file():
        return None

    modules = {}
    current_file_path = None

    for event, elem in ET.iterparse(path, events=("start", "end")):
        tag = elem.tag.rsplit("}", maxsplit=1)[-1]

        if event == "start" and tag == "file":
            current_file_path = elem.attrib.get("path")
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


def copy_directory_contents(source_dir, target_dir):
    if not source_dir.is_dir():
        return

    for source in source_dir.iterdir():
        target = target_dir / source.name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)


def prepare_results_dir(results_dir, unit_dir, ui_dir, scopes):
    source_dirs = []
    if UNIT_SCOPE in scopes:
        source_dirs.append((unit_dir / "allure").resolve())
    if UI_SCOPE in scopes:
        source_dirs.append((ui_dir / "allure").resolve())

    if results_dir.resolve() in source_dirs:
        raise ValueError("--results-dir must differ from unit/ui source allure directories")

    if results_dir.exists():
        shutil.rmtree(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    if UNIT_SCOPE in scopes:
        copy_directory_contents(unit_dir / "allure", results_dir)
    if UI_SCOPE in scopes:
        copy_directory_contents(ui_dir / "allure", results_dir)

    for file_name in ALLURE_METADATA_FILES:
        (results_dir / file_name).unlink(missing_ok=True)


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


def remove_labels(labels, names):
    labels[:] = [label for label in labels if label.get("name") not in names]


def is_unit_result(labels):
    parent_suite = get_label(labels, "parentSuite")
    return (
        parent_suite in {"Unit tests", UNIT_PARENT_SUITE, UNIT_COVERAGE_SUITE}
        or get_label(labels, "framework") == "YAxUnit"
    )


def is_ui_result(labels):
    parent_suite = get_label(labels, "parentSuite")
    return (
        parent_suite in {UI_PARENT_SUITE, UI_COVERAGE_SUITE}
        or get_label(labels, "package") == "features"
        or bool(get_label(labels, "host"))
    )


def result_scope(labels):
    if is_unit_result(labels):
        return UNIT_SCOPE
    if is_ui_result(labels):
        return UI_SCOPE

    return None


def normalize_parent_suite(labels):
    if get_label(labels, "parentSuite") == "Unit tests":
        set_label(labels, "parentSuite", UNIT_PARENT_SUITE)
    elif get_label(labels, "framework") == "YAxUnit" and not get_label(labels, "parentSuite"):
        set_label(labels, "parentSuite", UNIT_PARENT_SUITE)

    if not get_label(labels, "parentSuite") and is_ui_result(labels):
        set_label(labels, "parentSuite", UI_PARENT_SUITE)
        if not get_label(labels, "suite"):
            set_label(labels, "suite", "Сценарии")


def set_engine_labels(labels, scope, versions):
    remove_labels(labels, {LABEL_TEST_ENGINE, LABEL_TEST_ENGINE_VERSION})
    engine, engine_version = test_engine_info(scope, versions)
    if engine:
        set_label(labels, LABEL_TEST_ENGINE, engine)
    if engine_version:
        set_label(labels, LABEL_TEST_ENGINE_VERSION, engine_version)


def normalize_result_groups(results_dir, versions):
    for path in results_dir.glob("*-result.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        labels = data.setdefault("labels", [])

        normalize_parent_suite(labels)
        remove_labels(labels, {LABEL_CONFIGURATION, LABEL_CONFIGURATION_VERSION})
        set_engine_labels(labels, result_scope(labels), versions)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_coverage_report(results_dir, title, test_scope, versions, source_dir):
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

    engine, engine_version = test_engine_info(test_scope, versions)
    diagnostic_labels = [
        {"name": LABEL_TEST_ENGINE, "value": engine},
    ]
    if engine_version:
        diagnostic_labels.append({"name": LABEL_TEST_ENGINE_VERSION, "value": engine_version})

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


def write_environment_properties(results_dir, unit_dir, ui_dir):
    release_version = os.environ.get("RELEASE_NAME", "").strip() or os.environ.get("RELEASE_TAG", "").strip()
    run_started_at = os.environ.get("REPORT_RUN_STARTED_AT", "").strip()
    if not run_started_at:
        run_started_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    platform_version = (
        environment_property(unit_dir / "allure" / "environment.properties", "ВерсияПлатформы")
        or dbgs_platform_version(unit_dir / "dbgs.log")
        or dbgs_platform_version(ui_dir / "dbgs.log")
    )

    properties = {
        "1С": platform_version,
        "EDT": os.environ.get("EDT_VERSION", "").strip(),
        "Версия сборки": release_version,
        "ВремяЗапуска": run_started_at,
    }
    content = "".join(
        f"{property_escape(key)}={property_escape(value)}\n"
        for key, value in properties.items()
    )
    (results_dir / "environment.properties").write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--unit-dir", required=True)
    parser.add_argument("--ui-dir", required=True)
    parser.add_argument("--scope", choices=("all", UNIT_SCOPE, UI_SCOPE), default="all")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    unit_dir = Path(args.unit_dir)
    ui_dir = Path(args.ui_dir)
    versions = test_engine_versions()
    scopes = (UNIT_SCOPE, UI_SCOPE) if args.scope == "all" else (args.scope,)

    prepare_results_dir(results_dir, unit_dir, ui_dir, scopes)
    write_environment_properties(results_dir, unit_dir, ui_dir)
    normalize_result_groups(results_dir, versions)
    if UNIT_SCOPE in scopes:
        add_coverage_report(results_dir, UNIT_COVERAGE_SUITE, UNIT_SCOPE, versions, unit_dir)
    if UI_SCOPE in scopes:
        add_coverage_report(results_dir, UI_COVERAGE_SUITE, UI_SCOPE, versions, ui_dir)


if __name__ == "__main__":
    main()
