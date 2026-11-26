#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Tests make_reference_text.py over the two roots it reads: a GUI.Forms
checkout and an installed SDK prefix, each a small fixture. The pack names the
GUI.Forms build the program is built against, and docs of another build are
refused."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parent / "make_reference_text.py"

REGISTRY = '{"controls": [{"type": "button", "category": "Commands", "purpose": "Runs a command."}]}\n'
TOPIC = "Commands\n========\n\nThe command types.\n\n- :doc:`generated/gui_forms.button`\n"
BUTTON = "button\n======\n\n:gf_source: include/gui_forms/button.hpp\n\nA push button.\n"


def write_pages(api: Path) -> None:
    (api / "generated").mkdir(parents=True)
    (api / "library.commands.rst").write_text(TOPIC)
    (api / "generated/gui_forms.button.rst").write_text(BUTTON)


def run(root: Path, out: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-B", str(TOOL), "--gui-forms", str(root), "--out", str(out), *extra],
                          capture_output=True, text=True)


def pack_line(out: Path) -> list[str]:
    return out.read_text(encoding="utf-8").splitlines()[0].split("\t")


class CheckoutRoot(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.root = self.directory / "gui_forms"
        write_pages(self.root / "docs/api")
        (self.root / "manifests").mkdir()
        (self.root / "manifests/controls.json").write_text(REGISTRY)
        (self.root / "CMakeLists.txt").write_text("project(GUIForms VERSION 1.0.5 LANGUAGES C CXX)\n")
        git = ["git", "-C", str(self.root), "-c", "user.name=test", "-c", "user.email=test@example.invalid"]
        subprocess.run(git[:3] + ["init", "-q"], check=True)
        subprocess.run(git + ["add", "-A"], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "fixture"], check=True)
        self.commit = subprocess.run(git[:3] + ["rev-parse", "HEAD"], check=True, capture_output=True,
                                     text=True).stdout.strip()
        self.out = self.directory / "reference.txt"

    def tearDown(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_names_the_checkout_build(self) -> None:
        result = run(self.root, self.out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(pack_line(self.out), ["@@pack", "1.0.5", self.commit[:12]])
        text = self.out.read_text(encoding="utf-8")
        self.assertIn("GUI.Forms 1.0.5 reference", text)
        self.assertIn("@@page\ttype/button", text)
        self.assertIn("@@page\ttopic/commands", text)

    def test_accepts_the_build_it_describes(self) -> None:
        result = run(self.root, self.out, "--version", "1.0.5", "--commit", self.commit)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(pack_line(self.out), ["@@pack", "1.0.5", self.commit[:12]])

    def test_refuses_another_version(self) -> None:
        result = run(self.root, self.out, "--version", "1.0.6")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("1.0.6", result.stderr)
        self.assertFalse(self.out.exists())

    def test_refuses_another_commit(self) -> None:
        other = "0" * 40 if not self.commit.startswith("0") else "1" * 40
        result = run(self.root, self.out, "--commit", other)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("commit", result.stderr)
        self.assertFalse(self.out.exists())


class SdkRoot(unittest.TestCase):
    COMMIT = "66a57f2d662d8189762dd96db55a2816b32843a9"

    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.root = self.directory / "gui-forms-sdk"
        share = self.root / "share/GUIForms"
        write_pages(share / "docs/api")
        (share / "ledgers").mkdir(parents=True)
        (share / "ledgers/controls.json").write_text(REGISTRY)
        config = self.root / "lib/cmake/GUIForms"
        config.mkdir(parents=True)
        (config / "GUIFormsConfigVersion.cmake").write_text('set(PACKAGE_VERSION "1.0.5")\n')
        self.out = self.directory / "reference.txt"

    def tearDown(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_reads_the_installed_docs(self) -> None:
        (self.root / "share/GUIForms/docs/api/REVISION").write_text(self.COMMIT + "\n")
        result = run(self.root, self.out, "--version", "1.0.5")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(pack_line(self.out), ["@@pack", "1.0.5", self.COMMIT[:12]])
        self.assertIn("@@page\ttype/button", self.out.read_text(encoding="utf-8"))

    def test_takes_the_commit_from_the_build(self) -> None:
        result = run(self.root, self.out, "--commit", self.COMMIT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(pack_line(self.out), ["@@pack", "1.0.5", self.COMMIT[:12]])

    def test_without_a_commit_says_so(self) -> None:
        result = run(self.root, self.out)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--commit", result.stderr)

    def test_refuses_an_sdk_of_another_version(self) -> None:
        result = run(self.root, self.out, "--version", "1.0.4", "--commit", self.COMMIT)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("1.0.4", result.stderr)

    def test_refuses_a_root_without_inputs(self) -> None:
        result = run(self.directory, self.out, "--commit", self.COMMIT)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no GUI.Forms reference inputs", result.stderr)


if __name__ == "__main__":
    unittest.main()
