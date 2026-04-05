#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_CATALOG_PAGE_SIZE = 25
DEFAULT_CATALOG_PAGE_NUMBER = 1


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


def _catalog_request_parameters(catalog_path: str | None) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "pageSize": DEFAULT_CATALOG_PAGE_SIZE,
        "pageNumber": DEFAULT_CATALOG_PAGE_NUMBER,
    }
    if catalog_path:
        parameters["catalogPath"] = catalog_path
    return parameters


def build_catalog_request(catalog_path: str | None) -> dict[str, Any]:
    return {
        "tool": "execute_custom_tool",
        "customToolName": "query_ui_asset_catalog",
        "parameters": _catalog_request_parameters(catalog_path),
    }


def build_direct_catalog_request(catalog_path: str | None) -> dict[str, Any]:
    return {
        "tool": "query_ui_asset_catalog",
        "parameters": _catalog_request_parameters(catalog_path),
    }


def build_catalog_resource_fallback(catalog_path: str | None) -> dict[str, Any]:
    return {
        "resource": "ui_asset_catalog",
        "parameters": _catalog_request_parameters(catalog_path),
    }


def _compact_candidate(candidate: Any) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None

    payload: dict[str, Any] = {}
    for key in ("id", "name", "path", "assetType", "score", "semanticText"):
        value = candidate.get(key)
        if value not in (None, "", []):
            payload[key] = value

    binding = candidate.get("binding")
    if isinstance(binding, dict):
        binding_payload = {
            key: value
            for key, value in binding.items()
            if key in {"kind", "unityLoadPath", "subAssetName", "localFileId"} and value not in (None, "", [])
        }
        if binding_payload:
            payload["binding"] = binding_payload

    return payload or None


def build_catalog_review_targets(binding_report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(binding_report, dict):
        return []

    targets: list[dict[str, Any]] = []
    for entry in binding_report.get("bindings") or []:
        if not isinstance(entry, dict):
            continue

        binding_state = str(entry.get("bindingState") or "")
        if binding_state == "auto_bind":
            continue

        query = entry.get("query") if isinstance(entry.get("query"), dict) else {}
        alternatives = []
        for candidate in entry.get("alternatives") or []:
            compact = _compact_candidate(candidate)
            if compact is not None:
                alternatives.append(compact)
            if len(alternatives) >= 3:
                break

        targets.append(
            {
                "hierarchyPath": entry.get("hierarchyPath"),
                "target": entry.get("target"),
                "bindingState": binding_state,
                "bindingDecision": entry.get("bindingDecision"),
                "queryText": query.get("queryText"),
                "preferredKind": query.get("preferredKind"),
                "chosenCandidate": _compact_candidate(entry.get("chosenCandidate")),
                "alternatives": alternatives,
            }
        )

    return targets


def build_catalog_access(binding_report: dict[str, Any] | None) -> dict[str, Any]:
    catalog_path = str(binding_report.get("catalog") or "") if isinstance(binding_report, dict) else ""
    review_targets = build_catalog_review_targets(binding_report)
    issue_messages = []
    if isinstance(binding_report, dict):
        for issue in binding_report.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            message = str(issue.get("message") or "").strip()
            if message:
                issue_messages.append(message)
            if len(issue_messages) >= 5:
                break

    guidance = [
        "Use `query_ui_asset_catalog` before inventing or replacing prefab, sprite, or TMP font paths.",
        "Treat the catalog as the source of truth for which project assets actually exist.",
        "Use `ui_asset_catalog` only when your MCP client handles raw resource browsing better than tool calls.",
    ]
    if review_targets:
        guidance.append("The binding report contains low-confidence or unresolved entries. Compare `chosenCandidate` and `alternatives` against the catalog before changing the blueprint.")

    payload: dict[str, Any] = {
        "toolName": "query_ui_asset_catalog",
        "resourceName": "ui_asset_catalog",
        "catalogPath": catalog_path or None,
        "preferredRequest": build_catalog_request(catalog_path or None),
        "directToolFallback": build_direct_catalog_request(catalog_path or None),
        "resourceFallback": build_catalog_resource_fallback(catalog_path or None),
        "guidance": guidance,
        "reviewTargets": review_targets,
    }
    if issue_messages:
        payload["issueMessages"] = issue_messages
    return payload


def build_bundle(
    *,
    blueprint_path: Path,
    blueprint: dict[str, Any],
    binding_report_path: Path | None,
    binding_report: dict[str, Any] | None,
) -> dict[str, Any]:
    root = blueprint.get("root") or {}
    root_name = root.get("name")
    catalog_access = build_catalog_access(binding_report)
    catalog_path = catalog_access.get("catalogPath")

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
            "catalogQueryToolName": "query_ui_asset_catalog",
            "catalogResourceName": "ui_asset_catalog",
        },
        "requests": {
            "inspectCatalog": build_catalog_request(catalog_path),
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
            "inspectCatalog": build_direct_catalog_request(catalog_path),
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
        "catalogAccess": catalog_access,
        "artifacts": {
            "resolvedBlueprint": str(blueprint_path),
            "bindingReport": str(binding_report_path) if binding_report_path else None,
            "catalogPath": catalog_path,
        },
        "notes": [
            "Inspect the project catalog with `query_ui_asset_catalog` before inventing or swapping prefab, sprite, or TMP font paths.",
            "Use `ui_asset_catalog` only if your MCP client handles raw resource browsing better than tool calls.",
            "Run validate before apply.",
            "If your MCP client exposes Unity custom tools directly, use directToolFallback.",
            "If custom tools are routed through execute_custom_tool, use requests.inspectCatalog and then requests.validate/apply.",
            "After apply succeeds, run requests.verify to capture a scene view screenshot.",
        ],
    }

    if binding_report is not None:
        bundle["bindingSummary"] = {
            "hasErrors": bool(binding_report.get("hasErrors")),
            "bindingCount": len(binding_report.get("bindings") or []),
            "issueCount": len(binding_report.get("issues") or []),
            "reviewTargetCount": len(catalog_access.get("reviewTargets") or []),
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
