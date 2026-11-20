#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import re
import shutil
import sys
import uuid
from pathlib import Path

from validate_allure_report import has_allure_results


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


def group_attachments(item):
    yield from item.get("attachments", [])
    for key in ("steps", "befores", "afters"):
        for step in item.get(key, []):
            yield from group_attachments(step)


def prepare_results_dir(results_dir, unit_dir, ui_dirs, scopes, grouped, versions, ui_groups=()):
    sources_by_target = {}
    if UNIT_SCOPE in scopes:
        sources_by_target[results_dir] = [unit_dir / "allure"]
    if UI_SCOPE in scopes:
        for ui_dir in ui_dirs:
            target = results_dir / ui_dir.name if grouped else results_dir
            sources_by_target.setdefault(target, []).append(ui_dir / "allure")

    sources = [source for paths in sources_by_target.values() for source in paths]
    if any(results_dir.resolve() == source.resolve() for source in sources):
        raise ValueError("--results-dir must differ from unit/ui source allure directories")

    if results_dir.exists():
        shutil.rmtree(results_dir)
    results_dir.mkdir(parents=True)
    groups_by_index = {str(index): group for index, group in enumerate(ui_groups)}
    valid = True
    for target, paths in sources_by_target.items():
        target.mkdir(exist_ok=True)
        for source in paths:
            copy_directory_contents(source, target)
        for file_name in ALLURE_METADATA_FILES:
            for metadata in target.rglob(file_name):
                if metadata.is_file():
                    metadata.unlink()
        is_ui_worker = target != results_dir
        ui_group = None
        if is_ui_worker and groups_by_index:
            group = groups_by_index.get(target.name.rpartition("-ui-")[2])
            if group is None:
                print(f"::error::{target.name}: no matching group in the UI matrix", file=sys.stderr)
                valid = False
            else:
                ui_group = group.split("/")
        if not normalize_results(target, versions, grouped=is_ui_worker, ui_group=ui_group):
            valid = False

    if grouped and UI_SCOPE in scopes:
        workers = {worker.name.rpartition("-ui-")[2]: worker for worker in ui_dirs}
        for index, group in groups_by_index.items():
            worker = workers.get(index)
            if worker is None or not has_allure_results(results_dir / worker.name):
                write_missing_ui_group(results_dir, group, worker)
                valid = False
    return valid


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


def normalize_suites(labels, ui_group):
    if ui_group is not None:
        section, object_name = ui_group
        remove_labels(labels, {"parentSuite", "suite", "subSuite"})
        labels.extend([
            {"name": "parentSuite", "value": UI_PARENT_SUITE},
            {"name": "suite", "value": section},
            {"name": "subSuite", "value": object_name},
        ])
        return

    if get_label(labels, "parentSuite") == "Unit tests":
        set_label(labels, "parentSuite", UNIT_PARENT_SUITE)
    elif get_label(labels, "framework") == "YAxUnit" and not get_label(labels, "parentSuite"):
        set_label(labels, "parentSuite", UNIT_PARENT_SUITE)

    if not get_label(labels, "parentSuite") and is_ui_result(labels):
        set_label(labels, "parentSuite", UI_PARENT_SUITE)
        if not get_label(labels, "suite"):
            set_label(labels, "suite", "Сценарии")


def write_missing_ui_group(results_dir, group, worker):
    message = f"Для UI-группы {group} отсутствуют читаемые результаты Allure."
    print(f"::error::{message}", file=sys.stderr)
    labels = []
    normalize_suites(labels, group.split("/"))
    record_id = str(uuid.uuid4())
    record = {
        "uuid": record_id,
        "name": f"Сбор результатов группы {group}",
        "fullName": f"release-ci/ui-results/{group}",
        "status": "broken",
        "statusDetails": {"message": message},
        "labels": labels,
    }
    url = os.environ.get("REPORT_RUN_URL")
    if url:
        if worker is not None and (worker / "check-run-id").is_file():
            job_id = (worker / "check-run-id").read_text(encoding="utf-8").strip()
            if job_id.isdecimal():
                url = f"{url}/job/{job_id}"
        record["links"] = [{"name": "Диагностика в GitHub Actions", "url": url, "type": "custom"}]
    (results_dir / f"{record_id}-result.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")


