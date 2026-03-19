#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def build_verification_request(root_name: str | None) -> dict[str, Any]:
    return {
        "tool": "manage_camera",
        "parameters": {
            "action": "screenshot",
            "capture_source": "scene_view",
            "view_target": root_name,
            "include_image": True,
            "max_resolution": 768,
        },
    }


def build_bundle(
    *,
    blueprint_path: Path,
    blueprint: dict[str, Any],
    binding_report_path: Path | None,
    binding_report: dict[str, Any] | None,
) -> dict[str, Any]:
    root = blueprint.get("root") or {}
    root_name = root.get("name")

    bundle = {
        "kind": "unity_mcp_handoff_bundle",
        "screenName": blueprint.get("screenName"),
        "resolvedBlueprint": str(blueprint_path),
        "preflight": [
            {
                "type": "resource_check",
                "resource": "custom_tools",
                "mustContain": "apply_ui_blueprint",
                "reason": "Ensure the Unity project discovered the package custom tool before execution.",
            }
        ],
        "contracts": {
            "customToolName": "apply_ui_blueprint",
            "customToolResource": "custom_tools",
        },
        "requests": {
            "validate": {
                "tool": "execute_custom_tool",
                "customToolName": "apply_ui_blueprint",
                "parameters": {
                    "action": "validate",
                    "blueprintPath": str(blueprint_path),
                },
            },
            "apply": {
                "tool": "execute_custom_tool",
                "customToolName": "apply_ui_blueprint",
                "parameters": {
                    "action": "apply",
                    "blueprintPath": str(blueprint_path),
                },
            },
            "verify": build_verification_request(root_name),
        },
        "directToolFallback": {
            "validate": {
                "tool": "apply_ui_blueprint",
                "parameters": {
                    "action": "validate",
                    "blueprintPath": str(blueprint_path),
                },
            },
            "apply": {
                "tool": "apply_ui_blueprint",
                "parameters": {
                    "action": "apply",
                    "blueprintPath": str(blueprint_path),
                },
            },
        },
        "artifacts": {
            "resolvedBlueprint": str(blueprint_path),
            "bindingReport": str(binding_report_path) if binding_report_path else None,
        },
        "notes": [
            "Run validate before apply.",
            "If your MCP client exposes Unity custom tools directly, use directToolFallback.",
            "If custom tools are routed through execute_custom_tool, use requests.validate/apply.",
            "After apply succeeds, run requests.verify to capture a scene view screenshot.",
        ],
    }

    if binding_report is not None:
        bundle["bindingSummary"] = {
            "hasErrors": bool(binding_report.get("hasErrors")),
            "bindingCount": len(binding_report.get("bindings") or []),
            "issueCount": len(binding_report.get("issues") or []),
        }

    return bundle


def default_output_path(blueprint_path: Path) -> Path:
    return blueprint_path.with_name(f"{blueprint_path.stem}.mcp-handoff.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a Unity MCP handoff bundle from a resolved blueprint."
    )
    parser.add_argument("resolved_blueprint", type=Path, help="Path to a resolved blueprint JSON")
    parser.add_argument("--binding-report", type=Path, help="Optional binding report JSON")
    parser.add_argument("--output", type=Path, help="Path to write the handoff bundle JSON")
    args = parser.parse_args()

    blueprint_path = args.resolved_blueprint.expanduser().resolve()
    blueprint = load_json(blueprint_path)
    binding_report_path = args.binding_report.expanduser().resolve() if args.binding_report else None
    binding_report = load_json(binding_report_path) if binding_report_path and binding_report_path.exists() else None

    output_path = args.output or default_output_path(blueprint_path)
    bundle = build_bundle(
        blueprint_path=blueprint_path,
        blueprint=blueprint,
        binding_report_path=binding_report_path,
        binding_report=binding_report,
    )
    save_json(output_path, bundle)

    print(json.dumps({
        "output": str(output_path),
        "screenName": bundle.get("screenName"),
        "hasBindingErrors": (bundle.get("bindingSummary") or {}).get("hasErrors"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
