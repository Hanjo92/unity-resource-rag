from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "Packages" / "com.hanjo92.unity-resource-rag"
APPLY_TOOL_PATH = PACKAGE_ROOT / "Editor" / "ResourceIndexing" / "ApplyUiBlueprintTool.cs"
CATALOG_BUILDER_PATH = PACKAGE_ROOT / "Editor" / "ResourceIndexing" / "ResourceCatalogBuilder.cs"
CATALOG_MODELS_PATH = PACKAGE_ROOT / "Editor" / "ResourceIndexing" / "ResourceCatalogModels.cs"
WINDOW_PATH = PACKAGE_ROOT / "Editor" / "UnityResourceRagWindow.cs"
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

    def test_catalog_window_exposes_initial_create_action(self) -> None:
        source = WINDOW_PATH.read_text(encoding="utf-8")

        self.assertIn('bool hasCatalogArtifacts = File.Exists(catalogPath) || File.Exists(manifestPath);', source)
        self.assertIn('string catalogButtonLabel = hasCatalogArtifacts ? "카탈로그 재생성" : "카탈로그 생성";', source)
        self.assertIn("GUILayout.Button(catalogButtonLabel", source)

    def test_catalog_models_include_richer_metadata_sections(self) -> None:
        source = CATALOG_MODELS_PATH.read_text(encoding="utf-8")

        self.assertIn("metadataTokens", source)
        self.assertIn("ResourceAssetProvenance", source)
        self.assertIn("ResourceTextureSummary", source)
        self.assertIn("ResourceMaterialSummary", source)
        self.assertIn("componentCounts", source)
        self.assertIn("referencedSpritePaths", source)

    def test_catalog_builder_collects_richer_texture_and_prefab_metadata(self) -> None:
        source = CATALOG_BUILDER_PATH.read_text(encoding="utf-8")

        self.assertIn("BuildAssetProvenance", source)
        self.assertIn("BuildTextureSummary", source)
        self.assertIn("BuildMaterialSummary", source)
        self.assertIn("BuildMetadataTokens", source)
        self.assertIn("ReadObjectProperty", source)
        self.assertIn("referencedSpritePaths", source)
        self.assertIn("componentCounts", source)


if __name__ == "__main__":
    unittest.main()
