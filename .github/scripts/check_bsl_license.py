#!/usr/bin/env python3
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
LICENSE_MARKER = re.compile(
    r"\b(?:MPL[-\s]+"
    r"|Mozilla\s+Public\s+License[,\s]+(?:v(?:ersion)?\.?\s*)?"
    r"|mozilla\.org/MPL/)2\.0\b(?!\.\d)",
    re.IGNORECASE,
)


def has_license_header(path: Path) -> bool:
    comments = []
    with path.open(encoding="utf-8-sig") as module:
        for line in module:
            line = line.strip()
            if line.startswith("//"):
                comments.append(line[2:].strip())
            elif line:
                break

    return bool(LICENSE_MARKER.search(" ".join(comments)))


def main() -> int:
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "*.bsl"], cwd=REPO_ROOT
    )
    filenames = tracked.decode("utf-8").split("\0")[:-1]
    failed = 0
    for filename in filenames:
        try:
            if has_license_header(REPO_ROOT / filename):
                continue
            message = "Missing MPL-2.0 license notice in the leading // comments"
        except (OSError, UnicodeError) as error:
            message = str(error)
        print(f"{filename!r}: {message}", file=sys.stderr)
        failed += 1

    print(f"Checked {len(filenames)} BSL files. Failed: {failed}.")
    return int(failed != 0)


if __name__ == "__main__":
    raise SystemExit(main())
