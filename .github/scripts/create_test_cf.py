# -*- coding: utf-8 -*-
"""Сборка базовой XML-конфигурации для тестовой базы из XML-выгрузок 1С.

Скрипт работает с XML формата Конфигуратора 1С, не с EDT-проектами.
Base берется как основа, adapter накладывается поверх нее.
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
    output_dir: Path


@dataclass(frozen=True)
class BuildStats:
    base_files: int
    adapter_files: int
    adapter_child_objects: int


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


def read_zip_entry(archive_path: Path, entry_name: str) -> bytes:
    with zipfile.ZipFile(archive_path) as archive:
        try:
            with archive.open(entry_name) as entry:
                return entry.read()
        except KeyError as error:
            raise FileNotFoundError(f"Archive {archive_path} does not contain {entry_name}") from error


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


def build_test_database(options: BuildOptions) -> BuildStats:
    # Порядок важен: base создает каталог результата, adapter добавляет
    # подсистему Kafka.
    base_files = unpack_base_archive(options.base_archive, options.output_dir)
    adapter_files = merge_adapter_archive(options.adapter_archive, options.output_dir)
    adapter_child_objects = merge_configuration_child_objects(
        options.adapter_archive,
        options.output_dir,
    )

    return BuildStats(
        base_files=base_files,
        adapter_files=adapter_files,
        adapter_child_objects=adapter_child_objects,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = RussianArgumentParser(
        description=(
            "Собирает базовый XML из архивов XML-выгрузок base и adapter. "
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