def set_engine_labels(labels, scope, versions):
    remove_labels(labels, {LABEL_TEST_ENGINE, LABEL_TEST_ENGINE_VERSION})
    engine, engine_version = test_engine_info(scope, versions)
    if engine:
        set_label(labels, LABEL_TEST_ENGINE, engine)
    if engine_version:
        set_label(labels, LABEL_TEST_ENGINE_VERSION, engine_version)


def normalize_results(directory, versions, *, grouped, ui_group=None):
    # Allure resolves attachment names across inputs, even for separate directories.
    directory = directory.resolve()
    files = {path for path in directory.rglob("*") if path.is_file()}
    namespace_attachments = grouped or any(path.parent != directory for path in files)
    names = {}
    valid = True
    for path in sorted(files):
        if not path.name.endswith(("-result.json", "-container.json")):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            if path.name.endswith("-result.json"):
                labels = data.setdefault("labels", [])
                normalize_suites(labels, ui_group)
                remove_labels(labels, {LABEL_CONFIGURATION, LABEL_CONFIGURATION_VERSION})
                set_engine_labels(labels, result_scope(labels), versions)
            if namespace_attachments:
                for attachment in group_attachments(data):
                    source = attachment["source"]
                    attachment_path = (path.parent / source).resolve()
                    if attachment_path not in files:
                        attachment_path = (directory / source).resolve()
                    if attachment_path not in files:
                        print(f"::warning::{path}: missing attachment {source}", file=sys.stderr)
                        continue
                    if attachment_path not in names:
                        names[attachment_path] = f"{uuid.uuid4()}-attachment{attachment_path.suffix}"
                        attachment_path.rename(directory / names[attachment_path])
                    attachment["source"] = names[attachment_path]
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            print(f"::error::{path}: invalid Allure record: {error}", file=sys.stderr)
            path.unlink()  # The test job retains the original raw artifact.
            valid = False
            continue
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return valid


def write_environment_properties(results_dir, unit_dir, ui_dirs):
    release_version = os.environ.get("RELEASE_NAME", "").strip() or os.environ.get("RELEASE_TAG", "").strip()
    run_started_at = os.environ.get("REPORT_RUN_STARTED_AT", "").strip()
    if not run_started_at:
        run_started_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    platform_version = (
        environment_property(unit_dir / "allure" / "environment.properties", "ВерсияПлатформы")
        or dbgs_platform_version(unit_dir / "dbgs.log")
    )
    for ui_dir in ui_dirs:
        if platform_version:
            break
        platform_version = dbgs_platform_version(ui_dir / "dbgs.log")

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
    ui = parser.add_mutually_exclusive_group(required=True)
    ui.add_argument("--ui-dir", type=Path)
    ui.add_argument("--ui-groups-dir", type=Path)
    parser.add_argument("--ui-groups-json", type=json.loads, default=[], help="Matrix groups in job-index order")
    parser.add_argument("--scope", choices=("all", UNIT_SCOPE, UI_SCOPE), default="all")
    args = parser.parse_args()
    if not isinstance(args.ui_groups_json, list) or not all(
        isinstance(path, str) and re.fullmatch(r"[^/]+/[^/]+", path) for path in args.ui_groups_json
    ):
        parser.error("--ui-groups-json must be a JSON array of section/object paths")

    results_dir = Path(args.results_dir)
    unit_dir = Path(args.unit_dir)
    grouped = args.ui_groups_dir is not None
    ui_dirs = sorted(args.ui_groups_dir.glob("test-results-*-ui-*")) if grouped else [args.ui_dir]
    versions = test_engine_versions()
    scopes = (UNIT_SCOPE, UI_SCOPE) if args.scope == "all" else (args.scope,)

    valid = prepare_results_dir(results_dir, unit_dir, ui_dirs, scopes, grouped, versions, args.ui_groups_json)
    write_environment_properties(results_dir, unit_dir, ui_dirs)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
