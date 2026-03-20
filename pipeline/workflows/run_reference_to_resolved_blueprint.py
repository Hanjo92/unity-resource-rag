#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
PLANNER_DIR = PIPELINE_ROOT / "planner"
RETRIEVAL_DIR = PIPELINE_ROOT / "retrieval"

EXTRACT_SCRIPT = PLANNER_DIR / "extract_reference_layout.py"
TEMPLATE_SCRIPT = PLANNER_DIR / "reference_layout_to_blueprint.py"
VECTOR_INDEX_SCRIPT = RETRIEVAL_DIR / "build_vector_index.py"
BIND_SCRIPT = RETRIEVAL_DIR / "bind_blueprint_assets.py"
MCP_HANDOFF_SCRIPT = PIPELINE_ROOT / "workflows" / "build_mcp_handoff_bundle.py"


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def run_json_command(command: list[str]) -> tuple[int, dict[str, Any], str, str]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=str(PIPELINE_ROOT.parent),
    )

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    payload: dict[str, Any] = {}

    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {"rawStdout": stdout}

    return completed.returncode, payload, stdout, stderr


def default_output_dir(image_path: Path | None, reference_layout_path: Path | None) -> Path:
    source = image_path or reference_layout_path
    assert source is not None
    return source.with_name(f"{source.stem}.unity-ui-flow")


def resolve_vector_index_path(catalog_path: Path, explicit_path: Path | None, output_dir: Path) -> tuple[Path, bool]:
    if explicit_path is not None:
        return explicit_path, explicit_path.exists()

    sibling = catalog_path.with_name("resource_vector_index.json")
    if sibling.exists():
        return sibling, True

    return output_dir / "resource_vector_index.json", False


