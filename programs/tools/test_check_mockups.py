"""The mockup check passes the checked-in mockups and reports each defect."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import check_mockups as cm

FORM = """<?xml version="1.0" encoding="UTF-8"?>
<form xmlns="urn:gui-forms:form:1" id="w" text="W" client-size="200 100">
  <panel id="root">
    <check-box id="auto" text="Auto"><bind property="checked" to="autosave"/></check-box>
    <button id="ok" text="OK"><bind property="command" to="accept"/></button>
    <list-box id="list"/>
  </panel>
</form>
"""

FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<fixture xmlns="urn:gui-forms:fixture:1">
  <value name="autosave" value="true"/>
  <records name="people" columns="name age:integer" shown-in="list">
    <row values="'Ada M' 36"/>
  </records>
</fixture>
"""


class CheckMockupsTests(unittest.TestCase):
    def write(self, directory: Path, form: str, fixture: str | None) -> Path:
        path = directory / "sample.form"
        path.write_text(form, encoding="utf-8")
        if fixture is not None:
            (directory / "sample.fixture").write_text(fixture, encoding="utf-8")
        return path

    def test_checked_in_mockups_pass(self) -> None:
        self.assertEqual(cm.main([str(cm.DEFAULT_DIRECTORY)]), 0)

    def test_a_good_mockup_has_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            self.assertEqual(cm.check_mockup(self.write(Path(name), FORM, FIXTURE)), [])

    def test_a_missing_source_is_reported_with_its_line(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            findings = cm.check_mockup(self.write(Path(name), FORM, None))
        self.assertEqual(len(findings), 1)
        self.assertIn("sample.form:4:", findings[0])
        self.assertIn("'autosave'", findings[0])

    def test_shown_in_must_name_an_object(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            findings = cm.check_mockup(self.write(Path(name), FORM, FIXTURE.replace('shown-in="list"', 'shown-in="grid"')))
        self.assertEqual(len(findings), 1)
        self.assertIn("shown-in names grid", findings[0])

    def test_repeated_ids_and_names_and_long_rows(self) -> None:
        form = FORM.replace('id="list"', 'id="ok"')
        fixture = FIXTURE.replace('<row values="\'Ada M\' 36"/>', '<row values="a 1 extra"/>').replace(
            'name="people"', 'name="autosave"')
        with tempfile.TemporaryDirectory() as name:
            findings = cm.check_mockup(self.write(Path(name), form, fixture))
        text = "\n".join(findings)
        self.assertIn("the id ok is used twice", text)
        self.assertIn("the name autosave is used twice", text)
        self.assertIn("3 values for 2 columns", text)

    def test_malformed_xml_and_wrong_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            broken = cm.check_mockup(self.write(Path(name), "<form id='w'><panel></form>", None))
            wrong = cm.check_mockup(self.write(Path(name), FORM.replace("form:1", "form:2"), FIXTURE))
        self.assertIn("not well-formed XML", broken[0])
        self.assertIn('xmlns="urn:gui-forms:form:1"', wrong[0])

    def test_list_items_follow_the_form_list_rules(self) -> None:
        self.assertEqual(cm.split_list("a 'b c' \"d\\\"e\" f"), ["a", "b c", 'd"e', "f"])


if __name__ == "__main__":
    unittest.main()
