#!/usr/bin/env python3
"""Проверка production-базы SonarQube перед анализом релиза."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

from sonar_static_report import SonarClient, SonarError, analysis_version, collect_analysis_history


def latest_stable_tag(releases: list[dict], current_tag: str) -> str:
    stable = [release for release in releases
              if release.get("draft") is False and release.get("prerelease") is False
              and release.get("tag_name") != current_tag and release.get("published_at")]
    if not stable:
        raise SonarError("No previous published stable release was found")
    latest_date = max(dt.datetime.fromisoformat(release["published_at"].replace("Z", "+00:00")) for release in stable)
    latest = [release for release in stable
              if dt.datetime.fromisoformat(release["published_at"].replace("Z", "+00:00")) == latest_date]
    if len(latest) != 1 or not latest[0].get("tag_name"):
        raise SonarError("The latest stable release is ambiguous")
    return latest[0]["tag_name"]


def github_releases() -> list[dict]:
    repository = os.environ["GITHUB_REPOSITORY"]
    headers = {"Accept": "application/vnd.github+json", "Authorization": f'Bearer {os.environ["GH_TOKEN"]}'}
    releases = []
    page = 1
    while True:
        query = urllib.parse.urlencode({"per_page": 100, "page": page})
        request = urllib.request.Request(f'{os.environ["GITHUB_API_URL"]}/repos/{repository}/releases?{query}', headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            items = json.load(response)
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise SonarError("Invalid GitHub releases response")
        releases.extend(items)
        if len(items) < 100:
            return releases
        page += 1


def verify_baseline(client: SonarClient, project: str, stable_tag: str, stable_revision: str) -> None:
    component = client.get("api/components/show", {"component": project}).get("component", {})
    if component.get("key") != project or component.get("qualifier") != "TRK":
        raise SonarError("Unexpected SonarQube project response")
    branches = client.get("api/project_branches/list", {"project": project}).get("branches", [])
    main = [branch.get("name") for branch in branches if branch.get("isMain")]
    if len(main) != 1 or not main[0]:
        raise SonarError("SonarQube main branch is missing or ambiguous")
    period = client.get("api/new_code_periods/show", {"project": project, "branch": main[0]})
    if period.get("type") != "SPECIFIC_ANALYSIS" or not period.get("value"):
        raise SonarError("Configure a Specific analysis production baseline before analysis")
    analyses = collect_analysis_history(client, project, None)
    baseline = next((analysis for analysis in analyses if analysis.get("key") == period["value"]), None)
    if baseline is None or analysis_version(baseline) != stable_tag or baseline.get("revision") != stable_revision:
        raise SonarError(f"SonarQube baseline does not match the latest stable release {stable_tag}")


def main() -> int:
    stable_tag = latest_stable_tag(github_releases(), os.environ["RELEASE_TAG"])
    stable_revision = subprocess.check_output(["git", "rev-parse", "--verify", f"refs/tags/{stable_tag}^{{commit}}"], text=True).strip()
    client = SonarClient(os.environ["SONAR_HOST_URL"], token=os.environ["SONAR_TOKEN"])
    verify_baseline(client, os.environ["SONAR_PROJECT_KEY"], stable_tag, stable_revision)
    print(f"Production baseline verified: {stable_tag}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SonarError, KeyError, ValueError, urllib.error.URLError, subprocess.CalledProcessError) as exc:
        print(f"Production baseline verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
