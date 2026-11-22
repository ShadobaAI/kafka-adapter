import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from list_ui_groups import feature_groups
from prepare_allure_results import UI_SCOPE, UNIT_SCOPE, prepare_results_dir


class ReleaseQualityTests(unittest.TestCase):
    def test_group_uses_first_two_directories_including_nested_features(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = root / "Раздел/Данные"
            fixtures.mkdir(parents=True)
            (fixtures / "README.md").touch()
            with self.assertRaisesRegex(ValueError, "No UI feature groups"):
                feature_groups(root)
            for name in ("Раздел/Объект/первый", "Раздел/Объект/Вложенный/второй", "Другой/Объект/третий"):
                path = root / (name + ".feature")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            (root / "Раздел/Новый").mkdir()
            self.assertEqual(feature_groups(root), ["Другой/Объект", "Раздел/Объект"])
            (root / "Раздел/без объекта.feature").touch()
            with self.assertRaises(ValueError):
                feature_groups(root)

    def test_partial_ui_results_keep_attachments_from_each_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "results"
            groups = [root / f"test-results-1-ui-{i}" for i in range(2)]
            for group in groups:
                raw = group / "allure"
                raw.mkdir(parents=True)
                (raw / "screen.png").write_bytes(group.name.encode())
                attachment = {"name": "screen", "source": "screen.png", "type": "image/png"}
                step = {"name": "open", "attachments": [attachment]}
                (raw / "same-result.json").write_text(json.dumps({"uuid": group.name, "steps": [step]}))
                (raw / "same-container.json").write_text(json.dumps({"befores": [{"steps": [step]}]}))
            raw = groups[0] / "allure"
            for index, record in enumerate(("{", '{"attachments":[{}]}', '{"steps":[null]}')):
                (raw / f"broken-{index}-result.json").write_text(record)

            errors = io.StringIO()
            with redirect_stderr(errors):
                valid = prepare_results_dir(results, root / "unit", groups, (UI_SCOPE,), True, {})
            self.assertFalse(valid)
            self.assertEqual(errors.getvalue().count("invalid Allure record"), 3)
            self.assertEqual(len(list(results.rglob("*-result.json"))), 2)
            sources = set()
            for group in groups:
                staged = results / group.name
                test = json.loads((staged / "same-result.json").read_text(encoding="utf-8"))
                fixture = json.loads((staged / "same-container.json").read_text(encoding="utf-8"))
                source = test["steps"][0]["attachments"][0]["source"]
                self.assertEqual(fixture["befores"][0]["steps"][0]["attachments"][0]["source"], source)
                self.assertEqual((staged / source).read_bytes(), group.name.encode())
                self.assertTrue((group / "allure/screen.png").is_file())
                sources.add(source)
            self.assertEqual(len(sources), 2)

    def test_nested_results_use_attachments_from_their_own_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            group = root / "test-results-2-ui-0"
            raw = group / "allure"
            paths = ("", "nested/deeper")
            for index, subdir in enumerate(paths):
                source = raw / subdir
                source.mkdir(parents=True)
                (source / "screen.png").write_bytes(bytes([index]))
                (source / "case-result.json").write_text(json.dumps({
                    "uuid": str(index), "attachments": [{"source": "screen.png"}],
                }), encoding="utf-8")
            results = root / "results"
            self.assertTrue(prepare_results_dir(results, root / "unit", [group], (UI_SCOPE,), True, {}, ["A/B"]))
            staged = results / group.name
            for index, subdir in enumerate(paths):
                data = json.loads((staged / subdir / "case-result.json").read_text(encoding="utf-8"))
                self.assertEqual((staged / data["attachments"][0]["source"]).read_bytes(), bytes([index]))

    def test_suite_tree_uses_matrix_index_when_some_workers_are_missing(self):
        matrix = ["РегистрыСведений/Объект", "Раздел/Пропущен", "Справочники/Объект"]
        original = [
            {"name": "package", "value": "ВложенныйКаталог"},
            {"name": "suite", "value": "Сценарии"},
            {"name": "suite", "value": "Другая метка"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            groups = [root / f"test-results-3-ui-{index}" for index in (2, 0)]
            for group in groups:
                raw = group / "allure"
                raw.mkdir(parents=True)
                (raw / "test-result.json").write_text(json.dumps({"labels": original}), encoding="utf-8")
            unit = root / "unit"
            (unit / "allure").mkdir(parents=True)
            unit_labels = [{"name": "parentSuite", "value": "Unit-тесты"}, {"name": "suite", "value": "Модуль"}]
            (unit / "allure/unit-result.json").write_text(json.dumps({"labels": unit_labels}), encoding="utf-8")

            results = root / "results"
            run_url = "https://github.com/example/adapter/actions/runs/123"
            with patch.dict("os.environ", REPORT_RUN_URL=run_url), redirect_stderr(io.StringIO()):
                self.assertFalse(prepare_results_dir(results, unit, groups, (UNIT_SCOPE, UI_SCOPE), True, {}, matrix))
            reports = [json.loads(p.read_text(encoding="utf-8")) for p in results.rglob("*-result.json")]
            self.assertEqual(len(reports), 4)
            missing, = [report for report in reports if report.get("status") == "broken"]
            self.assertIn(matrix[1], missing["name"])
            self.assertEqual(missing["links"][0]["url"], run_url)
            self.assertIn({"name": "subSuite", "value": "Пропущен"}, missing["labels"])
            unit_result = json.loads((results / "unit-result.json").read_text(encoding="utf-8"))
            suite_names = {"parentSuite", "suite", "subSuite"}
            self.assertEqual([label for label in unit_result["labels"] if label["name"] in suite_names], unit_labels)
            for group, section in zip(groups, ("Справочники", "РегистрыСведений")):
                labels = json.loads((results / group.name / "test-result.json").read_text(encoding="utf-8"))["labels"]
                self.assertCountEqual([label for label in labels if label["name"] in suite_names], [
                    {"name": "parentSuite", "value": "UI-тесты"},
                    {"name": "suite", "value": section},
                    {"name": "subSuite", "value": "Объект"},
                ])
                self.assertIn(original[0], labels)

    def test_crashed_group_links_to_the_job_even_if_all_results_are_unreadable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            group = root / "test-results-3-ui-0"
            raw = group / "allure"
            raw.mkdir(parents=True)
            (raw / "bad-result.json").write_text("{", encoding="utf-8")
            (group / "check-run-id").write_text("456\n", encoding="utf-8")
            results = root / "results"
            run_url = "https://github.com/example/adapter/actions/runs/123"
            with patch.dict("os.environ", REPORT_RUN_URL=run_url), redirect_stderr(io.StringIO()):
                self.assertFalse(prepare_results_dir(results, root / "unit", [group], (UI_SCOPE,), True, {}, ["A/B"]))
            record, = results.rglob("*-result.json")
            missing = json.loads(record.read_text(encoding="utf-8"))
            self.assertEqual(missing["status"], "broken")
            self.assertEqual(missing["links"][0]["url"], run_url + "/job/456")
            self.assertTrue((raw / "bad-result.json").is_file())


if __name__ == "__main__":
    unittest.main()
