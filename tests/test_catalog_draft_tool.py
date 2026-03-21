from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.mcp.tools import run_catalog_draft_ui_build


def _tool_payload(result: dict[str, object]) -> dict[str, object]:
    content = result["content"]
    assert isinstance(content, list)
    raw = content[0]["text"]
    assert isinstance(raw, str)
    wrapped = json.loads(raw)
    payload = wrapped["payload"]
    assert isinstance(payload, dict)
    return payload


def _write_catalog(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


class CatalogDraftToolTests(unittest.TestCase):
    def test_run_catalog_draft_ui_build_reindexes_and_applies_prefab_shell(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            unity_project_path = temp_path / "Project"
            for dirname in ("Assets", "Packages", "ProjectSettings"):
                (unity_project_path / dirname).mkdir(parents=True, exist_ok=True)

            catalog_path = unity_project_path / "Library/ResourceRag/resource_catalog.jsonl"
            records = [
                {
                    "id": "prefab-shell",
                    "guid": "guid-prefab-shell",
                    "path": "Assets/UI/PF_RewardPopup.prefab",
                    "assetType": "Prefab",
                    "name": "PF_RewardPopup",
                    "semanticText": "reward popup modal dialog shell window frame",
                    "binding": {"kind": "prefab", "unityLoadPath": "Assets/UI/PF_RewardPopup.prefab"},
                },
                {
                    "id": "panel-sprite",
                    "guid": "guid-panel-sprite",
                    "localFileId": 21300000,
                    "path": "Assets/UI/PopupFrame.png",
                    "subAssetName": "PopupFrame",
                    "assetType": "Sprite",
                    "name": "PopupFrame",
                    "semanticText": "popup frame panel background reward window",
                    "uiHints": {"isNineSliceCandidate": True},
                    "binding": {
                        "kind": "sprite",
                        "unityLoadPath": "Assets/UI/PopupFrame.png",
                        "subAssetName": "PopupFrame",
                        "localFileId": 21300000,
                    },
                },
                {
                    "id": "reward-icon",
                    "guid": "guid-reward-icon",
                    "localFileId": 21300001,
                    "path": "Assets/UI/RewardIcon.png",
                    "subAssetName": "RewardIcon",
                    "assetType": "Sprite",
                    "name": "RewardIcon",
                    "semanticText": "reward item icon badge",
                    "binding": {
                        "kind": "sprite",
                        "unityLoadPath": "Assets/UI/RewardIcon.png",
                        "subAssetName": "RewardIcon",
                        "localFileId": 21300001,
                    },
                },
                {
                    "id": "title-font",
                    "guid": "guid-title-font",
                    "path": "Assets/UI/Fonts/TitleFont.asset",
                    "assetType": "TMP_FontAsset",
                    "name": "TitleFont",
                    "semanticText": "ui title heading font bold",
                    "binding": {"kind": "tmp_font", "unityLoadPath": "Assets/UI/Fonts/TitleFont.asset"},
                },
                {
                    "id": "body-font",
                    "guid": "guid-body-font",
                    "path": "Assets/UI/Fonts/BodyFont.asset",
                    "assetType": "TMP_FontAsset",
                    "name": "BodyFont",
                    "semanticText": "readable ui body font sans",
                    "binding": {"kind": "tmp_font", "unityLoadPath": "Assets/UI/Fonts/BodyFont.asset"},
                },
            ]

            calls: list[tuple[str, dict[str, object]]] = []

            def fake_list_tools(url: str, timeout_ms: int) -> list[str]:
                self.assertEqual(url, "http://127.0.0.1:8080/mcp")
                self.assertEqual(timeout_ms, 3000)
                return ["index_project_resources", "apply_ui_blueprint"]

            def fake_call_tool(
                unity_mcp_url: str,
                available_tools: list[str],
                tool_name: str,
                arguments: dict[str, object],
                timeout_ms: int,
            ) -> dict[str, object]:
                calls.append((tool_name, arguments))
                if tool_name == "index_project_resources":
                    _write_catalog(catalog_path, records)
                    return {
                        "tool": tool_name,
                        "invocationMode": "direct",
                        "response": {"success": True, "recordCount": len(records)},
                    }
                if tool_name == "apply_ui_blueprint":
                    return {
                        "tool": tool_name,
                        "invocationMode": "direct",
                        "response": {
                            "success": True,
                            "screenName": "RewardPopupDraft",
                            "verificationHint": {"rootName": "RewardPopupDraftCanvas"},
                        },
                    }
                raise AssertionError(f"Unexpected tool: {tool_name}")

            def fake_search_catalog(
                catalog: Path,
                query_text: str,
                *,
                preferred_kind: str | None = None,
                region_type: str | None = None,
                aspect_ratio: float | None = None,
                vector_index_path: Path | None = None,
                top_k: int = 5,
            ) -> dict[str, object]:
                if preferred_kind == "prefab":
                    return {"results": [{"id": "prefab-shell", "score": 0.72, "path": "Assets/UI/PF_RewardPopup.prefab", "name": "PF_RewardPopup", "assetType": "Prefab", "binding": {"kind": "prefab"}, "semanticText": "reward popup modal dialog shell"}]}
                if preferred_kind == "sprite" and region_type == "popup_frame":
                    return {"results": [{"id": "panel-sprite", "score": 0.61, "path": "Assets/UI/PopupFrame.png", "name": "PopupFrame", "assetType": "Sprite", "binding": {"kind": "sprite"}, "semanticText": "popup frame panel"}]}
                if preferred_kind == "sprite" and region_type == "icon":
                    return {"results": [{"id": "reward-icon", "score": 0.58, "path": "Assets/UI/RewardIcon.png", "name": "RewardIcon", "assetType": "Sprite", "binding": {"kind": "sprite"}, "semanticText": "reward icon"}]}
                if preferred_kind == "tmp_font" and "title" in query_text:
                    return {"results": [{"id": "title-font", "score": 0.42, "path": "Assets/UI/Fonts/TitleFont.asset", "name": "TitleFont", "assetType": "TMP_FontAsset", "binding": {"kind": "tmp_font"}, "semanticText": "title heading font"}]}
                if preferred_kind == "tmp_font":
                    return {"results": [{"id": "body-font", "score": 0.39, "path": "Assets/UI/Fonts/BodyFont.asset", "name": "BodyFont", "assetType": "TMP_FontAsset", "binding": {"kind": "tmp_font"}, "semanticText": "body font"}]}
                raise AssertionError(f"Unexpected search query: {query_text}")

            with mock.patch("pipeline.mcp.tools._list_unity_mcp_tools", side_effect=fake_list_tools):
                with mock.patch("pipeline.mcp.tools._call_unity_mcp_tool", side_effect=fake_call_tool):
                    with mock.patch("pipeline.mcp.tools._search_catalog_records", side_effect=fake_search_catalog):
                        result = run_catalog_draft_ui_build(
                            {
                                "goal": "reward popup",
                                "screen_name": "RewardPopupDraft",
                                "title": "Reward Unlocked",
                                "body": "Collect the bonus reward and continue.",
                                "primary_action_label": "CLAIM",
                                "secondary_action_label": "CLOSE",
                                "price_text": "FREE",
                                "unity_project_path": str(unity_project_path),
                                "force_reindex": True,
                                "unity_mcp_timeout_ms": 3000,
                            }
                        )

            payload = _tool_payload(result)
            self.assertTrue(payload["catalogIndexed"])
            self.assertEqual(payload["draftMode"], "shell_prefab")
            self.assertEqual(payload["unityApply"]["invocationMode"], "direct")
            self.assertEqual(payload["verifyRequest"]["tool"], "manage_camera")
            self.assertEqual([name for name, _ in calls], ["index_project_resources", "apply_ui_blueprint", "apply_ui_blueprint"])

            blueprint_path = Path(payload["draftBlueprint"])
            self.assertTrue(blueprint_path.exists())
            blueprint = json.loads(blueprint_path.read_text(encoding="utf-8"))
            shell_node = blueprint["root"]["children"][0]["children"][0]
            self.assertEqual(shell_node["kind"], "prefab_instance")
            self.assertEqual(shell_node["asset"]["path"], "Assets/UI/PF_RewardPopup.prefab")
            overlay_children = shell_node["children"][0]["children"]
            self.assertEqual(overlay_children[0]["text"]["value"], "Reward Unlocked")

    def test_run_catalog_draft_ui_build_falls_back_to_panel_sprite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            unity_project_path = temp_path / "Project"
            for dirname in ("Assets", "Packages", "ProjectSettings"):
                (unity_project_path / dirname).mkdir(parents=True, exist_ok=True)

            catalog_path = unity_project_path / "Library/ResourceRag/resource_catalog.jsonl"
            records = [
                {
                    "id": "panel-sprite",
                    "guid": "guid-panel-sprite",
                    "localFileId": 21300000,
                    "path": "Assets/UI/PopupFrame.png",
                    "subAssetName": "PopupFrame",
                    "assetType": "Sprite",
                    "name": "PopupFrame",
                    "semanticText": "popup frame panel background reward window",
                    "uiHints": {"isNineSliceCandidate": True},
                    "binding": {
                        "kind": "sprite",
                        "unityLoadPath": "Assets/UI/PopupFrame.png",
                        "subAssetName": "PopupFrame",
                        "localFileId": 21300000,
                    },
                },
                {
                    "id": "body-font",
                    "guid": "guid-body-font",
                    "path": "Assets/UI/Fonts/BodyFont.asset",
                    "assetType": "TMP_FontAsset",
                    "name": "BodyFont",
                    "semanticText": "readable ui body font sans",
                    "binding": {"kind": "tmp_font", "unityLoadPath": "Assets/UI/Fonts/BodyFont.asset"},
                },
            ]
            _write_catalog(catalog_path, records)

            def fake_search_catalog(
                catalog: Path,
                query_text: str,
                *,
                preferred_kind: str | None = None,
                region_type: str | None = None,
                aspect_ratio: float | None = None,
                vector_index_path: Path | None = None,
                top_k: int = 5,
            ) -> dict[str, object]:
                if preferred_kind == "prefab":
                    return {"results": []}
                if preferred_kind == "sprite" and region_type == "popup_frame":
                    return {"results": [{"id": "panel-sprite", "score": 0.55, "path": "Assets/UI/PopupFrame.png", "name": "PopupFrame", "assetType": "Sprite", "binding": {"kind": "sprite"}, "semanticText": "popup frame panel"}]}
                if preferred_kind == "sprite" and region_type == "icon":
                    return {"results": []}
                if preferred_kind == "tmp_font":
                    return {"results": [{"id": "body-font", "score": 0.28, "path": "Assets/UI/Fonts/BodyFont.asset", "name": "BodyFont", "assetType": "TMP_FontAsset", "binding": {"kind": "tmp_font"}, "semanticText": "body font"}]}
                raise AssertionError(f"Unexpected search query: {query_text}")

            with mock.patch("pipeline.mcp.tools._search_catalog_records", side_effect=fake_search_catalog):
                result = run_catalog_draft_ui_build(
                    {
                        "goal": "shop popup",
                        "screen_name": "ShopPopupDraft",
                        "title": "Night Shift Shop",
                        "body": "Catalog-first popup draft without a reusable shell prefab.",
                        "unity_project_path": str(unity_project_path),
                        "apply_in_unity": False,
                    }
                )

            payload = _tool_payload(result)
            self.assertEqual(payload["draftMode"], "panel_sprite")
            self.assertIsNone(payload["unityApply"])
            self.assertIn("panel sprite", " ".join(payload["nextActions"]))

            blueprint_path = Path(payload["draftBlueprint"])
            blueprint = json.loads(blueprint_path.read_text(encoding="utf-8"))
            shell_node = blueprint["root"]["children"][0]["children"][0]
            self.assertEqual(shell_node["kind"], "image")
            self.assertEqual(shell_node["image"]["type"], "Sliced")

    def test_run_catalog_draft_ui_build_requires_catalog_or_project(self) -> None:
        with self.assertRaisesRegex(Exception, "catalog"):
            run_catalog_draft_ui_build(
                {
                    "goal": "reward popup",
                }
            )


if __name__ == "__main__":
    unittest.main()
