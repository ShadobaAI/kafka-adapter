# -*- coding: utf-8 -*-
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
TESTER_UPDATE_HANDLERS_PROCEDURE = f"кфк_т_{UPDATE_HANDLERS_PROCEDURE}"
UPDATE_DB_MODULE_PATH = Path("CommonModules") / UPDATE_DB_MODULE_NAME / "Ext" / "Module.bsl"
UPDATE_DB_MODULE_ARCHIVE_ENTRY = f"CommonModules/{UPDATE_DB_MODULE_NAME}/Ext/Module.bsl"
APPLICATION_MODULE_ARCHIVE_ENTRIES = (
    "Ext/ManagedApplicationModule.bsl",
    "Ext/OrdinaryApplicationModule.bsl",
)

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
    tester_archive: Path
    yaxunit_archive: Path | None
    output_dir: Path


@dataclass(frozen=True)
class ApplicationModuleMergeStats:
    copied_modules: int
    variable_declarations: int
    methods: int


@dataclass(frozen=True)
class BuildStats:
    base_files: int
    adapter_files: int
    adapter_child_objects: int
    tester_files: int
    tester_child_objects: int
    yaxunit_files: int
    yaxunit_child_objects: int
    yaxunit_application_modules: ApplicationModuleMergeStats
    update_handler_lines: int
    user_type_nodes: int


BASE_EXCLUSIONS = ArchiveExclusions(
    roots=frozenset({"ConfigDumpInfo.xml"}),
)

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

