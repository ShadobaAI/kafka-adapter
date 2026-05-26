# -*- coding: utf-8 -*-
"""Создание тестовой файловой ИБ из DT-шаблона и общей XML-конфигурации.

Общий XML собирается соседним create_test_cf.py. Затем vrunner init-dev
загружает DT-шаблон и XML в чистую файловую базу, а расширения грузятся
отдельными вызовами vrunner loadext.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
VA_EXTENSION_NAME = "VAExtension"
YAXUNIT_EXTENSION_NAME = "YAXUNIT"
CONFIG_XML_DIR_NAME = "config-xml"


class ScriptError(RuntimeError):
    pass


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
class Options:
    workdir: Path
    ib_path: Path
    base_archive: Path
    adapter_archive: Path
    examples_archive: Path
    yaxunit: Path | None
    va_extension: Path | None
    template_dt: Path


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = RussianArgumentParser(
        description=(
            "Создает тестовую файловую ИБ: собирает общий XML через create_test_cf.py, "
            "загружает шаблон DT и XML через vrunner init-dev, "
            "опционально загружает расширения YAXUNIT/VAExtension через vrunner loadext."
        )
    )
    parser.add_argument(
        "--ib",
        dest="ib_path",
        type=Path,
        required=True,
        metavar="PATH",
        help="путь к файловой ИБ.",
    )
    parser.add_argument(
        "--dt",
        dest="template_dt",
        type=Path,
        required=True,
        metavar="PATH",
        help="шаблон информационной базы.",
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
        "-y",
        "--yaxunit",
        type=Path,
        metavar="PATH",
        help="опционально: файл YAXUNIT.cfe.",
    )
    parser.add_argument(
        "--va",
        dest="va_extension",
        type=Path,
        metavar="PATH",
        help="опционально: файл VAExtension.cfe.",
    )
    return parser


def absolute(path: Path, base_dir: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def parse_options(argv: list[str] | None) -> Options:
    parser = build_parser()
    args = parser.parse_args(argv)
    workdir = Path.cwd().resolve()

    return Options(
        workdir=workdir,
        ib_path=absolute(args.ib_path, workdir),
        base_archive=absolute(args.base_archive, workdir),
        adapter_archive=absolute(args.adapter_archive, workdir),
        examples_archive=absolute(args.examples_archive, workdir),
        yaxunit=absolute(args.yaxunit, workdir) if args.yaxunit else None,
        va_extension=absolute(args.va_extension, workdir) if args.va_extension else None,
        template_dt=absolute(args.template_dt, workdir),
    )


def builder_script() -> Path:
    # create_test_cf.py должен поставляться рядом с этим скриптом.
    # Зависимости от локальной структуры workspace здесь быть не должно.
    return SCRIPT_DIR / "create_test_cf.py"


def config_xml_dir(options: Options) -> Path:
    # Временный каталог создается в текущем рабочем каталоге запуска.
    # Он удаляется после init-dev независимо от результата загрузки XML.
    return options.workdir / CONFIG_XML_DIR_NAME


def require_file(path: Path, description: str) -> None:
    if not path.is_file():
        raise ScriptError(f"{description} не найден: {path}")


def require_dir(path: Path, description: str) -> None:
    if not path.is_dir():
        raise ScriptError(f"{description} не найден: {path}")


def require_command(command: str) -> None:
    if shutil.which(command) is None:
        raise ScriptError(f"Команда не найдена в PATH: {command}")


def validate_options(options: Options) -> None:
    require_dir(options.workdir, "Текущий каталог")
    require_file(options.base_archive, "Архив XML базы")
    require_file(options.adapter_archive, "Архив XML адаптера")
    require_file(options.examples_archive, "Архив XML примеров")
    require_file(options.template_dt, "Шаблон DT")
    if options.va_extension is not None:
        require_file(options.va_extension, "Расширение Vanessa Automation")
        if options.va_extension.name.lower() != "vaextension.cfe":
            raise ScriptError(
                f"Расширение Vanessa Automation должно называться VAExtension.cfe: {options.va_extension}"
            )
    require_file(builder_script(), "Скрипт сборки XML")
    require_command("vrunner")

    if options.yaxunit is not None:
        require_file(options.yaxunit, "Расширение YAxUnit")
        if options.yaxunit.name.lower() != "yaxunit.cfe":
            raise ScriptError(f"Расширение YAxUnit должно называться YAXUNIT.cfe: {options.yaxunit}")


def quote_command(args: Sequence[str | Path]) -> str:
    return subprocess.list2cmdline([str(arg) for arg in args])


def ensure_safe_remove_path(path: Path) -> Path:
    # Защита от случайного удаления корня диска или некорректно вычисленного пути.
    resolved = path.resolve()
    if resolved == Path(resolved.anchor) or resolved.parent == resolved:
        raise ScriptError(f"Небезопасный путь для удаления: {resolved}")
    return resolved


def remove_tree(path: Path) -> None:
    resolved = ensure_safe_remove_path(path)
    if not resolved.exists():
        return
    if not resolved.is_dir():
        raise ScriptError(f"Ожидался каталог для удаления: {resolved}")

    print(f"Удаление каталога: {resolved}")
    shutil.rmtree(resolved)


def run_command(args: Sequence[str | Path], options: Options) -> None:
    print(f"> {quote_command(args)}")
    completed = subprocess.run(
        [str(arg) for arg in args],
        cwd=options.workdir,
        check=False,
    )
    if completed.returncode != 0:
        raise ScriptError(f"Команда завершилась с кодом {completed.returncode}: {quote_command(args)}")


def ib_connection(options: Options) -> str:
    return f"/F{options.ib_path}"


def build_config_xml(options: Options) -> None:
    # Сборка общего XML делегируется create_test_cf.py, чтобы правила merge
    # были едиными для отдельной сборки XML и для сборки DT.
    command: list[str | Path] = [
        sys.executable,
        builder_script(),
        "--base",
        options.base_archive,
        "--adapter",
        options.adapter_archive,
        "--examples",
        options.examples_archive,
        "--output",
        config_xml_dir(options),
    ]

    run_command(command, options)


def init_infobase(options: Options) -> None:
    # init-dev создает чистую файловую ИБ из DT-шаблона и собранного XML.
    run_command(
        [
            "vrunner",
            "init-dev",
            "--src",
            config_xml_dir(options),
            "--dt",
            options.template_dt,
            "--ibcmd",
            "--ibconnection",
            ib_connection(options),
        ],
        options,
    )


def load_extension(options: Options, extension_file: Path, extension_name: str) -> None:
    # CFE не попадают в общий XML: каждое расширение загружается поверх ИБ.
    run_command(
        [
            "vrunner",
            "loadext",
            "-f",
            extension_file,
            "--extension",
            extension_name,
            "--updatedb",
            "--ibcmd",
            "--ibconnection",
            ib_connection(options),
        ],
        options,
    )


def run(options: Options) -> None:
    validate_options(options)

    # Итоговая ИБ пересоздается полностью, поэтому путь --ib должен указывать
    # только на рабочий каталог тестовой базы.
    remove_tree(options.ib_path)
    build_config_xml(options)
    try:
        init_infobase(options)
    finally:
        remove_tree(config_xml_dir(options))

    if options.va_extension is not None:
        load_extension(options, options.va_extension, VA_EXTENSION_NAME)
    if options.yaxunit is not None:
        load_extension(options, options.yaxunit, YAXUNIT_EXTENSION_NAME)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()

    try:
        options = parse_options(argv)
        run(options)
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
