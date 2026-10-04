import argparse
import contextlib
import io
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, unquote, urlsplit

from sonar_release_project import main as resolve_project, project_key
from sonar_static_report import SonarError, build_report, collect_current_version_analysis, compact_report


class FakeSonar:
    def __init__(self, analyses=None):
        self.analyses = analyses if analyses is not None else [
            {"key": "current", "date": "2026-02-01", "projectVersion": "next"},
            {"key": "base", "date": "2026-01-01", "projectVersion": "stable", "revision": "stable-sha"},
        ]
        self.pages = []

    def get(self, path, params, **kwargs):
        if path == "api/project_analyses/search":
            self.pages.append(params["p"])
            offset = (params["p"] - 1) * 100
            return {"paging": {"total": len(self.analyses)}, "analyses": self.analyses[offset:offset + 100]}
        raise AssertionError(path)


class AnalysisBaselineTests(unittest.TestCase):
    def test_specific_analysis_resolves_uuid_to_version(self):
        result = collect_current_version_analysis(FakeSonar(), "project", None, "next", "base", "SPECIFIC_ANALYSIS")
        self.assertEqual(result["baseline"]["version"], "stable")
        self.assertEqual(result["baseline"]["analysisKey"], "base")

    def test_baseline_after_first_page_is_found(self):
        client = FakeSonar([{"key": str(index), "projectVersion": "next", "date": "2026-02-01"} for index in range(105)]
                           + [{"key": "base", "projectVersion": "stable", "date": "2026-01-01"}])
        result = collect_current_version_analysis(client, "project", None, "next", "base", "SPECIFIC_ANALYSIS")
        self.assertEqual(result["analysisKey"], "0")
        self.assertEqual(result["baseline"]["version"], "stable")
        self.assertEqual(client.pages, [1, 2])

    def test_version_event_without_project_version(self):
        client = FakeSonar([{"key": "base", "date": "2026-01-01", "revision": "stable-sha", "events": [{"category": "VERSION", "name": "stable"}]}])
        result = collect_current_version_analysis(client, "project", None, "stable", "base", "SPECIFIC_ANALYSIS")
        self.assertEqual(result["baseline"]["version"], "stable")

    def test_missing_specific_baseline_fails(self):
        with self.assertRaises(SonarError):
            collect_current_version_analysis(FakeSonar(), "project", None, "next", "missing", "SPECIFIC_ANALYSIS")

    def test_specific_baseline_without_version_fails(self):
        client = FakeSonar([
            {"key": "current", "date": "2026-02-01", "projectVersion": "next"},
            {"key": "base", "date": "2026-01-01"},
        ])
        with self.assertRaises(SonarError):
            collect_current_version_analysis(client, "project", None, "next", "base", "SPECIFIC_ANALYSIS")

    def test_previous_version_baseline_resolves_version(self):
        result = collect_current_version_analysis(FakeSonar(), "project", None, "next", "stable", "PREVIOUS_VERSION")
        self.assertEqual(result["baseline"]["analysisKey"], "base")


class ProjectKeyTests(unittest.TestCase):
    def test_main_keeps_production_project(self):
        self.assertEqual(project_key("kafka-adapter", "main"), "kafka-adapter")

    def test_each_git_branch_has_a_distinct_valid_key(self):
        branches = ["main", "pre", "prerelease", "develop", "feature/report", "feature-report",
                    "feature_report", "feature:2Freport", "feature%2Freport", "feature/Report", "feature/отчёт"]
        keys = [project_key("kafka-adapter", branch) for branch in branches]
        self.assertEqual(len(keys), len(set(keys)))
        for branch, key in zip(branches[1:], keys[1:]):
            with self.subTest(branch=branch):
                self.assertRegex(key, r"^[A-Za-z0-9_.:-]+$")
                self.assertEqual(unquote(key.removeprefix("kafka-adapter:").replace(":", "%")), branch)
        self.assertEqual(project_key("kafka-adapter", "prerelease"), "kafka-adapter:prerelease")
        self.assertEqual(project_key("kafka-adapter", "feature/report"), "kafka-adapter:feature:2Freport")

    def test_empty_repository_or_branch_fails(self):
        for repository, branch in [("", "main"), ("project", "")]:
            with self.subTest(repository=repository, branch=branch), self.assertRaises(ValueError):
                project_key(repository, branch)

    def test_long_branches_use_bounded_stable_keys_in_separate_namespace(self):
        repository = "kafka-adapter"
        limit_branch = "a" * (400 - len(repository) - 1)
        self.assertEqual(len(project_key(repository, limit_branch)), 400)
        branches = [limit_branch + "a", "feature/" + "я" * 64, "feature/" + "Я" * 64]
        keys = [project_key(repository, branch) for branch in branches]
        self.assertEqual(len(set(keys)), len(branches))
        for branch, key in zip(branches, keys):
            with self.subTest(branch=branch):
                self.assertLessEqual(len(key), 400)
                self.assertRegex(key, r"^kafka-adapter::sha256:[0-9a-f]{64}$")
                self.assertEqual(project_key(repository, branch), key)

    def test_environment_and_dashboard_select_same_project_without_sonar_branch(self):
        env = {"SONAR_BASE_PROJECT_KEY": "kafka-adapter", "SONAR_BRANCH_NAME": "feature/a+b's",
               "SONAR_HOST_URL": "https://sonar.example/"}
        output = io.StringIO()
        with patch.dict("os.environ", env, clear=True), contextlib.redirect_stdout(output):
            resolve_project()
        values = dict(line.split("=", 1) for line in output.getvalue().splitlines())
        self.assertEqual(parse_qs(urlsplit(values["SONAR_DASHBOARD_URL"]).query), {"id": [values["SONAR_PROJECT_KEY"]]})
        self.assertEqual(values["SONAR_PROJECT_KEY"], project_key("kafka-adapter", env["SONAR_BRANCH_NAME"]))


