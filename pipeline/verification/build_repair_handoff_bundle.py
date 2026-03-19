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


def build_verify_request(root_name: str | None) -> dict[str, Any]:
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


def build_repair_prompt(
    *,
    screen_name: str | None,
    root_name: str | None,
    reference_image: str,
    captured_image: str,
    issues: list[dict[str, Any]],
    focus_nodes: list[dict[str, Any]],
) -> str:
    lines = [
        f"Repair the current Unity UI so it matches the reference image more closely for screen '{screen_name or 'UnknownScreen'}'.",
        f"Reference image: {reference_image}",
        f"Captured image: {captured_image}",
        "Treat this as a bounded repair, not a redesign.",
        "Fix parent containers, top-level anchor grouping, and scaling rules before local offsets.",
        "If a decorative region should read as one baked image, keep it as one image instead of over-modeling it.",
    ]

    if root_name:
        lines.append(f"Focus the repair under root '{root_name}'.")

    if focus_nodes:
        lines.append("Prioritize these suspect nodes:")
        for node in focus_nodes[:4]:
            lines.append(f"- {node.get('hierarchyPath')} ({node.get('kind')})")

    if issues:
        lines.append("Main mismatches:")
        for issue in issues[:3]:
            lines.append(f"- {issue.get('title')}: {issue.get('details')}")

    lines.append("After the smallest structural fix, capture another screenshot and compare again.")
    return "\n".join(lines)


def build_bundle(
    *,
    verification_report: dict[str, Any],
    resolved_blueprint: dict[str, Any] | None,
) -> dict[str, Any]:
    root = (resolved_blueprint or {}).get("root") or {}
    screen_name = (resolved_blueprint or {}).get("screenName") or verification_report.get("screenName")
    root_name = root.get("name")
    focus_nodes = verification_report.get("suspectNodes") or []
    issues = verification_report.get("issues") or []

    return {
        "kind": "unity_ui_repair_handoff_bundle",
        "screenName": screen_name,
        "summary": {
            "hasMeaningfulMismatch": verification_report.get("hasMeaningfulMismatch"),
            "issueCount": len(issues),
            "topSeverity": issues[0]["severity"] if issues else None,
        },
        "focusNodes": focus_nodes[:5],
        "strategyOrder": [
            "Inspect the exact wrong region and its parent chain.",
            "Fix parent/container ownership and top-level anchors first.",
            "Then check CanvasScaler, size rules, and layout ownership.",
            "Only after structure is stable, review asset choice or local spacing.",
            "Re-verify with a screenshot before broadening scope.",
        ],
        "repairPrompt": build_repair_prompt(
            screen_name=screen_name,
            root_name=root_name,
            reference_image=verification_report["referenceImage"],
            captured_image=verification_report["capturedImage"],
            issues=issues,
            focus_nodes=focus_nodes,
        ),
        "requests": {
            "reverify": build_verify_request(root_name),
        },
        "artifacts": {
            "referenceImage": verification_report["referenceImage"],
            "capturedImage": verification_report["capturedImage"],
        },
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a repair handoff bundle from a verification mismatch report."
    )
    parser.add_argument("verification_report", type=Path, help="Path to a verification report JSON")
    parser.add_argument("--resolved-blueprint", type=Path, help="Optional resolved blueprint for root metadata")
    parser.add_argument("--output", type=Path, help="Path to write the repair handoff bundle JSON")
    args = parser.parse_args()

    verification_path = args.verification_report.expanduser().resolve()
    verification_report = load_json(verification_path)
    resolved_blueprint = load_json(args.resolved_blueprint.expanduser().resolve()) if args.resolved_blueprint else None
    bundle = build_bundle(
        verification_report=verification_report,
        resolved_blueprint=resolved_blueprint,
    )

    output_path = args.output or verification_path.with_name(f"{verification_path.stem}.repair-handoff.json")
    save_json(output_path, bundle)
    print(json.dumps({
        "output": str(output_path),
        "issueCount": len(bundle["issues"]),
        "screenName": bundle.get("screenName"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