def build_workflow_report(
    *,
    mode: str,
    output_dir: Path,
    screen_name: str | None,
    image_path: Path | None,
    reference_layout_path: Path | None,
    catalog_path: Path | None,
    vector_index_path: Path | None,
    steps: list[dict[str, Any]],
    has_errors: bool,
) -> dict[str, Any]:
    return {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "screenName": screen_name,
        "outputDir": str(output_dir),
        "image": str(image_path) if image_path else None,
        "referenceLayout": str(reference_layout_path) if reference_layout_path else None,
        "catalog": str(catalog_path) if catalog_path else None,
        "vectorIndex": str(vector_index_path) if vector_index_path else None,
        "hasErrors": has_errors,
        "steps": steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the reference-image-to-resolved-blueprint workflow end to end."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--image", type=Path, help="Path to a reference image to extract from.")
    source_group.add_argument("--reference-layout", type=Path, help="Existing reference layout JSON to start from.")

    parser.add_argument("--catalog", type=Path, help="Path to resource_catalog.jsonl. Required unless --dry-run is used.")
    parser.add_argument("--vector-index", type=Path, help="Optional existing resource_vector_index.json path.")
    parser.add_argument("--output-dir", type=Path, help="Directory for workflow artifacts.")
    parser.add_argument("--screen-name", help="Screen name override for extraction.")
    parser.add_argument("--provider", default="auto", help="Extraction provider: auto, openai, gemini, antigravity, claude, claude_code, openai_compatible, or local_heuristic.")
    parser.add_argument("--provider-base-url", help="Base URL override for openai_compatible, gemini/antigravity, or claude/claude_code extraction providers.")
    parser.add_argument("--provider-api-key-env", default="OPENAI_API_KEY", help="Environment variable name for the extraction provider API key. Provider presets default to OPENAI_API_KEY/openai, GEMINI_API_KEY or GOOGLE_API_KEY/gemini, ANTHROPIC_API_KEY/claude.")
    parser.add_argument("--auth-mode", choices=["api_key", "oauth_token"], help="Authentication mode for API-backed extraction providers.")
    parser.add_argument("--oauth-token-env", help="Environment variable name for an OAuth bearer token.")
    parser.add_argument("--oauth-token-file", help="File path containing an OAuth bearer token.")
    parser.add_argument("--oauth-token-command", help="Command that prints an OAuth bearer token to stdout.")
    parser.add_argument("--codex-auth-file", help="Path to a Codex OAuth auth.json file.")
    parser.add_argument("--model", default="gpt-4.1-mini", help="Extraction model.")
    parser.add_argument("--detail", choices=["low", "high", "auto"], default="high", help="Image detail hint for extraction.")
    parser.add_argument("--max-image-dim", type=int, default=1600, help="Maximum width/height sent to extraction.")
    parser.add_argument("--hint", action="append", default=[], help="Optional prompt hints for extraction.")
    parser.add_argument("--safe-area-component-type", help="Optional safe area component type to inject during extraction.")
    parser.add_argument("--safe-area-properties", help="JSON object string for the injected safe area component.")
    parser.add_argument("--allow-partial", action="store_true", help="Allow unresolved asset queries during binding.")
    parser.add_argument("--dry-run", action="store_true", help="Only run extraction request preview. Valid with --image.")
    args = parser.parse_args()

    image_path = args.image.expanduser().resolve() if args.image else None
    reference_layout_path = args.reference_layout.expanduser().resolve() if args.reference_layout else None
    output_dir = (args.output_dir.expanduser().resolve() if args.output_dir else default_output_dir(image_path, reference_layout_path))
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run and image_path is None:
        raise SystemExit("--dry-run is only valid with --image.")

    if not args.dry_run and args.catalog is None:
        raise SystemExit("--catalog is required unless --dry-run is used.")

    catalog_path = args.catalog.expanduser().resolve() if args.catalog else None
    steps: list[dict[str, Any]] = []
    workflow_report_path = output_dir / "workflow-report.json"

    if image_path is not None and not image_path.exists():
        raise SystemExit(f"Image not found: {image_path}")

    if reference_layout_path is not None and not reference_layout_path.exists():
        raise SystemExit(f"Reference layout not found: {reference_layout_path}")

    current_reference_layout = reference_layout_path
    screen_name = args.screen_name or (image_path.stem if image_path else reference_layout_path.stem if reference_layout_path else None)

    if image_path is not None:
        extracted_layout_path = output_dir / "01-reference-layout.json"
        extraction_report_path = output_dir / "01-extract-report.json"
        command = [
            sys.executable,
            str(EXTRACT_SCRIPT),
            str(image_path),
            "--output",
            str(extracted_layout_path),
            "--report",
            str(extraction_report_path),
            "--provider",
            args.provider,
            "--provider-api-key-env",
            args.provider_api_key_env,
            "--model",
            args.model,
            "--detail",
            args.detail,
            "--max-image-dim",
            str(args.max_image_dim),
        ]

        if args.screen_name:
            command.extend(["--screen-name", args.screen_name])
        if args.provider_base_url:
            command.extend(["--provider-base-url", args.provider_base_url])
        if args.auth_mode:
            command.extend(["--auth-mode", args.auth_mode])
        if args.oauth_token_env:
            command.extend(["--oauth-token-env", args.oauth_token_env])
        if args.oauth_token_file:
            command.extend(["--oauth-token-file", args.oauth_token_file])
        if args.oauth_token_command:
            command.extend(["--oauth-token-command", args.oauth_token_command])
        if args.codex_auth_file:
            command.extend(["--codex-auth-file", args.codex_auth_file])
        for hint in args.hint:
            command.extend(["--hint", hint])
        if args.safe_area_component_type:
            command.extend(["--safe-area-component-type", args.safe_area_component_type])
        if args.safe_area_properties:
            command.extend(["--safe-area-properties", args.safe_area_properties])
        if args.dry_run:
            command.append("--dry-run")

        exit_code, payload, stdout, stderr = run_json_command(command)
        steps.append({
            "step": "extract_reference_layout",
            "exitCode": exit_code,
            "payload": payload,
            "stdout": stdout or None,
            "stderr": stderr or None,
        })

        if exit_code != 0:
            report = build_workflow_report(
                mode="dry-run" if args.dry_run else "image",
                output_dir=output_dir,
                screen_name=screen_name,
                image_path=image_path,
                reference_layout_path=current_reference_layout,
                catalog_path=catalog_path,
                vector_index_path=args.vector_index.expanduser().resolve() if args.vector_index else None,
                steps=steps,
                has_errors=True,
            )
            save_json(workflow_report_path, report)
            print(json.dumps({"workflowReport": str(workflow_report_path), "hasErrors": True}, ensure_ascii=False, indent=2))
            return exit_code

        if args.dry_run:
            report = build_workflow_report(
                mode="dry-run",
                output_dir=output_dir,
                screen_name=screen_name,
                image_path=image_path,
                reference_layout_path=current_reference_layout,
                catalog_path=None,
                vector_index_path=None,
                steps=steps,
                has_errors=False,
            )
            save_json(workflow_report_path, report)
            print(json.dumps({
                "workflowReport": str(workflow_report_path),
                "mode": "dry-run",
                "hasErrors": False,
            }, ensure_ascii=False, indent=2))
            return 0

        current_reference_layout = extracted_layout_path

    assert current_reference_layout is not None
    assert catalog_path is not None

    blueprint_template_path = output_dir / "02-blueprint-template.json"
    exit_code, payload, stdout, stderr = run_json_command([
        sys.executable,
        str(TEMPLATE_SCRIPT),
        str(current_reference_layout),
        "--output",
        str(blueprint_template_path),
    ])
    steps.append({
        "step": "reference_layout_to_blueprint",
        "exitCode": exit_code,
        "payload": payload,
        "stdout": stdout or None,
        "stderr": stderr or None,
    })
    if exit_code != 0:
        report = build_workflow_report(
            mode="layout",
            output_dir=output_dir,
            screen_name=screen_name,
            image_path=image_path,
            reference_layout_path=current_reference_layout,
            catalog_path=catalog_path,
            vector_index_path=args.vector_index.expanduser().resolve() if args.vector_index else None,
            steps=steps,
            has_errors=True,
        )
        save_json(workflow_report_path, report)
        print(json.dumps({"workflowReport": str(workflow_report_path), "hasErrors": True}, ensure_ascii=False, indent=2))
        return exit_code

    vector_index_path, vector_index_exists = resolve_vector_index_path(
        catalog_path,
        args.vector_index.expanduser().resolve() if args.vector_index else None,
        output_dir,
    )
    if not vector_index_exists:
        exit_code, payload, stdout, stderr = run_json_command([
            sys.executable,
            str(VECTOR_INDEX_SCRIPT),
            str(catalog_path),
            "--output",
            str(vector_index_path),
        ])
        steps.append({
            "step": "build_vector_index",
            "exitCode": exit_code,
            "payload": payload,
            "stdout": stdout or None,
            "stderr": stderr or None,
        })
        if exit_code != 0:
            report = build_workflow_report(
                mode="layout",
                output_dir=output_dir,
                screen_name=screen_name,
                image_path=image_path,
                reference_layout_path=current_reference_layout,
                catalog_path=catalog_path,
                vector_index_path=vector_index_path,
                steps=steps,
                has_errors=True,
            )
            save_json(workflow_report_path, report)
            print(json.dumps({"workflowReport": str(workflow_report_path), "hasErrors": True}, ensure_ascii=False, indent=2))
            return exit_code
    else:
        steps.append({
            "step": "build_vector_index",
            "exitCode": 0,
            "payload": {
                "output": str(vector_index_path),
                "reusedExisting": True,
            },
            "stdout": None,
            "stderr": None,
        })

    resolved_blueprint_path = output_dir / "03-resolved-blueprint.json"
    binding_report_path = output_dir / "03-binding-report.json"
    bind_command = [
        sys.executable,
        str(BIND_SCRIPT),
        str(blueprint_template_path),
        str(catalog_path),
        "--output",
        str(resolved_blueprint_path),
        "--report",
        str(binding_report_path),
        "--vector-index",
        str(vector_index_path),
    ]
    if args.allow_partial:
        bind_command.append("--allow-partial")

    exit_code, payload, stdout, stderr = run_json_command(bind_command)
    steps.append({
        "step": "bind_blueprint_assets",
        "exitCode": exit_code,
        "payload": payload,
        "stdout": stdout or None,
        "stderr": stderr or None,
    })

    mcp_handoff_path = output_dir / "04-mcp-handoff.json"
    handoff_exit_code, handoff_payload, handoff_stdout, handoff_stderr = run_json_command([
        sys.executable,
        str(MCP_HANDOFF_SCRIPT),
        str(resolved_blueprint_path),
        "--binding-report",
        str(binding_report_path),
        "--output",
        str(mcp_handoff_path),
    ])
    steps.append({
        "step": "build_mcp_handoff_bundle",
        "exitCode": handoff_exit_code,
        "payload": handoff_payload,
        "stdout": handoff_stdout or None,
        "stderr": handoff_stderr or None,
    })

    has_errors = exit_code != 0 or handoff_exit_code != 0
    report = build_workflow_report(
        mode="image" if image_path is not None else "layout",
        output_dir=output_dir,
        screen_name=screen_name,
        image_path=image_path,
        reference_layout_path=current_reference_layout,
        catalog_path=catalog_path,
        vector_index_path=vector_index_path,
        steps=steps,
        has_errors=has_errors,
    )
    report["artifacts"] = {
        "referenceLayout": str(current_reference_layout),
        "blueprintTemplate": str(blueprint_template_path),
        "resolvedBlueprint": str(resolved_blueprint_path),
        "bindingReport": str(binding_report_path),
        "mcpHandoffBundle": str(mcp_handoff_path),
    }
    if image_path is not None:
        report["artifacts"]["extractReport"] = str(output_dir / "01-extract-report.json")
    save_json(workflow_report_path, report)

    print(json.dumps({
        "workflowReport": str(workflow_report_path),
        "outputDir": str(output_dir),
        "resolvedBlueprint": str(resolved_blueprint_path),
        "bindingReport": str(binding_report_path),
        "mcpHandoffBundle": str(mcp_handoff_path),
        "hasErrors": has_errors,
    }, ensure_ascii=False, indent=2))
    return exit_code or handoff_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
