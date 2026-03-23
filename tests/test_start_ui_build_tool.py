from __future__ import annotations

import json
import sys
import unittest
from unittest import mock


REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.mcp.tools import start_ui_build


def _formatted_result(title: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps({"title": title, "payload": payload}, ensure_ascii=False),
            }
        ],
        "isError": False,
    }


def _tool_payload(result: dict[str, object]) -> dict[str, object]:
    content = result["content"]
    assert isinstance(content, list)
    raw = content[0]["text"]
    assert isinstance(raw, str)
    wrapped = json.loads(raw)
    payload = wrapped["payload"]
    assert isinstance(payload, dict)
    return payload


class StartUiBuildToolTests(unittest.TestCase):
    def test_start_ui_build_routes_to_first_pass_when_reference_is_present(self) -> None:
        doctor_payload = {
            "overallStatus": "warn",
            "nextActions": ["doctor action"],
            "checks": [],
        }
        first_pass_payload = {
            "catalogPath": "/tmp/resource_catalog.jsonl",
            "resolvedBlueprint": "/tmp/03-resolved-blueprint.json",
            "nextActions": ["first pass action"],
        }

        with mock.patch("pipeline.mcp.tools.build_doctor_payload", return_value=doctor_payload) as doctor_mock:
            with mock.patch(
                "pipeline.mcp.tools.run_first_pass_ui_build",
                return_value=_formatted_result("run_first_pass_ui_build", first_pass_payload),
            ) as first_pass_mock:
                with mock.patch("pipeline.mcp.tools.run_catalog_draft_ui_build") as catalog_mock:
                    result = start_ui_build(
                        {
                            "image": "/tmp/reference.png",
                            "unity_project_path": "/tmp/Project",
                            "connection_preset": "offline_local",
                        }
                    )

        payload = _tool_payload(result)
        self.assertEqual(payload["selectedPath"], "reference_first_pass")
        self.assertEqual(payload["doctor"]["overallStatus"], "warn")
        self.assertEqual(payload["execution"]["catalogPath"], "/tmp/resource_catalog.jsonl")
        self.assertEqual(payload["nextActions"], ["doctor action", "first pass action"])
        doctor_mock.assert_called_once()
        first_pass_mock.assert_called_once()
        catalog_mock.assert_not_called()

    def test_start_ui_build_routes_to_catalog_draft_and_infers_goal(self) -> None:
        doctor_payload = {
            "overallStatus": "ok",
            "nextActions": [],
            "checks": [],
        }
        catalog_payload = {
            "templateMode": "list",
            "draftMode": "panel_sprite",
            "draftBlueprint": "/tmp/01-catalog-draft-blueprint.json",
            "nextActions": ["draft action"],
        }

        with mock.patch("pipeline.mcp.tools.build_doctor_payload", return_value=doctor_payload):
            with mock.patch("pipeline.mcp.tools.run_first_pass_ui_build") as first_pass_mock:
                with mock.patch(
                    "pipeline.mcp.tools.run_catalog_draft_ui_build",
                    return_value=_formatted_result("run_catalog_draft_ui_build", catalog_payload),
                ) as catalog_mock:
                    result = start_ui_build(
                        {
                            "title": "Night Shift Shop",
                            "template_mode": "list",
                            "screen_name": "ShopPopupDraft",
                            "unity_project_path": "/tmp/Project",
                        }
                    )

        payload = _tool_payload(result)
        self.assertEqual(payload["selectedPath"], "catalog_draft")
        self.assertEqual(payload["execution"]["templateMode"], "list")
        self.assertEqual(payload["execution"]["draftMode"], "panel_sprite")
        self.assertEqual(payload["nextActions"], ["draft action"])
        self.assertIn("template_mode `list`", payload["routeReason"])
        first_pass_mock.assert_not_called()
        called_args = catalog_mock.call_args.args[0]
        self.assertEqual(called_args["goal"], "Night Shift Shop")
        self.assertEqual(called_args["template_mode"], "list")

    def test_start_ui_build_stops_when_doctor_reports_error(self) -> None:
        doctor_payload = {
            "overallStatus": "error",
            "nextActions": ["fix setup"],
            "checks": [],
        }

        with mock.patch("pipeline.mcp.tools.build_doctor_payload", return_value=doctor_payload):
            with mock.patch("pipeline.mcp.tools.run_first_pass_ui_build") as first_pass_mock:
                with self.assertRaisesRegex(Exception, "Doctor detected blocking setup issues"):
                    start_ui_build(
                        {
                            "image": "/tmp/reference.png",
                            "unity_project_path": "/tmp/Project",
                        }
                    )

        first_pass_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
