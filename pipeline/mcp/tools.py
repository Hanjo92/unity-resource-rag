from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = REPO_ROOT / "pipeline"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], dict[str, Any]]


class ToolExecutionError(RuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


def _script_path(*parts: str) -> Path:
    return PIPELINE_ROOT.joinpath(*parts)


def _run_script(script_path: Path, args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
    command = [sys.executable, str(script_path), *args]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO_ROOT),
        env=env or os.environ.copy(),
    )

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    payload: dict[str, Any]

    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {"rawStdout": stdout}
    else:
        payload = {}

    payload["_process"] = {
        "command": command,
        "returnCode": completed.returncode,
        "stdout": stdout or None,
        "stderr": stderr or None,
    }

    if completed.returncode != 0:
        raise ToolExecutionError(
            f"Command failed with exit code {completed.returncode}.",
            details=payload,
        )

    return payload


def _json_arg(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _require_path(args: dict[str, Any], name: str) -> str:
    value = args.get(name)
    if not value or not str(value).strip():
        raise ToolExecutionError(f"Missing required argument: {name}.")
    return str(value)


def _build_extract_reference_layout_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "image": {"type": "string", "description": "Path to the reference image."},
            "output": {"type": "string", "description": "Optional output path for the reference layout JSON."},
            "report": {"type": "string", "description": "Optional output path for the extraction report JSON."},
            "screen_name": {"type": "string"},
            "provider": {"type": "string", "enum": ["auto", "openai", "openai_compatible", "local_heuristic"]},
            "provider_base_url": {"type": "string"},
            "provider_api_key_env": {"type": "string"},
            "auth_mode": {"type": "string", "enum": ["auto", "api_key_env", "oauth_token_env", "oauth_token_file", "oauth_token_command"]},
            "oauth_token_env": {"type": "string"},
            "oauth_token_file": {"type": "string"},
            "oauth_token_command": {"type": "string"},
            "model": {"type": "string"},
            "detail": {"type": "string", "enum": ["low", "high", "auto"]},
            "max_image_dim": {"type": "integer", "minimum": 1},
            "hint": {"type": "array", "items": {"type": "string"}},
            "safe_area_component_type": {"type": "string"},
            "safe_area_properties": {"type": "string", "description": "JSON string for injected safe area component properties."},
            "dry_run": {"type": "boolean"},
        },
        "required": ["image"],
        "additionalProperties": False,
    }


def _build_run_reference_to_resolved_blueprint_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "image": {"type": "string", "description": "Path to the reference image."},
            "reference_layout": {"type": "string", "description": "Existing reference layout JSON. Use this instead of image when already extracted."},
            "catalog": {"type": "string", "description": "Path to resource_catalog.jsonl."},
            "vector_index": {"type": "string"},
            "output_dir": {"type": "string"},
            "screen_name": {"type": "string"},
            "provider": {"type": "string", "enum": ["auto", "openai", "openai_compatible", "local_heuristic"]},
            "provider_base_url": {"type": "string"},
            "provider_api_key_env": {"type": "string"},
            "auth_mode": {"type": "string", "enum": ["auto", "api_key_env", "oauth_token_env", "oauth_token_file", "oauth_token_command"]},
            "oauth_token_env": {"type": "string"},
            "oauth_token_file": {"type": "string"},
            "oauth_token_command": {"type": "string"},
            "model": {"type": "string"},
            "detail": {"type": "string", "enum": ["low", "high", "auto"]},
            "max_image_dim": {"type": "integer", "minimum": 1},
            "hint": {"type": "array", "items": {"type": "string"}},
            "safe_area_component_type": {"type": "string"},
            "safe_area_properties": {"type": "string"},
            "allow_partial": {"type": "boolean"},
            "dry_run": {"type": "boolean"},
        },
        "anyOf": [
            {"required": ["image"]},
            {"required": ["reference_layout"]},
        ],
        "additionalProperties": False,
    }


def _build_run_verification_repair_loop_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "reference_image": {"type": "string"},
            "captured_image": {"type": "string"},
            "resolved_blueprint": {"type": "string"},
            "output_dir": {"type": "string"},
        },
        "required": ["reference_image", "captured_image"],
        "additionalProperties": False,
    }


def _build_build_mcp_handoff_bundle_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "resolved_blueprint": {"type": "string"},
            "binding_report": {"type": "string"},
            "output": {"type": "string"},
        },
        "required": ["resolved_blueprint"],
        "additionalProperties": False,
    }


def _format_tool_result(title: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = {
        "title": title,
        "payload": payload,
    }
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(body, ensure_ascii=False, indent=2),
            }
        ],
        "isError": False,
    }


def _format_tool_error(message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"error": message}
    if details:
        body["details"] = details
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(body, ensure_ascii=False, indent=2),
            }
        ],
        "isError": True,
    }


