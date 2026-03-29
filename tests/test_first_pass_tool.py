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

from pipeline.mcp.tools import _call_unity_mcp_tool, run_first_pass_ui_build


def _tool_payload(result: dict[str, object]) -> dict[str, object]:
    content = result["content"]
    assert isinstance(content, list)
    raw = content[0]["text"]
    assert isinstance(raw, str)
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)
    return parsed["payload"]


def _formatted_workflow_result(payload: dict[str, object]) -> dict[str, object]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"title": "run_reference_to_resolved_blueprint", "payload": payload}, ensure_ascii=False),
            }
        ],
        "isError": False,
    }


class FirstPassToolTests(unittest.TestCase):
    def test_run_first_pass_ui_build_reindexes_and_applies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            unity_project_path = temp_path / "Project"
            for dirname in ("Assets", "Packages", "ProjectSettings"):
                (unity_project_path / dirname).mkdir(parents=True, exist_ok=True)

            catalog_path = unity_project_path / "Library/ResourceRag/resource_catalog.jsonl"
            resolved_blueprint = temp_path / "03-resolved-blueprint.json"
            resolved_blueprint.write_text("{}", encoding="utf-8")
            handoff_bundle = temp_path / "04-mcp-handoff.json"
            handoff_bundle.write_text(
                json.dumps(
                    {
                        "requests": {
                            "verify": {
                                "tool": "manage_camera",
                                "parameters": {"action": "screenshot", "view_target": "RewardPopupCanvas"},
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            calls: list[tuple[str, dict[str, object]]] = []

            def fake_list_tools(url: str, timeout_ms: int) -> list[str]:
                self.assertEqual(url, "http://127.0.0.1:8080/mcp")
                return ["index_project_resources", "apply_ui_blueprint"]

            def fake_call_tool(
                url: str,
                available_tools: list[str],
                tool_name: str,
                arguments: dict[str, object],
                timeout_ms: int,
                unity_project_path: Path | None = None,
            ) -> dict[str, object]:
                calls.append((tool_name, arguments))
                if tool_name == "index_project_resources":
                    catalog_path.parent.mkdir(parents=True, exist_ok=True)
                    catalog_path.write_text('{"name":"RewardPanel","assetType":"Prefab","path":"Assets/UI/RewardPanel.prefab"}\n', encoding="utf-8")
                    return {"tool": tool_name, "invocationMode": "direct", "response": {"success": True}}
                if tool_name == "apply_ui_blueprint":
                    return {"tool": tool_name, "invocationMode": "direct", "response": {"success": True, "data": {"rootName": "RewardPopupCanvas"}}}
                raise AssertionError(f"Unexpected tool: {tool_name}")

            workflow_payload = {
                "workflowReport": str(temp_path / "workflow-report.json"),
                "outputDir": str(temp_path),
                "resolvedBlueprint": str(resolved_blueprint),
                "bindingReport": str(temp_path / "03-binding-report.json"),
                "mcpHandoffBundle": str(handoff_bundle),
                "hasErrors": False,
            }

            with mock.patch("pipeline.mcp.tools._list_unity_mcp_tools", side_effect=fake_list_tools):
                with mock.patch("pipeline.mcp.tools._call_unity_mcp_tool", side_effect=fake_call_tool):
                    with mock.patch("pipeline.mcp.tools.run_reference_to_resolved_blueprint", return_value=_formatted_workflow_result(workflow_payload)) as workflow_mock:
                        result = run_first_pass_ui_build(
                            {
                                "image": str(temp_path / "reference.png"),
                                "unity_project_path": str(unity_project_path),
                                "connection_preset": "offline_local",
                            }
                        )

            payload = _tool_payload(result)
            self.assertEqual(Path(payload["catalogPath"]).resolve(), catalog_path.resolve())
            self.assertTrue(payload["catalogIndexed"])
            self.assertEqual(payload["unityApply"]["invocationMode"], "direct")
            self.assertEqual(payload["verifyRequest"]["tool"], "manage_camera")
            self.assertEqual([name for name, _ in calls], ["index_project_resources", "apply_ui_blueprint", "apply_ui_blueprint"])
            workflow_args = workflow_mock.call_args.args[0]
            self.assertEqual(Path(workflow_args["catalog"]).resolve(), catalog_path.resolve())

    def test_call_unity_mcp_tool_falls_back_to_execute_custom_tool(self) -> None:
        captured: list[dict[str, object]] = []

        def fake_http_request(url: str, method: str, params: dict[str, object] | None, timeout_ms: int, request_id: int) -> dict[str, object]:
            captured.append({"url": url, "method": method, "params": params or {}})
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"success": True, "data": {"recordCount": 2}}, ensure_ascii=False),
                    }
                ]
            }

        with mock.patch("pipeline.mcp.tools._http_json_request", side_effect=fake_http_request):
            result = _call_unity_mcp_tool(
                "http://127.0.0.1:8080/mcp",
                ["execute_custom_tool"],
                "query_ui_asset_catalog",
                {"pageSize": 2},
                3000,
            )

        self.assertEqual(result["invocationMode"], "execute_custom_tool")
        self.assertEqual(captured[0]["method"], "tools/call")
        self.assertEqual(captured[0]["params"]["name"], "execute_custom_tool")
        self.assertEqual(captured[0]["params"]["arguments"]["customToolName"], "query_ui_asset_catalog")

    def test_run_first_pass_ui_build_requires_catalog_or_project(self) -> None:
        with self.assertRaisesRegex(Exception, "catalog"):
            run_first_pass_ui_build(
                {
                    "image": "/tmp/reference.png",
                    "connection_preset": "offline_local",
                    "apply_in_unity": False,
                }
            )


if __name__ == "__main__":
    unittest.main()
