import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree

from validate_coverage_report import validate_report


class CoverageReportTests(unittest.TestCase):
    def validate(self, xml):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "genericCoverage.xml"
            path.write_text(xml, encoding="utf-8")
            return validate_report(path)

    def test_valid_partial_coverage(self):
        self.assertEqual(self.validate('''<coverage version="1">
            <file path="Модуль/Module.bsl">
                <lineToCover lineNumber="3" covered="true"/>
                <lineToCover lineNumber="4" covered="false"/>
            </file></coverage>'''), (1, 2, 1))

    def test_zero_coverage_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Нет покрытых строк"):
            self.validate('''<coverage version="1"><file path="Module.bsl">
                <lineToCover lineNumber="3" covered="false"/>
            </file></coverage>''')

    def test_empty_report_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "нет строк"):
            self.validate('<coverage version="1"/>')

    def test_invalid_entries_are_rejected_even_with_covered_lines(self):
        for line in (
            '<lineToCover lineNumber="0" covered="true"/>',
            '<lineToCover lineNumber="4" covered="yes"/>',
            '<lineToCover lineNumber="3" covered="false"/>',
        ):
            with self.subTest(line=line), self.assertRaises(ValueError):
                self.validate(f'''<coverage version="1"><file path="Module.bsl">
                    <lineToCover lineNumber="3" covered="true"/>{line}
                </file></coverage>''')

    def test_wrong_format_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Generic Coverage"):
            self.validate('<coverage version="2"/>')

    def test_truncated_xml_is_rejected(self):
        with self.assertRaises(ElementTree.ParseError):
            self.validate('<coverage version="1"><file path="Module.bsl">')


if __name__ == "__main__":
    unittest.main()
