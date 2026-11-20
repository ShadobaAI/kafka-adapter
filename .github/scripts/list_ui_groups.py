#!/usr/bin/env python3
import json
import sys
from pathlib import Path


def feature_groups(root: Path) -> list[str]:
    groups = set()
    for feature in root.rglob("*.feature"):
        if not feature.is_file():
            continue
        parts = feature.relative_to(root).parts
        if len(parts) < 3:
            raise ValueError(f"Feature outside features/<section>/<object>: {feature}")
        groups.add("/".join(parts[:2]))
    if not groups:
        raise ValueError(f"No UI feature groups in {root}")
    return sorted(groups)


if __name__ == "__main__":
    print("ui_groups=" + json.dumps(feature_groups(Path(sys.argv[1])), ensure_ascii=False))