TESTER_EXCLUSIONS = ArchiveExclusions(
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

TESTER_EXCLUDED_CHILD_OBJECTS: frozenset[ChildObjectKey] = frozenset(
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
    for argument_name, description in (
        ("base_archive", "Архив XML базы"),
        ("adapter_archive", "Архив XML адаптера"),
        ("tester_archive", "Архив XML тестера"),
        ("output_dir", "Каталог выгрузки XML"),
    ):
        if getattr(args, argument_name) is None:
            raise ValueError(f"Не указан обязательный параметр: {description}")

    yaxunit_archive = None
    if args.yaxunit_archive is not None:
        yaxunit_archive = validate_file(args.yaxunit_archive, "YAxUnit")

    return BuildOptions(
        base_archive=validate_file(args.base_archive, "База"),
        adapter_archive=validate_file(args.adapter_archive, "Адаптер"),
        tester_archive=validate_file(args.tester_archive, "Тестер"),
        yaxunit_archive=yaxunit_archive,
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


def merge_tester_archive(archive_path: Path, output_dir: Path) -> int:
    return extract_zip(archive_path, output_dir, TESTER_EXCLUSIONS)


def merge_yaxunit_archive(archive_path: Path, output_dir: Path) -> int:
    return extract_zip(archive_path, output_dir, CONFIGURATION_EXCLUSIONS)


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


@dataclass(frozen=True)
class BslMethod:
    name: str
    kind: str
    start: int
    end: int


def is_region_start(line: str, region_name: str) -> bool:
    return line.strip().lower() == f"#область {region_name}".lower()


def is_region_end(line: str) -> bool:
    return line.strip().lower() == "#конецобласти"


def region_bounds(lines: list[str], region_name: str) -> tuple[int, int] | None:
    for start_index, line in enumerate(lines):
        if not is_region_start(line, region_name):
            continue

        for end_index in range(start_index + 1, len(lines)):
            if is_region_end(lines[end_index]):
                return start_index, end_index

        raise ValueError(f"Region end not found: {region_name}")

    return None


def bsl_method_start(line: str) -> tuple[str, str] | None:
    stripped = line.lstrip()
    keyword_by_kind = {
        "процедура": "procedure",
        "procedure": "procedure",
        "функция": "function",
        "function": "function",
    }

    for keyword, kind in keyword_by_kind.items():
        prefix = f"{keyword} "
        if not stripped.lower().startswith(prefix):
            continue

        rest = stripped[len(prefix) :].lstrip()
        name = rest.split("(", maxsplit=1)[0].strip()
        if name:
            return name, kind

    return None


def is_bsl_method_end(line: str, kind: str) -> bool:
    stripped = line.strip().lower()
    if kind == "procedure":
        return stripped in {"конецпроцедуры", "endprocedure"}
    if kind == "function":
        return stripped in {"конецфункции", "endfunction"}
    return False


def iter_bsl_methods(lines: list[str]) -> list[BslMethod]:
    methods: list[BslMethod] = []
    index = 0

    while index < len(lines):
        method_start = bsl_method_start(lines[index])
        if method_start is None:
            index += 1
            continue

        name, kind = method_start
        for end_index in range(index + 1, len(lines)):
            if is_bsl_method_end(lines[end_index], kind):
                methods.append(BslMethod(name=name, kind=kind, start=index, end=end_index))
                index = end_index + 1
                break
        else:
            raise ValueError(f"Method end not found: {name}")

    return methods


def bsl_method_bounds(lines: list[str], method_name: str) -> BslMethod:
    normalized_name = method_name.lower()

    for method in iter_bsl_methods(lines):
        if method.name.lower() == normalized_name:
            return method

    raise ValueError(f"Method not found: {method_name}")


def bsl_method_body_start(lines: list[str], method: BslMethod) -> int:
    if ")" in lines[method.start]:
        return method.start + 1

    for index in range(method.start + 1, method.end):
        if ")" in lines[index]:
            return index + 1

    return method.start + 1


def bsl_method_body(lines: list[str], method: BslMethod) -> list[str]:
    return trimmed_body(lines[bsl_method_body_start(lines, method) : method.end])


def variable_names(line: str) -> tuple[str, ...]:
    stripped = line.strip()
    lower = stripped.lower()

    if lower.startswith("перем "):
        declaration = stripped[len("Перем ") :]
    elif lower.startswith("var "):
        declaration = stripped[len("Var ") :]
    else:
        return ()

    declaration = declaration.split("//", maxsplit=1)[0]
    declaration = declaration.replace(";", " ")

    names: list[str] = []
    for part in declaration.split(","):
        words = part.strip().split()
        if not words:
            continue

        name = words[0]
        if name.lower() not in {"экспорт", "export"}:
            names.append(name)

    return tuple(names)


def variable_declaration_blocks(lines: list[str]) -> list[tuple[tuple[str, ...], list[str]]]:
    bounds = region_bounds(lines, "ОписаниеПеременных")
    if bounds is None:
        return []

    _, region_end = bounds
    blocks: list[tuple[tuple[str, ...], list[str]]] = []
    index = bounds[0] + 1

    while index < region_end:
        names = variable_names(lines[index])
        if not names:
            index += 1
            continue

        block_end = index + 1
        while (
            block_end < region_end
            and lines[block_end].startswith((" ", "\t"))
            and lines[block_end].lstrip().startswith("//")
        ):
            block_end += 1

        blocks.append((names, lines[index:block_end]))
        index = block_end

    return blocks


def all_variable_names(lines: list[str]) -> set[str]:
    result: set[str] = set()
    for line in lines:
        result.update(name.lower() for name in variable_names(line))
    return result


def ensure_variables_region(lines: list[str]) -> tuple[int, int]:
    bounds = region_bounds(lines, "ОписаниеПеременных")
    if bounds is not None:
        return bounds

    insertion_index = 0
    while (
        insertion_index < len(lines)
        and (lines[insertion_index].strip() == "" or lines[insertion_index].lstrip().startswith("//"))
    ):
        insertion_index += 1

    lines[insertion_index:insertion_index] = [
        "#Область ОписаниеПеременных",
        "",
        "#КонецОбласти",
        "",
    ]
    return insertion_index, insertion_index + 2


def insert_missing_variable_declarations(target_lines: list[str], source_lines: list[str]) -> int:
    existing_names = all_variable_names(target_lines)
    inserted_lines: list[str] = []
    inserted_count = 0

    for names, block in variable_declaration_blocks(source_lines):
        missing_names = [name for name in names if name.lower() not in existing_names]
        if not missing_names:
            continue

        inserted_lines.extend(block)
        inserted_count += len(missing_names)
        existing_names.update(name.lower() for name in names)

    if not inserted_lines:
        return 0

    _, region_end = ensure_variables_region(target_lines)
    if region_end > 0 and target_lines[region_end - 1].strip() != "":
        inserted_lines = ["", *inserted_lines]
    if inserted_lines[-1].strip() != "":
        inserted_lines.append("")

    target_lines[region_end:region_end] = inserted_lines
    return inserted_count


def append_bsl_method(target_lines: list[str], method_lines: list[str]) -> None:
    while target_lines and target_lines[-1].strip() == "":
        target_lines.pop()

    target_lines.extend(["", *method_lines])


def merge_bsl_methods(target_lines: list[str], source_lines: list[str]) -> int:
    merged_count = 0

    for source_method in iter_bsl_methods(source_lines):
        source_body = bsl_method_body(source_lines, source_method)
        if not source_body:
            continue

        try:
            target_method = bsl_method_bounds(target_lines, source_method.name)
        except ValueError:
            append_bsl_method(target_lines, source_lines[source_method.start : source_method.end + 1])
            merged_count += 1
            continue

        while target_method.end > target_method.start + 1 and target_lines[target_method.end - 1].strip() == "":
            del target_lines[target_method.end - 1]
            target_method = bsl_method_bounds(target_lines, source_method.name)

        target_lines[target_method.end : target_method.end] = ["", *source_body, ""]
        merged_count += 1

    return merged_count


def merge_yaxunit_application_module(
    yaxunit_archive: Path,
    output_dir: Path,
    entry_name: str,
) -> ApplicationModuleMergeStats:
    target_path = output_dir.resolve() / Path(entry_name)
    source_text = decode_text(read_zip_entry(yaxunit_archive, entry_name))

    if not target_path.is_file():
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(source_text, encoding="utf-8")
        return ApplicationModuleMergeStats(copied_modules=1, variable_declarations=0, methods=0)

    target_text = target_path.read_text(encoding="utf-8-sig")
    source_lines = source_text.splitlines()
    target_lines = target_text.splitlines()

    variable_declarations = insert_missing_variable_declarations(target_lines, source_lines)
    methods = merge_bsl_methods(target_lines, source_lines)

    if variable_declarations or methods:
        newline = detect_newline(target_text)
        target_path.write_text(newline.join(target_lines) + newline, encoding="utf-8")

    return ApplicationModuleMergeStats(
        copied_modules=0,
        variable_declarations=variable_declarations,
        methods=methods,
    )


def merge_yaxunit_application_modules(yaxunit_archive: Path, output_dir: Path) -> ApplicationModuleMergeStats:
    copied_modules = 0
    variable_declarations = 0
    methods = 0

    for entry_name in APPLICATION_MODULE_ARCHIVE_ENTRIES:
        stats = merge_yaxunit_application_module(yaxunit_archive, output_dir, entry_name)
        copied_modules += stats.copied_modules
        variable_declarations += stats.variable_declarations
        methods += stats.methods

    return ApplicationModuleMergeStats(
        copied_modules=copied_modules,
        variable_declarations=variable_declarations,
        methods=methods,
    )


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


def merge_update_handlers_procedure(tester_archive: Path, output_dir: Path) -> int:
    module_path = output_dir.resolve() / UPDATE_DB_MODULE_PATH
    if not module_path.is_file():
        raise FileNotFoundError(f"Update module file not found: {module_path}")

    tester_module_text = decode_text(read_zip_entry(tester_archive, UPDATE_DB_MODULE_ARCHIVE_ENTRY))
    tester_body = procedure_body(
        tester_module_text.splitlines(),
        TESTER_UPDATE_HANDLERS_PROCEDURE,
    )

    if not tester_body:
        return 0

    module_text = module_path.read_text(encoding="utf-8-sig")
    module_lines = module_text.splitlines()
    insert_before_procedure_end(module_lines, UPDATE_HANDLERS_PROCEDURE, tester_body)

    newline = detect_newline(module_text)
    module_path.write_text(newline.join(module_lines) + newline, encoding="utf-8")

    return len(tester_body)


def build_test_database(options: BuildOptions) -> BuildStats:
    base_files = unpack_base_archive(options.base_archive, options.output_dir)
    adapter_files = merge_adapter_archive(options.adapter_archive, options.output_dir)
    adapter_child_objects = merge_configuration_child_objects(
        options.adapter_archive,
        options.output_dir,
    )
    tester_files = merge_tester_archive(options.tester_archive, options.output_dir)
    tester_child_objects = merge_configuration_child_objects(
        options.tester_archive,
        options.output_dir,
        excluded_child_objects=TESTER_EXCLUDED_CHILD_OBJECTS,
    )
    yaxunit_files = 0
    yaxunit_child_objects = 0
    yaxunit_application_modules = ApplicationModuleMergeStats(
        copied_modules=0,
        variable_declarations=0,
        methods=0,
    )

    if options.yaxunit_archive is not None:
        yaxunit_files = merge_yaxunit_archive(options.yaxunit_archive, options.output_dir)
        yaxunit_child_objects = merge_configuration_child_objects(
            options.yaxunit_archive,
            options.output_dir,
        )
        yaxunit_application_modules = merge_yaxunit_application_modules(
            options.yaxunit_archive,
            options.output_dir,
        )

    update_handler_lines = merge_update_handlers_procedure(
        options.tester_archive,
        options.output_dir,
    )
    user_type_nodes = update_user_defined_type(options.output_dir)

    return BuildStats(
        base_files=base_files,
        adapter_files=adapter_files,
        adapter_child_objects=adapter_child_objects,
        tester_files=tester_files,
        tester_child_objects=tester_child_objects,
        yaxunit_files=yaxunit_files,
        yaxunit_child_objects=yaxunit_child_objects,
        yaxunit_application_modules=yaxunit_application_modules,
        update_handler_lines=update_handler_lines,
        user_type_nodes=user_type_nodes,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = RussianArgumentParser(
        description=(
            "Собирает XML-конфигурацию тестовой 1С базы из архивов XML-выгрузок конфигураций. "
            "Файлы расширений .cfe сюда не передаются."
        )
    )
    parser.add_argument(
        "-b",
        "--base",
        dest="base_archive",
        type=Path,
        metavar="PATH",
        help="архив XML-выгрузки базовой конфигурации.",
    )
    parser.add_argument(
        "-a",
        "--adapter",
        dest="adapter_archive",
        type=Path,
        metavar="PATH",
        help="архив XML-выгрузки конфигурации адаптера.",
    )
    parser.add_argument(
        "-t",
        "--tester",
        dest="tester_archive",
        type=Path,
        metavar="PATH",
        help="архив XML-выгрузки конфигурации тестера.",
    )
    parser.add_argument(
        "-y",
        "--yaxunit",
        dest="yaxunit_archive",
        type=Path,
        metavar="PATH",
        help="опциональный архив XML-выгрузки конфигурации YAxUnit.",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_dir",
        type=Path,
        metavar="PATH",
        help="каталог для результата: собранной XML-конфигурации.",
    )
    return parser


def print_summary(options: BuildOptions, stats: BuildStats) -> None:
    print(f"Base XML unpacked from {options.base_archive} to {options.output_dir}: {stats.base_files} files")
    print(f"Adapter XML merged from {options.adapter_archive}: {stats.adapter_files} files")
    print(f"Adapter Configuration/ChildObjects merged: {stats.adapter_child_objects} items")
    print(f"Tester XML merged from {options.tester_archive}: {stats.tester_files} files")
    print(f"Tester Configuration/ChildObjects merged: {stats.tester_child_objects} items")
    if options.yaxunit_archive is None:
        print("YAxUnit XML merge skipped: no archive provided")
    else:
        print(f"YAxUnit XML merged from {options.yaxunit_archive}: {stats.yaxunit_files} files")
        print(f"YAxUnit Configuration/ChildObjects merged: {stats.yaxunit_child_objects} items")
        print(
            "YAxUnit application modules merged: "
            f"{stats.yaxunit_application_modules.copied_modules} copied, "
            f"{stats.yaxunit_application_modules.variable_declarations} variables, "
            f"{stats.yaxunit_application_modules.methods} methods"
        )
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