def extract_reference_layout(args: dict[str, Any]) -> dict[str, Any]:
    script_path = _script_path("planner", "extract_reference_layout.py")
    command = [
        _require_path(args, "image"),
    ]
    opts: list[str] = []
    for key, flag in [
        ("output", "--output"),
        ("report", "--report"),
        ("screen_name", "--screen-name"),
        ("provider", "--provider"),
        ("provider_base_url", "--provider-base-url"),
        ("provider_api_key_env", "--provider-api-key-env"),
        ("auth_mode", "--auth-mode"),
        ("oauth_token_env", "--oauth-token-env"),
        ("oauth_token_file", "--oauth-token-file"),
        ("oauth_token_command", "--oauth-token-command"),
        ("model", "--model"),
        ("detail", "--detail"),
        ("max_image_dim", "--max-image-dim"),
        ("safe_area_component_type", "--safe-area-component-type"),
        ("safe_area_properties", "--safe-area-properties"),
    ]:
        value = args.get(key)
        if value not in (None, "", []):
            opts.extend([flag, str(value)])

    for hint in args.get("hint") or []:
        opts.extend(["--hint", str(hint)])

    if args.get("dry_run"):
        opts.append("--dry-run")

    payload = _run_script(script_path, [command[0], *opts])
    return _format_tool_result("extract_reference_layout", payload)


def run_reference_to_resolved_blueprint(args: dict[str, Any]) -> dict[str, Any]:
    script_path = _script_path("workflows", "run_reference_to_resolved_blueprint.py")
    opts: list[str] = []

    if args.get("image"):
        opts.extend(["--image", str(args["image"])])
    if args.get("reference_layout"):
        opts.extend(["--reference-layout", str(args["reference_layout"])])

    for key, flag in [
        ("catalog", "--catalog"),
        ("vector_index", "--vector-index"),
        ("output_dir", "--output-dir"),
        ("screen_name", "--screen-name"),
        ("provider", "--provider"),
        ("provider_base_url", "--provider-base-url"),
        ("provider_api_key_env", "--provider-api-key-env"),
        ("auth_mode", "--auth-mode"),
        ("oauth_token_env", "--oauth-token-env"),
        ("oauth_token_file", "--oauth-token-file"),
        ("oauth_token_command", "--oauth-token-command"),
        ("model", "--model"),
        ("detail", "--detail"),
        ("max_image_dim", "--max-image-dim"),
        ("safe_area_component_type", "--safe-area-component-type"),
        ("safe_area_properties", "--safe-area-properties"),
    ]:
        value = args.get(key)
        if value not in (None, "", []):
            opts.extend([flag, str(value)])

    for hint in args.get("hint") or []:
        opts.extend(["--hint", str(hint)])

    if args.get("allow_partial"):
        opts.append("--allow-partial")
    if args.get("dry_run"):
        opts.append("--dry-run")

    payload = _run_script(script_path, opts)
    return _format_tool_result("run_reference_to_resolved_blueprint", payload)


def run_verification_repair_loop(args: dict[str, Any]) -> dict[str, Any]:
    script_path = _script_path("workflows", "run_verification_repair_loop.py")
    opts: list[str] = [
        _require_path(args, "reference_image"),
        _require_path(args, "captured_image"),
    ]

    if args.get("resolved_blueprint"):
        opts.extend(["--resolved-blueprint", str(args["resolved_blueprint"])])
    if args.get("output_dir"):
        opts.extend(["--output-dir", str(args["output_dir"])])

    payload = _run_script(script_path, opts)
    return _format_tool_result("run_verification_repair_loop", payload)


def build_mcp_handoff_bundle(args: dict[str, Any]) -> dict[str, Any]:
    script_path = _script_path("workflows", "build_mcp_handoff_bundle.py")
    opts: list[str] = [
        _require_path(args, "resolved_blueprint"),
    ]

    if args.get("binding_report"):
        opts.extend(["--binding-report", str(args["binding_report"])])
    if args.get("output"):
        opts.extend(["--output", str(args["output"])])

    payload = _run_script(script_path, opts)
    return _format_tool_result("build_mcp_handoff_bundle", payload)


TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="unity_rag.extract_reference_layout",
        description="Extract a reference layout plan JSON from a reference image using the configured provider. Falls back to a local heuristic provider when no API key is available.",
        input_schema=_build_extract_reference_layout_schema(),
        handler=extract_reference_layout,
    ),
    ToolSpec(
        name="unity_rag.run_reference_to_resolved_blueprint",
        description="Run the full reference-image or reference-layout workflow through template generation, vector indexing, asset binding, and MCP handoff bundle creation.",
        input_schema=_build_run_reference_to_resolved_blueprint_schema(),
        handler=run_reference_to_resolved_blueprint,
    ),
    ToolSpec(
        name="unity_rag.run_verification_repair_loop",
        description="Compare a captured Unity screenshot against a reference image and produce a bounded repair handoff bundle.",
        input_schema=_build_run_verification_repair_loop_schema(),
        handler=run_verification_repair_loop,
    ),
    ToolSpec(
        name="unity_rag.build_mcp_handoff_bundle",
        description="Convert a resolved blueprint into a Unity MCP handoff bundle with validate, apply, and verify requests.",
        input_schema=_build_build_mcp_handoff_bundle_schema(),
        handler=build_mcp_handoff_bundle,
    ),
]

TOOL_BY_NAME = {tool.name: tool for tool in TOOLS}

