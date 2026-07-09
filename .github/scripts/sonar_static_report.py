#!/usr/bin/env python3
"""Генератор статического подробного отчета SonarQube."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import pathlib
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable


DEFAULT_PROJECT = "kafka-adapter"
DEFAULT_URL = "http://localhost:9000"
DEFAULT_LANGUAGE = "bsl"
TEMPLATE_DIR = pathlib.Path(__file__).with_name("sonar-report-template")


class SonarError(RuntimeError):
    pass


class SonarClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: int = 30,
        pause: float = 0.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.pause = pause
        self.errors: list[dict[str, Any]] = []
        self.headers = {"Accept": "application/json,text/plain;q=0.9,*/*;q=0.8"}

        if token:
            raw = f"{token}:".encode("utf-8")
            self.headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")

    def get(self, path: str, params: dict[str, Any] | None = None, optional: bool = False) -> Any:
        if self.pause:
            time.sleep(self.pause)

        params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        query = urllib.parse.urlencode(params, doseq=True)
        url = f"{self.base_url}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{query}"

        req = urllib.request.Request(url, headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                body = response.read()
                content_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            error = {
                "path": path,
                "params": params,
                "status": exc.code,
                "reason": exc.reason,
                "body": detail[:2000],
            }
            self.errors.append(error)
            if optional:
                return {"_error": error}
            raise SonarError(f"{path}: HTTP {exc.code} {exc.reason}: {detail[:300]}") from exc
        except urllib.error.URLError as exc:
            error = {"path": path, "params": params, "error": str(exc.reason)}
            self.errors.append(error)
            if optional:
                return {"_error": error}
            raise SonarError(f"{path}: {exc.reason}") from exc

        text = body.decode("utf-8", errors="replace")
        if "json" in content_type:
            return json.loads(text) if text else {}

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def paged(
        self,
        path: str,
        params: dict[str, Any],
        item_key: str,
        page_size: int = 500,
        optional: bool = True,
    ) -> dict[str, Any]:
        items: list[Any] = []
        first: dict[str, Any] | None = None
        page = 1

        while True:
            page_params = dict(params)
            page_params.update({"p": page, "ps": page_size})
            data = self.get(path, page_params, optional=optional)
            if isinstance(data, dict) and "_error" in data:
                return {"items": items, "first": first, "error": data["_error"]}
            if not isinstance(data, dict):
                return {"items": items, "first": first, "error": {"body": data}}

            if first is None:
                first = data
            batch = data.get(item_key) or []
            items.extend(batch)

            paging = data.get("paging") or {}
            total = data.get("total", paging.get("total", len(items)))
            current_size = data.get("ps", paging.get("pageSize", page_size))
            if len(items) >= int(total or 0) or not batch or len(batch) < int(current_size or page_size):
                return {"items": items, "first": first, "total": total}
            page += 1


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def with_branch(params: dict[str, Any], branch: str | None) -> dict[str, Any]:
    result = dict(params)
    if branch:
        result["branch"] = branch
    return result


def with_language(params: dict[str, Any], language: str | None, param_name: str = "languages") -> dict[str, Any]:
    result = dict(params)
    if language:
        result[param_name] = language
    return result


def collect_current_version_analysis(
    client: SonarClient,
    project: str,
    branch: str | None,
    current_version: str | None,
    baseline_version: str | None,
) -> dict[str, Any]:
    data = client.get(
        "api/project_analyses/search",
        with_branch({"project": project, "ps": 50}, branch),
        optional=True,
    )
    if not isinstance(data, dict) or "_error" in data:
        return data

    result: dict[str, Any] = {}
    analyses = data.get("analyses") or []
    for analysis in analyses:
        if not isinstance(analysis, dict):
            continue
        events = [event for event in analysis.get("events", []) if isinstance(event, dict)]
        version_names = [
            event.get("name")
            for event in events
            if event.get("category") == "VERSION"
        ]
        if current_version and (analysis.get("projectVersion") == current_version or current_version in version_names):
            result.update({
                "version": current_version,
                "date": analysis.get("date"),
                "analysisKey": analysis.get("key"),
            })
        if baseline_version and (analysis.get("projectVersion") == baseline_version or baseline_version in version_names):
            quality_gate_event = next(
                (event for event in events if event.get("category") == "QUALITY_GATE"),
                None,
            )
            result["baseline"] = {
                "version": baseline_version,
                "date": analysis.get("date"),
                "analysisKey": analysis.get("key"),
                "qualityGateStatus": quality_gate_event.get("name") if quality_gate_event else None,
            }
        if result.get("date") and result.get("baseline"):
            return result

    if analyses and isinstance(analyses[0], dict):
        latest = analyses[0]
        result.setdefault("version", latest.get("projectVersion") or current_version)
        result.setdefault("date", latest.get("date"))
        result.setdefault("analysisKey", latest.get("key"))
    return result


def safe_collect(report: dict[str, Any], name: str, func: Callable[[], Any]) -> Any:
    try:
        value = func()
        report["raw"][name] = value
        return value
    except Exception as exc:  # noqa: BLE001 - отчет должен продолжаться при частичных ошибках API.
        error = {"section": name, "error": str(exc)}
        report["collection_errors"].append(error)
        report["raw"][name] = {"_error": error}
        return None


def collect_measures(
    client: SonarClient,
    component: str,
    metric_keys: list[str],
    branch: str | None,
    metric_types: dict[str, str] | None = None,
    chunk_size: int = 80,
) -> dict[str, Any]:
    measures: list[dict[str, Any]] = []
    errors: list[Any] = []

    metric_types = metric_types or {}
    no_period_types = {"DATA", "LEVEL"}
    unsupported_measure_types = {"STRING"}
    metric_keys = [key for key in metric_keys if metric_types.get(key) not in unsupported_measure_types]
    no_period_keys = {key for key in metric_keys if metric_types.get(key) in no_period_types}
    grouped_requests = [
        ([key for key in metric_keys if key not in no_period_keys], "metrics,period"),
        ([key for key in metric_keys if key in no_period_keys], "metrics"),
    ]

    for keys, additional_fields in grouped_requests:
        if not keys:
            continue
        for part in chunks(keys, chunk_size):
            data = client.get(
                "api/measures/component",
                with_branch(
                    {
                        "component": component,
                        "metricKeys": ",".join(part),
                        "additionalFields": additional_fields,
                    },
                    branch,
                ),
                optional=True,
            )
            if isinstance(data, dict) and "_error" in data:
                errors.append(data["_error"])
                continue
            component_data = data.get("component", {}) if isinstance(data, dict) else {}
            measures.extend(component_data.get("measures", []))

    # Дедупликация нужна на случай пересечения fallback-ключей и каталога метрик.
    deduped: dict[str, dict[str, Any]] = {}
    for measure in measures:
        metric = measure.get("metric")
        if metric:
            deduped[metric] = measure

    return {"component": component, "measures": list(deduped.values()), "errors": errors}

def collect_component_tree_measures(
    client: SonarClient,
    project: str,
    metric_keys: list[str],
    branch: str | None,
    language: str | None,
    metric_types: dict[str, str] | None = None,
    chunk_size: int = 75,
) -> dict[str, Any]:
    components: dict[str, dict[str, Any]] = {}
    errors: list[Any] = []
    first: dict[str, Any] | None = None
    total = 0
    metric_types = metric_types or {}
    component_metric_types = {"INT", "FLOAT", "PERCENT", "BOOL", "RATING", "MILLISEC", "WORK_DUR"}
    metric_keys = [key for key in metric_keys if not metric_types.get(key) or metric_types.get(key) in component_metric_types]

    for part in chunks(metric_keys, chunk_size):
        data = client.paged(
            "api/measures/component_tree",
            with_branch(
                {
                    "component": project,
                    "metricKeys": ",".join(part),
                    "qualifiers": "FIL,UTS",
                    "s": "path",
                },
                branch,
            ),
            "components",
            optional=True,
        )
        if first is None:
            first = data.get("first") if isinstance(data, dict) else None
        if data.get("error"):
            errors.append(data["error"])

        for component in data.get("items", []):
            if language and component.get("language") != language:
                continue
            key = component.get("key")
            if not key:
                continue
            current = components.setdefault(key, {k: v for k, v in component.items() if k != "measures"})
            current_measures = {measure.get("metric"): measure for measure in current.get("measures", [])}
            for measure in component.get("measures", []):
                metric = measure.get("metric")
                if metric:
                    current_measures[metric] = measure
            current["measures"] = list(current_measures.values())
        total = max(total, int(data.get("total") or 0))

    return {"items": list(components.values()), "first": first, "total": total, "errors": errors}


def collect_issues(
    client: SonarClient,
    project: str,
    branch: str | None,
    language: str | None,
    in_new_code_period: bool = False,
) -> dict[str, Any]:
    params = with_language(
        with_branch(
            {
                "componentKeys": project,
                "additionalFields": "_all",
                "s": "FILE_LINE",
                "asc": "true",
                "inNewCodePeriod": "true" if in_new_code_period else "",
            },
            branch,
        ),
        language,
    )
    result = client.paged("api/issues/search", params, "issues", optional=True)
    if result.get("error") and params.get("additionalFields"):
        params.pop("additionalFields", None)
        result = client.paged("api/issues/search", params, "issues", optional=True)
    return result


def collect_hotspots(
    client: SonarClient,
    project: str,
    branch: str | None,
    allowed_components: set[str] | None = None,
) -> dict[str, Any]:
    params_all = with_branch({"projectKey": project, "onlyMine": "false"}, branch)
    all_result = client.paged("api/hotspots/search", params_all, "hotspots", optional=True)
    if allowed_components is not None:
        all_result = dict(all_result)
        all_result["items"] = [
            hotspot for hotspot in all_result.get("items", []) if hotspot.get("component") in allowed_components
        ]
        all_result["filtered_total"] = len(all_result["items"])
    return {"all": all_result}


def collect_rules(client: SonarClient, issues: list[dict[str, Any]]) -> dict[str, Any]:
    rules: dict[str, Any] = {}
    for rule_key in sorted({issue.get("rule") for issue in issues if issue.get("rule")}):
        data = client.get("api/rules/show", {"key": rule_key, "actives": "true"}, optional=True)
        rules[rule_key] = data
    return rules


def collect_source_files(
    client: SonarClient,
    branch: str | None,
    issues: list[dict[str, Any]],
    hotspots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    seen: set[str] = set()

    for item in [*issues, *(hotspots or [])]:
        component = item.get("component")
        if not component or component in seen:
            continue
        seen.add(component)

        data = client.get("api/sources/lines", with_branch({"key": component}, branch), optional=True)
        result[component] = data
        # Исходники часто требуют отдельного права Browse/See Source Code.
        if isinstance(data, dict) and data.get("_error", {}).get("status") in (401, 403):
            result["_stopped"] = "api/sources/lines недоступен для текущего токена"
            break
    return result


def collect_hotspot_details(
    client: SonarClient,
    hotspots: list[dict[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for hotspot in hotspots:
        key = hotspot.get("key")
        if key:
            data = client.get("api/hotspots/show", {"hotspot": key}, optional=True)
            result[key] = data
            # Подробности hotspot могут быть закрыты даже при доступном списке.
            if isinstance(data, dict) and data.get("_error", {}).get("status") in (401, 403):
                result["_stopped"] = "api/hotspots/show недоступен для текущего токена"
                break
    return result


def collect_profile_rules(client: SonarClient, profiles: dict[str, Any], language: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    profile_items = profiles.get("profiles", []) if isinstance(profiles, dict) else []
    for profile in profile_items:
        if language and profile.get("language") != language:
            continue
        key = profile.get("key")
        if not key:
            continue
        result[key] = client.paged(
            "api/rules/search",
            with_language({"qprofile": key, "activation": "true"}, language),
            "rules",
            optional=True,
        )
    return result


ISSUE_FIELDS = {
    "key",
    "rule",
    "severity",
    "component",
    "line",
    "status",
    "message",
    "effort",
    "tags",
    "creationDate",
    "updateDate",
    "type",
    "impacts",
    "issueStatus",
    "resolution",
    "closeDate",
    "flows",
}

RULE_FIELDS = {
    "key",
    "name",
    "severity",
    "type",
    "sysTags",
    "tags",
    "params",
    "htmlDesc",
    "descriptionSections",
    "cleanCodeAttribute",
    "cleanCodeAttributeCategory",
    "impacts",
    "actives",
}

SOURCE_LINE_FIELDS = {"line", "code", "duplicated", "lineHits"}
CLOSED_ISSUE_STATUSES = {"CLOSED", "RESOLVED"}
CLOSED_ISSUE_RESOLUTIONS = {"FIXED", "FALSE_POSITIVE", "WONTFIX", "WONT_FIX", "REMOVED"}

CORE_FILE_METRICS = {
    "ncloc",
    "lines",
    "functions",
    "statements",
    "complexity",
    "cognitive_complexity",
    "coverage",
    "line_coverage",
    "lines_to_cover",
    "uncovered_lines",
    "duplicated_blocks",
    "duplicated_lines",
    "duplicated_lines_density",
    "open_issues",
    "bugs",
    "code_smells",
    "security_hotspots",
    "security_hotspots_reviewed",
    "security_hotspots_to_review_status",
    "info_violations",
    "minor_violations",
    "major_violations",
    "critical_violations",
    "blocker_violations",
    "reliability_rating",
    "security_rating",
    "security_review_rating",
    "software_quality_maintainability_rating",
    "software_quality_reliability_rating",
    "software_quality_security_rating",
    "software_quality_maintainability_issues",
    "software_quality_reliability_issues",
    "software_quality_security_issues",
    "software_quality_info_issues",
    "software_quality_low_issues",
    "software_quality_medium_issues",
    "software_quality_high_issues",
    "software_quality_maintainability_debt_ratio",
    "software_quality_maintainability_remediation_effort",
    "software_quality_reliability_remediation_effort",
    "software_quality_security_remediation_effort",
}

NOISY_PROJECT_METRICS = {
    "analysis_from_sonarqube_9_4",
    "quality_profiles",
}

RULE_KEY_PREFIX = "bsl-language-server:"


def is_noisy_metric(metric_key: str | None) -> bool:
    if not metric_key:
        return True
    return (
        metric_key in NOISY_PROJECT_METRICS
        or metric_key.startswith("software_quality_")
        or metric_key.startswith("new_software_quality_")
    )


def keep_keys(value: dict[str, Any], keys: set[str]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key in keys and item not in (None, "", [], {})}


def strip_rule_key_prefix(value: Any) -> Any:
    if isinstance(value, str):
        return value.removeprefix(RULE_KEY_PREFIX)
    return value


def normalize_issue_state(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_")


def is_closed_issue(issue: dict[str, Any]) -> bool:
    status_values = {
        normalize_issue_state(issue.get("status")),
        normalize_issue_state(issue.get("issueStatus")),
    }
    resolution = normalize_issue_state(issue.get("resolution"))
    return bool(
        status_values & (CLOSED_ISSUE_STATUSES | CLOSED_ISSUE_RESOLUTIONS)
        or resolution in CLOSED_ISSUE_RESOLUTIONS
    )


def filter_open_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [issue for issue in issues if not is_closed_issue(issue)]


def compact_issue(issue: dict[str, Any]) -> dict[str, Any]:
    result = keep_keys(issue, ISSUE_FIELDS)
    if "rule" in result:
        result["rule"] = strip_rule_key_prefix(result["rule"])
    flows = []
    for flow in issue.get("flows") or []:
        locations = []
        for location in flow.get("locations") or []:
            text_range = location.get("textRange") or {}
            compact_location = keep_keys(location, {"component", "msg"})
            if text_range.get("startLine"):
                compact_location["line"] = text_range["startLine"]
            if compact_location:
                locations.append(compact_location)
        if locations:
            flows.append({"locations": locations})
    if flows:
        result["flows"] = flows
    elif "flows" in result:
        result.pop("flows", None)
    return result


def compact_rule(rule: dict[str, Any]) -> dict[str, Any]:
    result = keep_keys(rule, RULE_FIELDS)
    if "key" in result:
        result["key"] = strip_rule_key_prefix(result["key"])
    if "actives" in result:
        result["actives"] = [
            keep_keys(active, {"qProfile", "severity", "inheritance", "params"})
            for active in result.get("actives") or []
        ]
    return result


def compact_hotspot(hotspot: dict[str, Any]) -> dict[str, Any]:
    result = dict(hotspot)
    if "ruleKey" in result:
        result["ruleKey"] = strip_rule_key_prefix(result["ruleKey"])
    return result


def compact_hotspot_rule(rule: dict[str, Any]) -> dict[str, Any]:
    result = keep_keys(rule, {"key", "name", "securityCategory", "vulnerabilityProbability"})
    if "key" in result:
        result["key"] = strip_rule_key_prefix(result["key"])
    return result


def keep_file_metric(metric_key: str | None) -> bool:
    return bool(metric_key and not is_noisy_metric(metric_key) and (metric_key in CORE_FILE_METRICS or metric_key.startswith("new_")))


def compact_file_measure(component: dict[str, Any]) -> dict[str, Any]:
    measures = [measure for measure in component.get("measures", []) if keep_file_metric(measure.get("metric"))]
    result = keep_keys(component, {"path", "name"})
    result["measures"] = measures
    return result


def compact_report(report: dict[str, Any]) -> None:
    raw = report.get("raw", {})

    component = raw.get("project", {}).get("component")
    if isinstance(component, dict):
        component.pop("analysisDate", None)
        component.pop("visibility", None)
        component.pop("qualifier", None)
        component.pop("needIssueSync", None)
        component.pop("isAiCodeFixEnabled", None)

    if isinstance(raw.get("branches"), dict):
        for branch in raw["branches"].get("branches", []):
            if isinstance(branch, dict):
                branch.pop("analysisDate", None)

    quality_gate_status = raw.get("quality_gate", {}).get("projectStatus")
    if isinstance(quality_gate_status, dict):
        quality_gate_status.pop("caycStatus", None)

    quality_gate_period = raw.get("quality_gate", {}).get("projectStatus", {}).get("period")
    if isinstance(quality_gate_period, dict):
        quality_gate_period.pop("mode", None)

    if isinstance(raw.get("issues"), dict):
        raw["issues"].pop("first", None)
        raw["issues"]["items"] = [compact_issue(issue) for issue in filter_open_issues(raw["issues"].get("items", []))]

    if isinstance(raw.get("new_issues"), dict):
        raw["new_issues"].pop("first", None)
        raw["new_issues"]["items"] = [
            compact_issue(issue)
            for issue in filter_open_issues(raw["new_issues"].get("items", []))
        ]

    if isinstance(raw.get("source_files"), dict):
        for component, source in list(raw["source_files"].items()):
            if not isinstance(source, dict) or component.startswith("_"):
                continue
            source["sources"] = [
                keep_keys(line, SOURCE_LINE_FIELDS)
                for line in source.get("sources", [])
            ]

    if isinstance(raw.get("file_measures"), dict):
        raw["file_measures"].pop("first", None)
        raw["file_measures"]["items"] = [
            compact_file_measure(component)
            for component in raw["file_measures"].get("items", [])
        ]

    if isinstance(raw.get("project_measures"), dict):
        raw["project_measures"].pop("first", None)
        raw["project_measures"]["measures"] = [
            measure
            for measure in raw["project_measures"].get("measures", [])
            if isinstance(measure, dict) and not is_noisy_metric(measure.get("metric"))
        ]

    if isinstance(raw.get("rules"), dict):
        raw["rules"] = {
            strip_rule_key_prefix(key): {"rule": compact_rule(value.get("rule", value))}
            for key, value in raw["rules"].items()
            if isinstance(value, dict)
        }

    if isinstance(raw.get("profile_rules"), dict):
        for section in raw["profile_rules"].values():
            if isinstance(section, dict):
                section.pop("first", None)
                section["items"] = [compact_rule(rule) for rule in section.get("items", [])]

    if isinstance(raw.get("hotspots"), dict):
        for section in raw["hotspots"].values():
            if isinstance(section, dict):
                section.pop("first", None)
                section["items"] = [
                    compact_hotspot(hotspot)
                    for hotspot in section.get("items", [])
                    if isinstance(hotspot, dict)
                ]

    if isinstance(raw.get("hotspot_details"), dict):
        raw["hotspot_details"] = {
            key: {"rule": compact_hotspot_rule(detail.get("rule", {}))}
            for key, detail in raw["hotspot_details"].items()
            if isinstance(detail, dict) and not key.startswith("_")
        }

    raw.pop("quality_profiles", None)

    used_metric_keys = {
        measure.get("metric")
        for measure in raw.get("project_measures", {}).get("measures", [])
        if isinstance(measure, dict)
    }
    for component in raw.get("file_measures", {}).get("items", []):
        used_metric_keys.update(
            measure.get("metric")
            for measure in component.get("measures", [])
            if isinstance(measure, dict)
        )
    if isinstance(raw.get("metrics_catalog"), dict):
        raw["metrics_catalog"]["items"] = [
            keep_keys(metric, {"key", "name", "shortName", "domain", "type"})
            for metric in raw["metrics_catalog"].get("items", [])
            if metric.get("key") in used_metric_keys and not is_noisy_metric(metric.get("key"))
        ]


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    token = args.token or os.environ.get("SONAR_TOKEN")
    if not token:
        raise SonarError("Укажите SonarQube token через --token или переменную SONAR_TOKEN")

    client = SonarClient(
        args.url,
        token=token,
        timeout=args.timeout,
        pause=args.pause,
    )

    report: dict[str, Any] = {
        "meta": {
            "project": args.project,
            "branch": args.branch,
            "language": args.language,
            "url": args.url.rstrip("/"),
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
        "raw": {},
        "collection_errors": [],
    }

    project_result = safe_collect(report, "project", lambda: client.get("api/components/show", {"component": args.project}, optional=True))
    current_version = None
    if isinstance(project_result, dict):
        component = project_result.get("component")
        if isinstance(component, dict):
            current_version = component.get("version")
    quality_gate_result = safe_collect(report, "quality_gate", lambda: client.get("api/qualitygates/project_status", with_branch({"projectKey": args.project}, args.branch), optional=True))
    baseline_version = None
    if isinstance(quality_gate_result, dict):
        period = quality_gate_result.get("projectStatus", {}).get("period")
        if isinstance(period, dict):
            baseline_version = period.get("parameter")
    safe_collect(
        report,
        "current_version_analysis",
        lambda: collect_current_version_analysis(client, args.project, args.branch, current_version, baseline_version),
    )
    safe_collect(report, "branches", lambda: client.get("api/project_branches/list", {"project": args.project}, optional=True))
    quality_profiles = safe_collect(
        report,
        "quality_profiles",
        lambda: client.get(
            "api/qualityprofiles/search",
            with_language({"project": args.project}, args.language, "language"),
            optional=True,
        ),
    )

    metrics_catalog = safe_collect(report, "metrics_catalog", lambda: client.paged("api/metrics/search", {}, "metrics", optional=True))
    catalog_items = metrics_catalog.get("items", []) if isinstance(metrics_catalog, dict) else []
    all_metric_keys = sorted({m.get("key") for m in catalog_items if m.get("key")})
    metric_types = {m.get("key"): m.get("type") for m in catalog_items if m.get("key")}

    safe_collect(report, "project_measures", lambda: collect_measures(client, args.project, all_metric_keys, args.branch, metric_types))
    file_measures_result = safe_collect(
        report,
        "file_measures",
        lambda: collect_component_tree_measures(
            client,
            args.project,
            all_metric_keys,
            args.branch,
            args.language,
            metric_types,
        ),
    )

    issues_result = safe_collect(report, "issues", lambda: collect_issues(client, args.project, args.branch, args.language))
    if isinstance(issues_result, dict):
        original_issues = issues_result.get("items", [])
        issues = filter_open_issues(original_issues)
        issues_result["items"] = issues
        issues_result["filtered_total"] = len(issues)
        issues_result["excluded_closed_total"] = len(original_issues) - len(issues)
    else:
        issues = []
    new_issues_result = safe_collect(
        report,
        "new_issues",
        lambda: collect_issues(client, args.project, args.branch, args.language, in_new_code_period=True),
    )
    if isinstance(new_issues_result, dict):
        original_new_issues = new_issues_result.get("items", [])
        new_issues = filter_open_issues(original_new_issues)
        new_issues_result["items"] = new_issues
        new_issues_result["filtered_total"] = len(new_issues)
        new_issues_result["excluded_closed_total"] = len(original_new_issues) - len(new_issues)
    safe_collect(report, "rules", lambda: collect_rules(client, issues))
    safe_collect(report, "profile_rules", lambda: collect_profile_rules(client, quality_profiles or {}, args.language))

    file_measure_items = file_measures_result.get("items", []) if isinstance(file_measures_result, dict) else []
    file_measures_complete = (
        isinstance(file_measures_result, dict)
        and not file_measures_result.get("error")
        and not file_measures_result.get("errors")
        and bool(file_measure_items)
    )
    # Фильтруем hotspots по файлам только когда дерево компонентов получено полностью.
    allowed_components = (
        {component.get("key") for component in file_measure_items if component.get("key")}
        if file_measures_complete
        else None
    )

    hotspots_result = safe_collect(
        report,
        "hotspots",
        lambda: collect_hotspots(client, args.project, args.branch, allowed_components),
    )
    all_hotspots = []
    if isinstance(hotspots_result, dict):
        all_hotspots = hotspots_result.get("all", {}).get("items", []) or hotspots_result.get("open", {}).get("items", [])
    safe_collect(report, "hotspot_details", lambda: collect_hotspot_details(client, all_hotspots))
    safe_collect(report, "source_files", lambda: collect_source_files(client, args.branch, issues, all_hotspots))

    compact_report(report)
    report["api_errors"] = client.errors
    return report


def print_collection_errors(report: dict[str, Any]) -> None:
    errors = list(report.get("collection_errors", [])) + list(report.get("api_errors", []))
    if not errors:
        print("Ошибок API/сбора: 0")
        return

    print(f"Ошибок API/сбора: {len(errors)}")
    for error in errors:
        section = error.get("section") or error.get("path") or "unknown"
        status = error.get("status") or error.get("error") or ""
        reason = error.get("reason") or ""
        body = (error.get("body") or "").replace("\n", " ")[:300]
        print(f"- {section} {status} {reason} {body}".strip())


def has_report_errors(report: dict[str, Any]) -> bool:
    return bool(report.get("collection_errors") or report.get("api_errors"))


def write_site(report: dict[str, Any], out_dir: pathlib.Path) -> None:
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    data_js = "window.__SONAR_REPORT__ = "
    data_js += json.dumps(report, ensure_ascii=False, separators=(",", ":"))
    data_js += ";\n"
    data_path = assets_dir / "report-data.js"
    temp_data_path = assets_dir / "report-data.js.tmp"
    temp_data_path.write_text(data_js, encoding="utf-8")
    temp_data_path.replace(data_path)
    shutil.copyfile(TEMPLATE_DIR / "assets" / "app.js", assets_dir / "app.js")
    shutil.copyfile(TEMPLATE_DIR / "assets" / "styles.css", assets_dir / "styles.css")
    i18n_dir = TEMPLATE_DIR / "assets" / "i18n"
    if i18n_dir.exists():
        shutil.copytree(i18n_dir, assets_dir / "i18n", dirs_exist_ok=True)
    shutil.copyfile(TEMPLATE_DIR / "index.html", out_dir / "index.html")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Собирает подробный SonarQube отчет и генерирует статический сайт.",
    )
    parser.add_argument("--url", default=DEFAULT_URL, help=f"URL SonarQube, по умолчанию {DEFAULT_URL}")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help=f"Ключ проекта, по умолчанию {DEFAULT_PROJECT}")
    parser.add_argument("--branch", default=None, help="Имя ветки SonarQube, если нужен не main branch")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help=f"Язык для отбора данных, по умолчанию {DEFAULT_LANGUAGE}")
    parser.add_argument("--out", default="sonar-static-report", help="Папка для готового сайта")
    parser.add_argument("--token", default=None, help="Sonar token. Также поддерживается переменная SONAR_TOKEN")
    parser.add_argument("--timeout", type=int, default=30, help="Таймаут HTTP-запроса в секундах")
    parser.add_argument("--pause", type=float, default=0.0, help="Пауза между API-запросами")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Вернуть код 0 даже при частичных ошибках API/сбора",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    out_dir = pathlib.Path(args.out).resolve()
    try:
        report = build_report(args)
    except SonarError as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    write_site(report, out_dir)

    index_path = out_dir / "index.html"
    print(f"Готово: {index_path}")
    print_collection_errors(report)
    if has_report_errors(report) and not args.allow_partial:
        print("Отчет сформирован частично. Для кода 0 используйте --allow-partial.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
