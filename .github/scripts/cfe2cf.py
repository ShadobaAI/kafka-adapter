#!/usr/bin/env python3
"""Convert an EDT extension project (CFE) to an EDT configuration project (CF)."""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path


EDT_PROJECT_ENTRIES = (".project", ".settings", "DT-INF", "src")
EXTENSION_TAGS = (
    "objectBelonging",
    "extension",
    "keepMappingToExtendedConfigurationObjectsByIDs",
    "namePrefix",
    "configurationExtensionPurpose",
    "configurationExtensionCompatibilityMode",
)


def copy_edt_project(source_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for entry in EDT_PROJECT_ENTRIES:
        source = source_dir / entry
        target = output_dir / entry
        if not source.exists():
            sys.exit(f"ERROR: EDT project entry was not found: {source}")

        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)


def patch_file(path: Path, transform) -> None:
    content = path.read_text(encoding="utf-8")
    path.write_text(transform(content), encoding="utf-8")
    print(f"  patched: {path}")


def patch_mdo(project_dir: Path) -> None:
    def transform(content: str) -> str:
        for tag in EXTENSION_TAGS:
            content = re.sub(rf"\s*<{tag}/>", "", content)
            content = re.sub(rf"\s*<{tag}>.*?</{tag}>", "", content, flags=re.DOTALL)
        return content

    patch_file(project_dir / "src/Configuration/Configuration.mdo", transform)


def patch_project(project_dir: Path) -> None:
    patch_file(
        project_dir / ".project",
        lambda content: content.replace("V8ExtensionNature", "V8ConfigurationNature"),
    )


def patch_pmf(project_dir: Path) -> None:
    def transform(content: str) -> str:
        lines = [line for line in content.splitlines(keepends=True) if "Base-Project" not in line]
        return "".join(lines)

    patch_file(project_dir / "DT-INF/PROJECT.PMF", transform)


def convert_cfe_to_cf(source_dir: Path, output_dir: Path) -> None:
    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()

    if source_dir != output_dir:
        copy_edt_project(source_dir, output_dir)

    patch_mdo(output_dir)
    patch_project(output_dir)
    patch_pmf(output_dir)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", nargs="?", default=".")
    parser.add_argument("output_dir", nargs="?")
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else Path(args.source_dir)
    print("Converting CFE EDT project to CF EDT project...")
    convert_cfe_to_cf(Path(args.source_dir), output_dir)
    print("Done.")


if __name__ == "__main__":
    main()
