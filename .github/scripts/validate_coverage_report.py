"""Проверка, что CI действительно собрал покрытие кода адаптера."""
from __future__ import annotations

import argparse
from pathlib import Path
from xml.etree import ElementTree


def validate_report(path: Path) -> tuple[int, int, int]:
    root = ElementTree.parse(path).getroot()
    if root.tag != "coverage" or root.get("version") != "1":
        raise ValueError("Ожидался Generic Coverage XML версии 1")

    files = root.findall("file")
    total = 0
    covered = 0
    for file in files:
        if not file.get("path"):
            raise ValueError("В отчёте отсутствует путь исходного файла")
        seen_lines = set()
        for line in file.findall("lineToCover"):
            number = int(line.get("lineNumber", "0"))
            if number <= 0 or number in seen_lines:
                raise ValueError(f"Некорректная или повторная строка {number}: {file.get('path')}")
            seen_lines.add(number)
            if line.get("covered") not in {"true", "false"}:
                raise ValueError(f"Некорректный covered: {file.get('path')}:{number}")
            total += 1
            covered += line.get("covered") == "true"

    if total == 0:
        raise ValueError("В отчёте нет строк для покрытия")
    if covered == 0:
        raise ValueError("Нет покрытых строк адаптера; проверь подключение ibsrv к dbgs и сопоставление исходников")
    return len(files), total, covered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        files, total, covered = validate_report(args.report)
    except (OSError, ElementTree.ParseError, ValueError) as error:
        print(f"::error::{args.report}: {error}")
        return 1
    print(f"{args.report}: файлов {files}, покрыто {covered}/{total} строк ({covered / total:.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
