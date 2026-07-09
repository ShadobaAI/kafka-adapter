#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import re
import shutil
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
        parent_suite in {"Unit tests", UNIT_PARENT_SUITE}
        or get_label(labels, "framework") == "YAxUnit"
    )


def is_ui_result(labels):
    parent_suite = get_label(labels, "parentSuite")
    return (
        parent_suite == UI_PARENT_SUITE
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


if __name__ == "__main__":
    main()
