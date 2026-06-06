"""Remove SSL-dependent objects before building the extension as CF."""
import argparse
import re
import shutil
from pathlib import Path


def patch_file(path: Path, func) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(func(text), encoding="utf-8")


def remove_ssl_objects(project_dir: Path) -> None:
    shutil.rmtree(project_dir / "src/Catalogs/Пользователи", ignore_errors=True)

    patch_file(
        project_dir / "src/DefinedTypes/кфкПользователь/кфкПользователь.mdo",
        lambda text: text.replace("CatalogRef.Пользователи", "UUID"),
    )

    def patch_mdo(text: str) -> str:
        return re.sub(r"\s*<catalogs>Catalog\.Пользователи</catalogs>", "", text)

    patch_file(project_dir / "src/Configuration/Configuration.mdo", patch_mdo)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", nargs="?", default=".")
    args = parser.parse_args()

    remove_ssl_objects(Path(args.project_dir))


if __name__ == "__main__":
    main()
