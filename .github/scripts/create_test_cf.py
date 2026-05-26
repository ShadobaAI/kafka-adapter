# -*- coding: utf-8 -*-
"""Сборка общей XML-конфигурации для тестовой базы из XML-выгрузок 1С.

Скрипт работает с XML формата Конфигуратора 1С, не с EDT-проектами.
Base берется как основа, adapter и examples накладываются поверх нее.
"""
from __future__ import annotations

import argparse
import copy
import io
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


# 1C XML metadata names.
V8_NAMESPACE = "http://v8.1c.ru/8.1/data/core"
USER_DEFINED_TYPE_PATH = Path("DefinedTypes") / "кфкПользователь.xml"
USER_DEFINED_TYPE_VALUE = "CatalogRef.Пользователи"

# Update module and procedure names.
UPDATE_DB_MODULE_NAME = "ОбновлениеИнформационнойБазыKafka"
UPDATE_HANDLERS_PROCEDURE = "ПриДобавленииОбработчиковОбновления"
EXAMPLES_UPDATE_HANDLERS_PROCEDURE = f"кфк_т_{UPDATE_HANDLERS_PROCEDURE}"
UPDATE_DB_MODULE_PATH = Path("CommonModules") / UPDATE_DB_MODULE_NAME / "Ext" / "Module.bsl"
UPDATE_DB_MODULE_ARCHIVE_ENTRY = f"CommonModules/{UPDATE_DB_MODULE_NAME}/Ext/Module.bsl"

ChildObjectKey = tuple[str, str]


class RussianArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs.setdefault("add_help", False)
        super().__init__(*args, **kwargs)
        self.add_argument("-h", "--help", action="help", help="показать эту справку.")

    def format_help(self) -> str:
        return super().format_help().replace("usage:", "Использование:").replace("options:", "Параметры:")

    def format_usage(self) -> str:
        return super().format_usage().replace("usage:", "Использование:")

    def error(self, message: str) -> None:
        message = message.replace("unrecognized arguments:", "неизвестные параметры:")
        message = message.replace("expected one argument", "ожидалось одно значение")
        message = message.replace("the following arguments are required:", "обязательные параметры:")
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: ошибка: {message}\n")


@dataclass(frozen=True)
class ArchiveExclusions:
    roots: frozenset[str] = frozenset()
    paths: frozenset[str] = frozenset()
    prefixes: frozenset[str] = frozenset()

    def contains(self, member_name: str) -> bool:
        normalized = normalized_archive_name(member_name)
        return (
            archive_root_name(normalized) in self.roots
            or normalized in self.paths
            or any(normalized.startswith(prefix) for prefix in self.prefixes)
        )


@dataclass(frozen=True)
class BuildOptions:
    base_archive: Path
    adapter_archive: Path
    examples_archive: Path
    output_dir: Path


@dataclass(frozen=True)
class BuildStats:
    base_files: int
    adapter_files: int
    adapter_child_objects: int
    examples_files: int
    examples_child_objects: int
    update_handler_lines: int
    user_type_nodes: int


BASE_EXCLUSIONS = ArchiveExclusions(
    roots=frozenset({"ConfigDumpInfo.xml"}),
)

# При наложении конфигураций верхний Configuration.xml сливается отдельно,
# поэтому служебные корневые файлы и общие каталоги расширения не копируются.
CONFIGURATION_EXCLUSIONS = ArchiveExclusions(
    roots=frozenset(
        {
            "Configuration.xml",
            "ConfigDumpInfo.xml",
            "Languages",
            "Ext",
        }
    ),
)

EXAMPLES_EXCLUSIONS = ArchiveExclusions(
    roots=CONFIGURATION_EXCLUSIONS.roots
    | frozenset(
        {
            UPDATE_DB_MODULE_NAME,
            f"{UPDATE_DB_MODULE_NAME}.xml",
        }
    ),
    paths=frozenset(
        {
            f"CommonModules/{UPDATE_DB_MODULE_NAME}.xml",
        }
    ),
    prefixes=frozenset(
        {
            f"CommonModules/{UPDATE_DB_MODULE_NAME}/",
        }
    ),
)

