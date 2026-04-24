from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"
EDITOR_SETTINGS_PATH = (
    REPO_ROOT
    / "Packages"
    / "com.hanjo92.unity-resource-rag"
    / "Editor"
    / "UnityResourceRagEditorSettings.cs"
)


class PythonRuntimeRequirementTests(unittest.TestCase):
    def test_readme_python_setup_uses_versioned_python_command(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn("python3.12 -m venv .venv", readme)
        self.assertIn("Python 3.11+", readme)
        self.assertIn("python3.11", readme)

    def test_unity_python_detection_rejects_older_interpreters(self) -> None:
        source = EDITOR_SETTINGS_PATH.read_text(encoding="utf-8")

        self.assertIn("MinimumPythonMajorVersion = 3", source)
        self.assertIn("MinimumPythonMinorVersion = 11", source)
        self.assertIn("sys.version_info >= (3, 11)", source)


if __name__ == "__main__":
    unittest.main()