class ReportBranchTests(unittest.TestCase):
    def test_previous_version_uses_restored_history_of_selected_project(self):
        project = "kafka-adapter:rc"
        client = Mock()
        client.errors = []
        client.paged.return_value = {"items": []}

        def get(path, params, **kwargs):
            if path == "api/components/show":
                self.assertEqual(params, {"component": project})
                return {"component": {"key": project, "qualifier": "TRK", "version": "3.0.0.1"}}
            if path == "api/qualitygates/project_status":
                self.assertEqual(params, {"projectKey": project})
                return {"projectStatus": {"period": {
                    "mode": "PREVIOUS_VERSION", "parameter": "2.5.1.0", "date": "2026-07-14",
                }}}
            if path == "api/project_branches/list":
                self.assertEqual(params, {"project": project})
                return {"branches": [{"name": "main", "isMain": True}]}
            if path == "api/new_code_periods/show":
                self.assertEqual(params, {"project": project, "branch": "main"})
                return {"type": "PREVIOUS_VERSION", "inherited": True}
            if path == "api/project_analyses/search":
                self.assertEqual(params["project"], project)
                self.assertNotIn("branch", params)
                return {"paging": {"total": 2}, "analyses": [
                    {"key": "rc-analysis", "date": "2026-10-04", "events": [{"category": "VERSION", "name": "3.0.0.1"}]},
                    {"key": "stable-analysis", "date": "2026-07-14", "events": [{"category": "VERSION", "name": "2.5.1.0"}]},
                ]}
            return {}

        client.get.side_effect = get
        args = argparse.Namespace(token="test-token", url="https://sonar.example", timeout=30,
                                  pause=0, project=project, branch=None, language="bsl")
        with patch("sonar_static_report.SonarClient", return_value=client):
            report = build_report(args)
        analysis = report["raw"]["current_version_analysis"]
        self.assertEqual(analysis["version"], "3.0.0.1")
        self.assertEqual(analysis["baseline"]["version"], "2.5.1.0")
        self.assertEqual(analysis["baseline"]["analysisKey"], "stable-analysis")
        self.assertEqual(report["collection_errors"], [])

    def test_compact_report_keeps_period_type_for_version_fallback(self):
        report = {"raw": {"quality_gate": {"projectStatus": {
            "period": {"mode": "previous_version", "parameter": "stable"},
        }}}}
        compact_report(report)
        self.assertEqual(report["raw"]["quality_gate"]["projectStatus"]["period"],
                         {"mode": "previous_version", "parameter": "stable"})

    def test_first_analysis_in_branch_project_needs_no_production_analysis_copy(self):
        project = "project:prerelease"
        client = Mock()
        client.errors = []
        client.paged.return_value = {"items": []}

        def get(path, params, **kwargs):
            if path == "api/components/show":
                self.assertEqual(params, {"component": project})
                return {"component": {"key": project, "qualifier": "TRK", "version": "first-release"}}
            if path == "api/project_branches/list":
                self.assertEqual(params, {"project": project})
                return {"branches": [{"name": "main", "isMain": True}]}
            if path == "api/new_code_periods/show":
                self.assertEqual(params, {"project": project, "branch": "main"})
                return {"type": "PREVIOUS_VERSION", "inherited": True}
            if path == "api/project_analyses/search":
                self.assertEqual(params["project"], project)
                self.assertNotIn("branch", params)
                return {"paging": {"total": 1}, "analyses": [
                    {"key": "first-analysis", "date": "2026-02-01", "projectVersion": "first-release"},
                ]}
            return {}

        client.get.side_effect = get
        args = argparse.Namespace(token="test-token", url="https://sonar.example", timeout=30,
                                  pause=0, project=project, branch=None, language="bsl")
        with patch("sonar_static_report.SonarClient", return_value=client):
            report = build_report(args)
        self.assertEqual(report["raw"]["current_version_analysis"]["version"], "first-release")
        self.assertNotIn("baseline", report["raw"]["current_version_analysis"])
        self.assertEqual(report["collection_errors"], [])

    def test_report_uses_selected_branch_version_and_history(self):
        for branch in ("main", "pre", "develop", "feature/report"):
            with self.subTest(branch=branch):
                client = Mock()
                client.errors = []
                client.paged.return_value = {"items": []}

                def get(path, params, **kwargs):
                    if path == "api/components/show":
                        version = "release" if params.get("branch") == branch else "other-branch-version"
                        return {"component": {"key": "project", "qualifier": "TRK", "version": version}}
                    if path == "api/project_branches/list":
                        return {"branches": [{"name": "main", "isMain": True}]}
                    if path == "api/project_analyses/search":
                        self.assertEqual(params["branch"], branch)
                        return {"paging": {"total": 1}, "analyses": [
                            {"key": "release-analysis", "date": "2026-02-01", "projectVersion": "release"},
                        ]}
                    return {}

                client.get.side_effect = get
                args = argparse.Namespace(token="test-token", url="https://sonar.example", timeout=30,
                                          pause=0, project="project", branch=branch, language="bsl")
                with patch("sonar_static_report.SonarClient", return_value=client):
                    report = build_report(args)
                self.assertEqual(report["meta"]["branch"], branch)
                self.assertEqual(report["raw"]["current_version_analysis"]["version"], "release")
                self.assertEqual(report["raw"]["current_version_analysis"]["analysisKey"], "release-analysis")
                self.assertEqual(report["collection_errors"], [])


if __name__ == "__main__":
    unittest.main()
