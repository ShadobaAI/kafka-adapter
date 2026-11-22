"""Проверка, что CI действительно собрал покрытие кода адаптера."""
from __future__ import annotations

import argparse
from pathlib import Path
from xml.etree import ElementTree


NO_COVERAGE = "Нет покрытых строк адаптера; проверь подключение ibsrv к dbgs и сопоставление исходников"


def validate_report(path: Path, *, allow_uncovered: bool = False) -> tuple[int, int, int]:
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
    if covered == 0 and not allow_uncovered:
        raise ValueError(NO_COVERAGE)
    return len(files), total, covered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--allow-uncovered", action="store_true", help="Проверить XML отдельной UI-группы")
    args = parser.parse_args()
    covered_lines = 0
    for report in args.reports:
        try:
            files, total, covered = validate_report(report, allow_uncovered=True)
        except (OSError, ElementTree.ParseError, ValueError) as error:
            print(f"::error::{report}: {error}")
            return 1
        print(f"{report}: файлов {files}, покрыто {covered}/{total} строк ({covered / total:.1%})")
        covered_lines += covered
    if not args.allow_uncovered and covered_lines == 0:
        print(f"::error::{NO_COVERAGE}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
