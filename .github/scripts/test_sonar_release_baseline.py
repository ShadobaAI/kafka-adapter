import argparse
import unittest
from unittest.mock import Mock, patch

from sonar_release_baseline import latest_stable_tag, verify_baseline
from sonar_static_report import SonarError, build_report, collect_current_version_analysis


class FakeSonar:
    def __init__(self, analyses=None, period=None):
        self.analyses = analyses if analyses is not None else [
            {"key": "current", "date": "2026-02-01", "projectVersion": "next"},
            {"key": "base", "date": "2026-01-01", "projectVersion": "stable", "revision": "stable-sha"},
        ]
        self.period = period if period is not None else {"type": "SPECIFIC_ANALYSIS", "value": "base"}
        self.pages = []

    def get(self, path, params, **kwargs):
        if path == "api/components/show":
            return {"component": {"key": "project", "qualifier": "TRK"}}
        if path == "api/project_branches/list":
            return {"branches": [{"name": "main", "isMain": True}]}
        if path == "api/new_code_periods/show":
            assert params["branch"] == "main"
            return self.period
        if path == "api/project_analyses/search":
            self.pages.append(params["p"])
            offset = (params["p"] - 1) * 100
            return {"paging": {"total": len(self.analyses)}, "analyses": self.analyses[offset:offset + 100]}
        raise AssertionError(path)


class BaselineTests(unittest.TestCase):
    def release(self, tag, date, **flags):
        return {"tag_name": tag, "published_at": date, "draft": False, "prerelease": False, **flags}

    def test_latest_stable_uses_publication_not_version_number(self):
        releases = [self.release("9.0", "2026-01-01T00:00:00Z"), self.release("1.0", "2026-02-01T00:00:00Z")]
        self.assertEqual(latest_stable_tag(releases, "current"), "1.0")

    def test_current_draft_and_prerelease_are_excluded(self):
        releases = [self.release("stable", "2026-01-01T00:00:00Z")]
        releases += [self.release("current", "2026-04-01T00:00:00Z"),
                     self.release("draft", "2026-05-01T00:00:00Z", draft=True),
                     self.release("pre", "2026-06-01T00:00:00Z", prerelease=True)]
        self.assertEqual(latest_stable_tag(releases, "current"), "stable")

    def test_no_stable_and_ambiguous_stable_fail(self):
        for releases in ([], [self.release(tag, "2026-01-01T00:00:00Z") for tag in ("a", "b")]):
            with self.subTest(releases=releases), self.assertRaises(SonarError):
                latest_stable_tag(releases, "current")

    def test_matching_baseline_passes(self):
        verify_baseline(FakeSonar(), "project", "stable", "stable-sha")

    def test_wrong_project_fails(self):
        with self.assertRaises(SonarError):
            verify_baseline(FakeSonar(), "other", "stable", "stable-sha")

    def test_wrong_baseline_version_fails(self):
        with self.assertRaises(SonarError):
            verify_baseline(FakeSonar(), "project", "another-stable", "stable-sha")

    def test_wrong_baseline_revision_fails(self):
        with self.assertRaises(SonarError):
            verify_baseline(FakeSonar(), "project", "stable", "another-sha")

    def test_missing_wrong_type_and_missing_analysis_fail(self):
        for period in ({}, {"type": "PREVIOUS_VERSION"}, {"type": "SPECIFIC_ANALYSIS", "value": "unknown"}):
            with self.subTest(period=period), self.assertRaises(SonarError):
                verify_baseline(FakeSonar(period=period), "project", "stable", "stable-sha")

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
        verify_baseline(client, "project", "stable", "stable-sha")
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

    def test_legacy_version_baseline_still_resolves(self):
        result = collect_current_version_analysis(FakeSonar(), "project", None, "next", "stable")
        self.assertEqual(result["baseline"]["analysisKey"], "base")


class ReportBranchTests(unittest.TestCase):
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
