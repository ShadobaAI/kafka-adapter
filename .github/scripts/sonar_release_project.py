#!/usr/bin/env python3
"""Выбор SonarQube project по Git-ветке релиза."""

import os
from hashlib import sha256
from urllib.parse import quote, urlencode


def project_key(repository: str, branch: str) -> str:
    if not repository or not branch:
        raise ValueError("Repository and release branch must not be empty")
    if branch == "main":
        return repository
    # ':' допустим в Sonar projectKey; URL-encoding сохраняет различие Git-веток.
    encoded_branch = quote(branch, safe="-_.").replace("%", ":")
    key = f"{repository}:{encoded_branch}"
    if len(key) > 400:
        # '::' не встречается в encoded_branch, поэтому пространства ключей различны.
        key = f"{repository}::sha256:{sha256(branch.encode('utf-8')).hexdigest()}"
    return key


def main() -> None:
    key = project_key(os.environ["SONAR_BASELINE_PROJECT_KEY"], os.environ["SONAR_BRANCH_NAME"])
    query = urlencode({"id": key})
    print(f"SONAR_PROJECT_KEY={key}")
    print(f'SONAR_DASHBOARD_URL={os.environ["SONAR_HOST_URL"].rstrip("/")}/dashboard?{query}')


if __name__ == "__main__":
    main()
