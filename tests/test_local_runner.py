from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.mcp.local_runner import run_tool
from pipeline.mcp.tools import ToolExecutionError


class LocalRunnerTests(unittest.TestCase):
    def test_run_tool_returns_doctor_payload_directly(self) -> None:
        doctor_payload = {"overallStatus": "ok", "checks": [], "nextActions": []}

        with mock.patch("pipeline.mcp.local_runner.build_doctor_payload", return_value=doctor_payload):
            result = run_tool("doctor", {"unity_project_path": "/tmp/Project"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["tool"], "doctor")
        self.assertEqual(result["payload"]["overallStatus"], "ok")

    def test_run_tool_extracts_wrapped_start_ui_build_payload(self) -> None:
        start_payload = {
            "selectedPath": "catalog_draft",
            "execution": {"draftMode": "panel_sprite"},
            "nextActions": ["draft action"],
        }
        wrapped_result = {
            "content": [
                {
                    "type": "text",
                    "text": '{"title": "start_ui_build", "payload": {"selectedPath": "catalog_draft", "execution": {"draftMode": "panel_sprite"}, "nextActions": ["draft action"]}}',
                }
            ],
            "isError": False,
        }

        with mock.patch("pipeline.mcp.local_runner.start_ui_build", return_value=wrapped_result):
            result = run_tool("start_ui_build", {"goal": "shop popup"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["payload"], start_payload)

    def test_run_tool_surfaces_tool_execution_error(self) -> None:
        with mock.patch(
            "pipeline.mcp.local_runner.start_ui_build",
            side_effect=ToolExecutionError("Doctor detected blocking setup issues", details={"doctor": {"overallStatus": "error"}}),
        ):
            result = run_tool("start_ui_build", {"goal": "shop popup"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "Doctor detected blocking setup issues")
        self.assertEqual(result["details"]["doctor"]["overallStatus"], "error")

    def test_run_tool_prefixes_generic_exception_with_type_name(self) -> None:
        with mock.patch(
            "pipeline.mcp.local_runner.start_ui_build",
            side_effect=TimeoutError("timed out"),
        ):
            result = run_tool("start_ui_build", {"goal": "shop popup"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "TimeoutError: timed out")

    def test_capture_result_resolves_assets_relative_screenshot_path(self) -> None:
        fake_response = {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": '{"success": true, "data": {"path": "Assets/Screenshots/reward.png"}}',
                    }
                ]
            }
        }
        fake_client = mock.Mock()
        fake_client.request.return_value = fake_response

        with mock.patch("pipeline.mcp.local_runner.get_unity_http_client", return_value=fake_client):
            result = run_tool(
                "capture_result",
                {
                    "unity_project_path": "/tmp/UnityProject",
                    "unity_mcp_url": "http://127.0.0.1:8080/mcp",
                    "verify_request": {
                        "tool": "manage_camera",
                        "parameters": {
                            "action": "screenshot",
                            "view_target": "RewardPopupCanvas",
                        },
                    },
                },
            )

        self.assertTrue(result["ok"])
        expected_path = str(Path("/tmp/UnityProject/Assets/Screenshots/reward.png").resolve())
        self.assertEqual(result["payload"]["capturedPath"], expected_path)
        self.assertFalse(result["payload"]["request"]["include_image"])

    def test_run_tool_extracts_wrapped_verification_repair_payload(self) -> None:
        wrapped_result = {
            "content": [
                {
                    "type": "text",
                    "text": '{"title": "run_verification_repair_loop", "payload": {"repairHandoff": "/tmp/repair.json", "hasErrors": false}}',
                }
            ],
            "isError": False,
        }

        with mock.patch("pipeline.mcp.local_runner.run_verification_repair_loop", return_value=wrapped_result):
            result = run_tool(
                "run_verification_repair_loop",
                {"reference_image": "/tmp/reference.png", "captured_image": "/tmp/captured.png"},
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["payload"]["repairHandoff"], "/tmp/repair.json")


if __name__ == "__main__":
    unittest.main()
