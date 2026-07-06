#!/usr/bin/env python3
import argparse
import base64
import datetime as dt
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


METRICS = {
    "coverage": "Покрытие",
    "lines_to_cover": "Строк к покрытию",
    "uncovered_lines": "Непокрытые строки",
    "duplicated_lines_density": "Доля дублирования строк",
    "bugs": "Ошибки",
    "vulnerabilities": "Уязвимости",
    "code_smells": "Замечания к коду",
    "security_hotspots": "Потенциальные проблемы безопасности",
}


QUALITY_GATE_STATUSES = {
    "OK": "Пройден",
    "WARN": "Предупреждение",
    "ERROR": "Не пройден",
    "NONE": "Нет данных",
    "n/a": "н/д",
}


def parse_report_task(path):
    values = {}
    if not path.is_file():
        return values

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    return values


def api_get(host_url, token, path, query=None):
    url = host_url.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode(query, doseq=True)

    request = urllib.request.Request(url)
    if token:
        credentials = base64.b64encode(f"{token}:".encode("utf-8")).decode("ascii")
        request.add_header("Authorization", f"Basic {credentials}")

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_analysis(host_url, token, task_id, timeout_seconds, poll_interval):
    if not task_id:
        return None, "SonarQube CE task id is empty"

    deadline = time.monotonic() + timeout_seconds
    last_status = ""

    while time.monotonic() < deadline:
        data = api_get(host_url, token, "/api/ce/task", {"id": task_id})
        task = data.get("task", {})
        last_status = task.get("status", "")

        if last_status == "SUCCESS":
            return task.get("analysisId"), ""
        if last_status in {"FAILED", "CANCELED"}:
            return task.get("analysisId"), f"SonarQube CE task finished with status {last_status}"

        time.sleep(poll_interval)

    return None, f"Timed out waiting for SonarQube CE task. Last status: {last_status or 'unknown'}"


def get_quality_gate(host_url, token, project_key, analysis_id):
    query = {"analysisId": analysis_id} if analysis_id else {"projectKey": project_key}
    return api_get(host_url, token, "/api/qualitygates/project_status", query).get("projectStatus", {})


def get_measures(host_url, token, project_key):
    data = api_get(
        host_url,
        token,
        "/api/measures/component",
        {
            "component": project_key,
            "metricKeys": ",".join(METRICS),
        },
    )
    measures = data.get("component", {}).get("measures", [])
    return {item.get("metric"): item.get("value", "") for item in measures}


def get_issues(host_url, token, project_key):
    data = api_get(
        host_url,
        token,
        "/api/issues/search",
        {
            "componentKeys": project_key,
            "severities": "BLOCKER,CRITICAL",
            "resolved": "false",
            "ps": "100",
        },
    )
    return data.get("issues", []), int(data.get("total", 0))


def markdown_escape(value):
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def metric_value(measures, metric):
    value = measures.get(metric, "")
    if value == "":
        return "н/д"
    if metric in {"coverage", "duplicated_lines_density"}:
        return f"{value}%"
    return value


def quality_gate_status(value):
    return QUALITY_GATE_STATUSES.get(value, value or "н/д")


def russian_message(message):
    if not message:
        return ""

    exact_messages = {
        "SONAR_HOST_URL is not configured": "SONAR_HOST_URL не настроен",
        "Unit or UI coverage XML is missing": "Отсутствует XML-файл покрытия unit или UI",
        "SonarQube CE task id is empty": "Идентификатор задачи SonarQube CE пустой",
        "SONAR_HOST_URL is empty": "SONAR_HOST_URL пустой",
    }
    if message in exact_messages:
        return exact_messages[message]

    prefix_messages = {
        "sonar-scanner exited with code ": "sonar-scanner завершился с кодом ",
        "SonarQube CE task finished with status ": "Задача SonarQube CE завершилась со статусом ",
        "Timed out waiting for SonarQube CE task. Last status: ": "Истекло время ожидания задачи SonarQube CE. Последний статус: ",
        "Failed to read SonarQube API: ": "Не удалось прочитать SonarQube API: ",
    }
    for prefix, translated_prefix in prefix_messages.items():
        if message.startswith(prefix):
            return translated_prefix + message[len(prefix):]

    return message


def dashboard_url(host_url, project_key, report_task):
    from_task = report_task.get("dashboardUrl", "")
    if from_task:
        return from_task
    if not host_url or not project_key:
        return ""
    host = urllib.parse.urlparse(host_url).hostname or ""
    if os.environ.get("CI") == "true" and host in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}:
        return ""
    return f"{host_url.rstrip('/')}/dashboard?id={urllib.parse.quote(project_key)}"


def copy_coverage(source, target):
    if source and source.is_file():
        shutil.copyfile(source, target)
        return True
    return False