EXAMPLES_EXCLUDED_CHILD_OBJECTS: frozenset[ChildObjectKey] = frozenset(
    {
        ("CommonModule", UPDATE_DB_MODULE_NAME),
    }
)


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def validate_file(path: Path, description: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{description} не найден: {resolved}")
    return resolved


def validate_options(args: argparse.Namespace) -> BuildOptions:
    return BuildOptions(
        base_archive=validate_file(args.base_archive, "База"),
        adapter_archive=validate_file(args.adapter_archive, "Адаптер"),
        examples_archive=validate_file(args.examples_archive, "Примеры"),
        output_dir=args.output_dir,
    )


def recreate_dir(path: Path) -> None:
    resolved = path.resolve()

    if resolved.exists():
        if resolved == Path(resolved.anchor) or resolved.parent == resolved:
            raise ValueError(f"Refusing to remove unsafe output path: {resolved}")
        shutil.rmtree(resolved)

    resolved.mkdir(parents=True, exist_ok=False)


def archive_root_name(member_name: str) -> str:
    normalized = normalized_archive_name(member_name)
    return normalized.split("/", maxsplit=1)[0]


def normalized_archive_name(member_name: str) -> str:
    return member_name.replace("\\", "/").lstrip("/")


def resolve_inside(base_dir: Path, member_name: str) -> Path:
    target = (base_dir / member_name).resolve()
    base = base_dir.resolve()

    if target == base or base in target.parents:
        return target

    raise ValueError(f"Unsafe archive member path: {member_name}")


def verify_zip(archive: zipfile.ZipFile) -> None:
    bad_file = archive.testzip()
    if bad_file is not None:
        raise zipfile.BadZipFile(f"Broken file in archive: {bad_file}")


def extract_zip(
    archive_path: Path,
    output_dir: Path,
    exclusions: ArchiveExclusions = ArchiveExclusions(),
) -> int:
    archive_path = archive_path.resolve()
    output_dir = output_dir.resolve()

    if not archive_path.is_file():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    extracted_count = 0

    with zipfile.ZipFile(archive_path) as archive:
        verify_zip(archive)

        for member in archive.infolist():
            if exclusions.contains(member.filename):
                continue

            target = resolve_inside(output_dir, member.filename)

            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            extracted_count += 1

    return extracted_count


def unpack_base_archive(archive_path: Path, output_dir: Path) -> int:
    recreate_dir(output_dir)
    return extract_zip(archive_path, output_dir, BASE_EXCLUSIONS)


def merge_adapter_archive(archive_path: Path, output_dir: Path) -> int:
    return extract_zip(archive_path, output_dir, CONFIGURATION_EXCLUSIONS)


def merge_examples_archive(archive_path: Path, output_dir: Path) -> int:
    return extract_zip(archive_path, output_dir, EXAMPLES_EXCLUSIONS)


def read_zip_entry(archive_path: Path, entry_name: str) -> bytes:
    with zipfile.ZipFile(archive_path) as archive:
        try:
            with archive.open(entry_name) as entry:
                return entry.read()
        except KeyError as error:
            raise FileNotFoundError(f"Archive {archive_path} does not contain {entry_name}") from error


def decode_text(data: bytes) -> str:
    return data.decode("utf-8-sig")


def detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def collect_namespaces(xml_source: Path | bytes) -> list[tuple[str, str]]:
    namespaces: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    source: str | io.BytesIO
    if isinstance(xml_source, Path):
        source = str(xml_source)
    else:
        source = io.BytesIO(xml_source)

    for _, namespace in ElementTree.iterparse(source, events=("start-ns",)):
        if namespace not in seen:
            seen.add(namespace)
            namespaces.append(namespace)

    return namespaces


def register_namespaces(*xml_sources: Path | bytes) -> None:
    for xml_source in xml_sources:
        for prefix, uri in collect_namespaces(xml_source):
            ElementTree.register_namespace(prefix, uri)


def element_local_name(element: ElementTree.Element) -> str:
    if element.tag.startswith("{"):
        return element.tag.rsplit("}", maxsplit=1)[1]
    return element.tag


def element_namespace_uri(element: ElementTree.Element) -> str:
    if element.tag.startswith("{"):
        return element.tag[1:].split("}", maxsplit=1)[0]
    return ""


def same_namespace_tag(element: ElementTree.Element, local_name: str) -> str:
    namespace_end = element.tag.rfind("}")
    namespace = element.tag[: namespace_end + 1] if element.tag.startswith("{") else ""
    return f"{namespace}{local_name}"


def child(element: ElementTree.Element, local_name: str) -> ElementTree.Element | None:
    return element.find(same_namespace_tag(element, local_name))


def required_child(element: ElementTree.Element, local_name: str, path: str) -> ElementTree.Element:
    result = child(element, local_name)
    if result is None:
        raise ValueError(f"Configuration.xml does not contain {path} node")
    return result


def configuration_child_objects(root: ElementTree.Element) -> ElementTree.Element:
    configuration = required_child(root, "Configuration", "Configuration")
    return required_child(configuration, "ChildObjects", "Configuration/ChildObjects")


def should_skip_child_object(
    child_object: ElementTree.Element,
    excluded_child_objects: frozenset[ChildObjectKey],
) -> bool:
    if element_local_name(child_object) == "Language":
        return True

    object_name = (child_object.text or "").strip()
    return (element_local_name(child_object), object_name) in excluded_child_objects


def merge_configuration_child_objects(
    source_path: Path,
    output_dir: Path,
    excluded_child_objects: frozenset[ChildObjectKey] = frozenset(),
) -> int:
    # В XML-выгрузке 1С список объектов конфигурации хранится в
    # Configuration/ChildObjects. Файлы объектов копируются отдельно,
    # а здесь добавляем только ссылки на них в базовый Configuration.xml.
    base_configuration_path = output_dir.resolve() / "Configuration.xml"
    if not base_configuration_path.is_file():
        raise FileNotFoundError(f"Base Configuration.xml not found: {base_configuration_path}")

    source_configuration_xml = read_zip_entry(source_path, "Configuration.xml")
    register_namespaces(base_configuration_path, source_configuration_xml)

    base_tree = ElementTree.parse(base_configuration_path)
    source_root = ElementTree.fromstring(source_configuration_xml)

    base_child_objects = configuration_child_objects(base_tree.getroot())
    source_child_objects = configuration_child_objects(source_root)

    added_count = 0
    for source_child in source_child_objects:
        if should_skip_child_object(source_child, excluded_child_objects):
            continue

        base_child_objects.append(copy.deepcopy(source_child))
        added_count += 1

    ElementTree.indent(base_tree, space="\t")
    base_tree.write(base_configuration_path, encoding="UTF-8", xml_declaration=True)

    return added_count


def update_user_defined_type(output_dir: Path) -> int:
    # В base определяемый тип пользователя пустой/абстрактный для адаптации.
    # Для тестовой базы фиксируем его на стандартный справочник Пользователи.
    defined_type_path = output_dir.resolve() / USER_DEFINED_TYPE_PATH
    if not defined_type_path.is_file():
        raise FileNotFoundError(f"Defined type file not found: {defined_type_path}")

    register_namespaces(defined_type_path)
    tree = ElementTree.parse(defined_type_path)

    updated_count = 0
    for element in tree.getroot().iter():
        if element_namespace_uri(element) == V8_NAMESPACE and element_local_name(element) == "Type":
            element.text = USER_DEFINED_TYPE_VALUE
            updated_count += 1

    if updated_count == 0:
        raise ValueError(f"v8:Type node not found in {defined_type_path}")

    ElementTree.indent(tree, space="\t")
    tree.write(defined_type_path, encoding="UTF-8", xml_declaration=True)

    return updated_count


def is_procedure_start(line: str, procedure_name: str) -> bool:
    stripped = line.lstrip()
    return stripped.startswith("Процедура ") and f" {procedure_name}(" in f" {stripped}"


def procedure_bounds(lines: list[str], procedure_name: str) -> tuple[int, int]:
    start_index = None

    for index, line in enumerate(lines):
        if is_procedure_start(line, procedure_name):
            start_index = index
            break

    if start_index is None:
        raise ValueError(f"Procedure not found: {procedure_name}")

    for index in range(start_index + 1, len(lines)):
        if lines[index].strip().lower() == "конецпроцедуры":
            return start_index, index

    raise ValueError(f"Procedure end not found: {procedure_name}")


def trimmed_body(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)

    while start < end and lines[start].strip() == "":
        start += 1
    while end > start and lines[end - 1].strip() == "":
        end -= 1

    return lines[start:end]


def procedure_body(lines: list[str], procedure_name: str) -> list[str]:
    start_index, end_index = procedure_bounds(lines, procedure_name)
    return trimmed_body(lines[start_index + 1 : end_index])


def insert_before_procedure_end(
    lines: list[str],
    procedure_name: str,
    inserted_lines: list[str],
) -> None:
    start_index, end_index = procedure_bounds(lines, procedure_name)

    while end_index > start_index + 1 and lines[end_index - 1].strip() == "":
        del lines[end_index - 1]
        end_index -= 1

    lines[end_index:end_index] = ["", *inserted_lines, ""]


def merge_update_handlers_procedure(examples_archive: Path, output_dir: Path) -> int:
    # В examples есть свой обработчик обновления с тестовыми данными.
    # Сам модуль examples не переносим, а тело процедуры добавляем в модуль adapter.
    module_path = output_dir.resolve() / UPDATE_DB_MODULE_PATH
    if not module_path.is_file():
        raise FileNotFoundError(f"Update module file not found: {module_path}")

    examples_module_text = decode_text(read_zip_entry(examples_archive, UPDATE_DB_MODULE_ARCHIVE_ENTRY))
    examples_body = procedure_body(
        examples_module_text.splitlines(),
        examples_UPDATE_HANDLERS_PROCEDURE,
    )

    if not examples_body:
        return 0

    module_text = module_path.read_text(encoding="utf-8-sig")
    module_lines = module_text.splitlines()
    insert_before_procedure_end(module_lines, UPDATE_HANDLERS_PROCEDURE, examples_body)

    newline = detect_newline(module_text)
    module_path.write_text(newline.join(module_lines) + newline, encoding="utf-8")

    return len(examples_body)


def build_test_database(options: BuildOptions) -> BuildStats:
    # Порядок важен: base создает каталог результата, adapter добавляет
    # подсистему Kafka, examples добавляет тестовые объекты и обработчики.
    base_files = unpack_base_archive(options.base_archive, options.output_dir)
    adapter_files = merge_adapter_archive(options.adapter_archive, options.output_dir)
    adapter_child_objects = merge_configuration_child_objects(
        options.adapter_archive,
        options.output_dir,
    )
    examples_files = merge_examples_archive(options.examples_archive, options.output_dir)
    examples_child_objects = merge_configuration_child_objects(
        options.examples_archive,
        options.output_dir,
        excluded_child_objects=EXAMPLES_EXCLUDED_CHILD_OBJECTS,
    )

    update_handler_lines = merge_update_handlers_procedure(
        options.examples_archive,
        options.output_dir,
    )
    user_type_nodes = update_user_defined_type(options.output_dir)

    return BuildStats(
        base_files=base_files,
        adapter_files=adapter_files,
        adapter_child_objects=adapter_child_objects,
        examples_files=examples_files,
        examples_child_objects=examples_child_objects,
        update_handler_lines=update_handler_lines,
        user_type_nodes=user_type_nodes,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = RussianArgumentParser(
        description=(
            "Собирает общий XML из архивов XML-выгрузок base, adapter и examples. "
            "Файлы расширений .cfe сюда не передаются."
        )
    )
    parser.add_argument(
        "-b",
        "--base",
        dest="base_archive",
        type=Path,
        required=True,
        metavar="PATH",
        help="архив XML-выгрузки базовой конфигурации.",
    )
    parser.add_argument(
        "-a",
        "--adapter",
        dest="adapter_archive",
        type=Path,
        required=True,
        metavar="PATH",
        help="архив XML-выгрузки конфигурации адаптера.",
    )
    parser.add_argument(
        "-e",
        "--examples",
        dest="examples_archive",
        type=Path,
        required=True,
        metavar="PATH",
        help="архив XML-выгрузки конфигурации примеров.",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_dir",
        type=Path,
        required=True,
        metavar="PATH",
        help="каталог для результата: собранной XML-конфигурации.",
    )
    return parser


def print_summary(options: BuildOptions, stats: BuildStats) -> None:
    print(f"Base XML unpacked from {options.base_archive} to {options.output_dir}: {stats.base_files} files")
    print(f"Adapter XML merged from {options.adapter_archive}: {stats.adapter_files} files")
    print(f"Adapter Configuration/ChildObjects merged: {stats.adapter_child_objects} items")
    print(f"examples XML merged from {options.examples_archive}: {stats.examples_files} files")
    print(f"examples Configuration/ChildObjects merged: {stats.examples_child_objects} items")
    print(f"Update handlers procedure body merged: {stats.update_handler_lines} lines")
    print(f"Updated user defined type: {stats.user_type_nodes} v8:Type nodes")


def main(argv: list[str] | None = None) -> int:
    configure_stdio()

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        options = validate_options(args)
        stats = build_test_database(options)
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print_summary(options, stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
