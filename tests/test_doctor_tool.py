from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.mcp.tools import doctor as doctor_tool


def _doctor_payload(result: dict[str, object]) -> dict[str, object]:
    content = result["content"]
    assert isinstance(content, list)
    raw = content[1]["text"]
    assert isinstance(raw, str)
    return json.loads(raw)


def _make_unity_project(with_catalog: bool = True) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temp_dir = tempfile.TemporaryDirectory()
    project_path = Path(temp_dir.name)
    for dirname in ("Assets", "Packages", "ProjectSettings"):
        (project_path / dirname).mkdir(parents=True, exist_ok=True)

    if with_catalog:
        catalog_path = project_path / "Library/ResourceRag/resource_catalog.jsonl"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        records = [
            {"name": "RewardPanel", "assetType": "Prefab", "path": "Assets/UI/RewardPanel.prefab"},
            {"name": "ButtonPrimary", "assetType": "Sprite", "path": "Assets/UI/ButtonPrimary.png"},
        ]
        with catalog_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    return temp_dir, project_path


class DoctorToolTests(unittest.TestCase):
    def test_doctor_reports_ready_project(self) -> None:
        temp_dir, project_path = _make_unity_project(with_catalog=True)
        self.addCleanup(temp_dir.cleanup)

        def fake_post_json_rpc(url: str, method: str, params: dict[str, object] | None, timeout_ms: int, request_id: int) -> dict[str, object]:
            self.assertEqual(url, "http://127.0.0.1:8080/mcp")
            if method == "tools/list":
                return {"tools": [{"name": "index_project_resources"}, {"name": "apply_ui_blueprint"}]}
            if method == "resources/list":
                return {"resources": [{"name": "ui_asset_catalog"}]}
            raise AssertionError(f"Unexpected method: {method}")

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("pipeline.mcp.doctor._post_json_rpc", side_effect=fake_post_json_rpc):
                result = doctor_tool(
                    {
                        "unity_project_path": str(project_path),
                        "connection_preset": "offline_local",
                    }
                )

        payload = _doctor_payload(result)
        self.assertFalse(result["isError"])
        self.assertEqual(payload["overallStatus"], "ok")
        checks = {item["key"]: item for item in payload["checks"]}
        self.assertEqual(checks["provider_setup"]["status"], "ok")
        self.assertEqual(checks["unity_project"]["status"], "ok")
        self.assertEqual(checks["catalog"]["status"], "ok")
        self.assertEqual(checks["unity_mcp"]["status"], "ok")
        self.assertEqual(checks["catalog"]["details"]["recordCount"], 2)

    def test_doctor_warns_when_unity_mcp_is_project_scoped(self) -> None:
        temp_dir, project_path = _make_unity_project(with_catalog=True)
        self.addCleanup(temp_dir.cleanup)

        def fake_post_json_rpc(url: str, method: str, params: dict[str, object] | None, timeout_ms: int, request_id: int) -> dict[str, object]:
            if method == "tools/list":
                return {"tools": [{"name": "execute_custom_tool"}]}
            if method == "resources/list":
                return {"resources": [{"uri": "mcpforunity://custom-tools"}]}
            raise AssertionError(f"Unexpected method: {method}")

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("pipeline.mcp.doctor._post_json_rpc", side_effect=fake_post_json_rpc):
                result = doctor_tool(
                    {
                        "unity_project_path": str(project_path),
                        "connection_preset": "offline_local",
                    }
                )

        payload = _doctor_payload(result)
        self.assertEqual(payload["overallStatus"], "warn")
        checks = {item["key"]: item for item in payload["checks"]}
        self.assertEqual(checks["unity_mcp"]["status"], "warn")
        self.assertTrue(checks["unity_mcp"]["details"]["projectScopedSymptom"])
        self.assertIn("Project Scoped Tools", " ".join(payload["nextActions"]))

    def test_doctor_warns_when_catalog_is_missing(self) -> None:
        temp_dir, project_path = _make_unity_project(with_catalog=False)
        self.addCleanup(temp_dir.cleanup)

        def fake_post_json_rpc(url: str, method: str, params: dict[str, object] | None, timeout_ms: int, request_id: int) -> dict[str, object]:
            if method == "tools/list":
                return {"tools": [{"name": "index_project_resources"}, {"name": "apply_ui_blueprint"}]}
            if method == "resources/list":
                return {"resources": [{"name": "ui_asset_catalog"}]}
            raise AssertionError(f"Unexpected method: {method}")

        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("pipeline.mcp.doctor._post_json_rpc", side_effect=fake_post_json_rpc):
                result = doctor_tool(
                    {
                        "unity_project_path": str(project_path),
                        "connection_preset": "offline_local",
                    }
                )

        payload = _doctor_payload(result)
        self.assertEqual(payload["overallStatus"], "warn")
        checks = {item["key"]: item for item in payload["checks"]}
        self.assertEqual(checks["catalog"]["status"], "warn")
        self.assertIn("index_project_resources", " ".join(payload["nextActions"]))


if __name__ == "__main__":
    unittest.main()