def write_summary(args, report_task, analysis_id, warning, quality_gate, measures, issues, total_issues):
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    unit_copied = copy_coverage(args.unit_coverage, output_dir / "coverage-unit.xml")
    ui_copied = copy_coverage(args.ui_coverage, output_dir / "coverage-ui.xml")

    project_dashboard_url = dashboard_url(args.host_url, args.project_key, report_task)
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    gate_status = quality_gate.get("status", "н/д")

    lines = [
        "# Отчёт SonarQube",
        "",
        "| Поле | Значение |",
        "| --- | --- |",
        f"| Проект | {markdown_escape(args.project_name)} |",
        f"| Версия | {markdown_escape(args.project_version or 'н/д')} |",
        f"| Коммит | {markdown_escape(args.commit_sha or 'н/д')} |",
        f"| Запуск GitHub | {markdown_escape(args.run_id or 'н/д')} / {markdown_escape(args.run_attempt or 'н/д')} |",
        f"| Дата анализа | {markdown_escape(generated_at)} |",
        f"| Quality Gate | {markdown_escape(quality_gate_status(gate_status))} |",
    ]

    if project_dashboard_url:
        lines.append(f"| Проект SonarQube | [Дашборд]({project_dashboard_url}) |")
    else:
        lines.append("| Проект SonarQube | н/д |")

    if args.skip_reason:
        lines.append(f"| Статус сканера | Пропущено: {markdown_escape(russian_message(args.skip_reason))} |")
    elif warning:
        lines.append(f"| Статус сканера | Предупреждение: {markdown_escape(russian_message(warning))} |")
    else:
        lines.append("| Статус сканера | Завершено |")

    lines.extend(["", "## Метрики", "", "| Метрика | Значение |", "| --- | --- |"])
    for metric, label in METRICS.items():
        lines.append(f"| {label} | {markdown_escape(metric_value(measures, metric))} |")

    lines.extend(
        [
            "",
            "## Покрытие",
            "",
            f"- Источник покрытия unit-тестов: {'coverage-unit.xml' if unit_copied else 'не найден'}",
            f"- Источник покрытия UI-тестов: {'coverage-ui.xml' if ui_copied else 'не найден'}",
            f"- Общее покрытие SonarQube: {markdown_escape(metric_value(measures, 'coverage'))}",
        ]
    )

    lines.extend(["", "## Условия Quality Gate", ""])
    conditions = quality_gate.get("conditions", [])
    if conditions:
        lines.extend(["| Метрика | Статус | Фактическое значение | Порог |", "| --- | --- | --- | --- |"])
        for condition in conditions:
            threshold = condition.get("errorThreshold") or condition.get("warningThreshold") or "н/д"
            lines.append(
                "| "
                + " | ".join(
                    markdown_escape(value)
                    for value in (
                        METRICS.get(condition.get("metricKey", ""), condition.get("metricKey", "н/д")),
                        quality_gate_status(condition.get("status", "н/д")),
                        condition.get("actualValue", "н/д"),
                        threshold,
                    )
                )
                + " |"
            )
    else:
        lines.append("SonarQube не вернул условия Quality Gate.")

    lines.extend(["", "## Критичные и блокирующие замечания", ""])
    if issues:
        lines.extend(["| Важность | Тип | Компонент | Строка | Сообщение |", "| --- | --- | --- | --- | --- |"])
        for issue in issues[:20]:
            lines.append(
                "| "
                + " | ".join(
                    markdown_escape(value)
                    for value in (
                        issue.get("severity", "н/д"),
                        issue.get("type", "н/д"),
                        issue.get("component", "н/д"),
                        issue.get("line", "н/д"),
                        issue.get("message", "н/д"),
                    )
                )
                + " |"
            )
        if total_issues > len(issues[:20]):
            lines.append("")
            lines.append(f"Показаны первые 20 из {total_issues} замечаний.")
    else:
        lines.append("SonarQube не вернул незакрытые критичные или блокирующие замечания.")

    if project_dashboard_url:
        lines.extend(["", f"[Полный дашборд SonarQube]({project_dashboard_url})"])

    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--project-key", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--project-version", default="")
    parser.add_argument("--commit-sha", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-attempt", default="")
    parser.add_argument("--host-url", default="")
    parser.add_argument("--token", default="")
    parser.add_argument("--report-task-file", default=".scannerwork/report-task.txt", type=Path)
    parser.add_argument("--unit-coverage", required=True, type=Path)
    parser.add_argument("--ui-coverage", required=True, type=Path)
    parser.add_argument("--skip-reason", default="")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--poll-interval", type=int, default=5)
    args = parser.parse_args()

    report_task = parse_report_task(args.report_task_file)
    warning = ""
    analysis_id = None
    quality_gate = {}
    measures = {}
    issues = []
    total_issues = 0

    if args.skip_reason:
        warning = args.skip_reason
    elif not args.host_url:
        warning = "SONAR_HOST_URL is empty"
    else:
        try:
            analysis_id, warning = wait_for_analysis(
                args.host_url,
                args.token,
                report_task.get("ceTaskId", ""),
                args.timeout_seconds,
                args.poll_interval,
            )
            quality_gate = get_quality_gate(args.host_url, args.token, args.project_key, analysis_id)
            measures = get_measures(args.host_url, args.token, args.project_key)
            issues, total_issues = get_issues(args.host_url, args.token, args.project_key)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as error:
            warning = f"Failed to read SonarQube API: {error}"

    write_summary(args, report_task, analysis_id, warning, quality_gate, measures, issues, total_issues)
    print(args.output_dir / "summary.md")


if __name__ == "__main__":
    sys.exit(main())
