from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "Packages" / "com.hanjo92.unity-resource-rag"
APPLY_TOOL_PATH = PACKAGE_ROOT / "Editor" / "ResourceIndexing" / "ApplyUiBlueprintTool.cs"
PACKAGE_JSON_PATH = PACKAGE_ROOT / "package.json"
PACKAGE_README_PATH = PACKAGE_ROOT / "README.md"
PACKAGE_DOC_README_PATH = PACKAGE_ROOT / "Documentation~" / "README.md"
SAMPLE_README_PATH = PACKAGE_ROOT / "Samples~" / "Blueprints" / "README.md"


class UnityPackageSourceTests(unittest.TestCase):
    def test_apply_blueprint_accepts_package_sample_paths(self) -> None:
        source = APPLY_TOOL_PATH.read_text(encoding="utf-8")

        self.assertIn("ResolveBlueprintPath", source)
        self.assertIn("Samples~/", source)
        self.assertIn("PackageInfo.FindForAssembly", source)

    def test_package_docs_do_not_depend_on_repo_relative_parent_links(self) -> None:
        for path in (PACKAGE_README_PATH, PACKAGE_DOC_README_PATH):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("../../", text)
                self.assertIn("https://github.com/Hanjo92/unity-resource-rag", text)

    def test_package_json_registers_blueprint_samples(self) -> None:
        payload = json.loads(PACKAGE_JSON_PATH.read_text(encoding="utf-8"))
        samples = payload.get("samples") or []

        self.assertIn(
            {
                "displayName": "Blueprint samples for project-specific bindings",
                "description": "Project-specific blueprint examples that reference project assets and a custom UI component binding. Use the template file as a starting point for your own retrieval and binding setup.",
                "path": "Samples~/Blueprints",
            },
            samples,
        )

    def test_sample_readme_marks_project_specific_dependencies(self) -> None:
        text = SAMPLE_README_PATH.read_text(encoding="utf-8")

        self.assertIn("Assets/UI/...", text)
        self.assertIn("MyGame.UI.SafeAreaFitter", text)
        self.assertIn("프로젝트 전용 예시", text)


if __name__ == "__main__":
    unittest.main()
