import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch
from zipfile import BadZipFile

import create_test_cf
import create_test_dt


class CreateTestDtTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        workdir = Path(self.directory.name)
        self.options = create_test_dt.Options(
            workdir=workdir,
            ib_path=workdir / "ib",
            base_archive=workdir / "base.zip",
            adapter_archive=workdir / "adapter.zip",
            examples_archive=workdir / "examples.zip",
            yaxunit=None,
            va_extension=None,
            template_dt=workdir / "template.dt",
        )
        self.options.ib_path.mkdir()
        self.existing_file = self.options.ib_path / "existing.txt"
        self.existing_file.write_text("existing database", encoding="utf-8")

    def test_builder_arguments_match_parser_and_examples_load_separately(self):
        commands = []

        def capture(command, **kwargs):
            commands.append(command)
            return Mock(returncode=0)

        with (
            patch.object(create_test_dt, "validate_options"),
            patch.object(create_test_dt, "extract_zip") as extract,
            patch.object(create_test_dt, "require_file"),
            patch.object(create_test_dt.subprocess, "run", side_effect=capture),
        ):
            create_test_dt.run(self.options)

        builder_options = create_test_cf.build_parser().parse_args(commands[0][2:])
        self.assertEqual(builder_options.base_archive, self.options.base_archive)
        self.assertEqual(builder_options.adapter_archive, self.options.adapter_archive)
        self.assertEqual(builder_options.output_dir, create_test_dt.config_xml_dir(self.options))
        self.assertEqual(commands[2][:3], ["vrunner", "cf", "load"])
        self.assertEqual(commands[3][:5], [
            "vrunner", "cfe", "load", "--extension-name", "ТестированиеАдаптераKafka",
        ])
        examples_xml = Path(commands[3][-1])
        extract.assert_called_once_with(self.options.examples_archive, examples_xml)
        self.assertFalse(examples_xml.exists())
        self.assertFalse(self.existing_file.exists())

    def test_builder_failure_preserves_existing_infobase(self):
        with (
            patch.object(create_test_dt, "validate_options"),
            patch.object(create_test_dt.subprocess, "run", return_value=Mock(returncode=2)) as runner,
            patch.object(create_test_dt, "extract_zip") as extract,
        ):
            with self.assertRaises(create_test_dt.ScriptError):
                create_test_dt.run(self.options)

        self.assertEqual(self.existing_file.read_text(encoding="utf-8"), "existing database")
        self.assertEqual(runner.call_count, 1)
        extract.assert_not_called()

    def test_invalid_examples_archive_preserves_existing_infobase(self):
        with (
            patch.object(create_test_dt, "validate_options"),
            patch.object(create_test_dt.subprocess, "run", return_value=Mock(returncode=0)) as runner,
            patch.object(create_test_dt, "extract_zip", side_effect=BadZipFile("invalid archive")),
        ):
            with self.assertRaises(BadZipFile):
                create_test_dt.run(self.options)

        self.assertEqual(self.existing_file.read_text(encoding="utf-8"), "existing database")
        self.assertEqual(runner.call_count, 1)

    def test_missing_examples_configuration_preserves_existing_infobase(self):
        with (
            patch.object(create_test_dt, "validate_options"),
            patch.object(create_test_dt.subprocess, "run", return_value=Mock(returncode=0)) as runner,
            patch.object(create_test_dt, "extract_zip"),
        ):
            with self.assertRaises(create_test_dt.ScriptError):
                create_test_dt.run(self.options)

        self.assertTrue(self.existing_file.is_file())
        self.assertEqual(runner.call_count, 1)

    def assert_unsafe_options_preserve_infobase(self, options):
        with (
            patch.object(create_test_dt, "require_file"),
            patch.object(create_test_dt, "require_command"),
            patch.object(create_test_dt.subprocess, "run") as runner,
            patch.object(create_test_dt, "remove_tree") as remove,
            patch.object(create_test_dt, "extract_zip") as extract,
        ):
            with self.assertRaises(create_test_dt.ScriptError):
                create_test_dt.run(options)

        runner.assert_not_called()
        remove.assert_not_called()
        extract.assert_not_called()
        self.assertEqual(self.existing_file.read_text(encoding="utf-8"), "existing database")

    def test_rejects_infobase_containing_workdir(self):
        for ib_path in (self.options.workdir, self.options.workdir.parent):
            with self.subTest(ib_path=ib_path):
                self.assert_unsafe_options_preserve_infobase(replace(self.options, ib_path=ib_path))

    def test_rejects_infobase_overlapping_xml_directory(self):
        xml_dir = create_test_dt.config_xml_dir(self.options)
        for ib_path in (xml_dir, xml_dir / "ib"):
            with self.subTest(ib_path=ib_path):
                self.assert_unsafe_options_preserve_infobase(replace(self.options, ib_path=ib_path))

        nested_workdir = self.options.ib_path / "work"
        nested_workdir.mkdir()
        self.assert_unsafe_options_preserve_infobase(replace(self.options, workdir=nested_workdir))

    def test_rejects_inputs_in_destructive_directories(self):
        filenames = {
            "base_archive": "base.zip",
            "adapter_archive": "adapter.zip",
            "examples_archive": "examples.zip",
            "template_dt": "template.dt",
            "va_extension": "VAExtension.cfe",
            "yaxunit": "YAXUNIT.cfe",
        }
        for directory in (self.options.ib_path, create_test_dt.config_xml_dir(self.options)):
            for field, filename in filenames.items():
                with self.subTest(directory=directory, field=field):
                    options = replace(self.options, **{field: directory / filename})
                    self.assert_unsafe_options_preserve_infobase(options)

    def test_rejects_builder_in_destructive_directories(self):
        for directory in (self.options.ib_path, create_test_dt.config_xml_dir(self.options)):
            with self.subTest(directory=directory):
                with patch.object(create_test_dt, "builder_script", return_value=directory / "builder.py"):
                    self.assert_unsafe_options_preserve_infobase(self.options)

    def test_accepts_default_infobase_subdirectory(self):
        with (
            patch.object(create_test_dt, "require_file"),
            patch.object(create_test_dt, "require_command"),
        ):
            create_test_dt.validate_options(self.options)

        self.assertTrue(self.existing_file.is_file())


if __name__ == "__main__":
    unittest.main()
