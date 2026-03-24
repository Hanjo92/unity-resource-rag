from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request

if __package__ in (None, ""):
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from pipeline.mcp.doctor import DEFAULT_UNITY_MCP_TIMEOUT_MS, DEFAULT_UNITY_MCP_URL, build_doctor_payload
    from pipeline.mcp.unity_http import UnityMcpHttpError, get_unity_http_client
    from pipeline.planner.extract_reference_layout import (
        DEFAULT_DETAIL,
        DEFAULT_MAX_IMAGE_DIM,
        DEFAULT_MODEL,
        ProviderConfig,
        inspect_provider_setup as inspect_provider_setup_config,
    )
else:
    from .doctor import DEFAULT_UNITY_MCP_TIMEOUT_MS, DEFAULT_UNITY_MCP_URL, build_doctor_payload
    from .unity_http import UnityMcpHttpError, get_unity_http_client
    from ..planner.extract_reference_layout import (
        DEFAULT_DETAIL,
        DEFAULT_MAX_IMAGE_DIM,
        DEFAULT_MODEL,
        ProviderConfig,
        inspect_provider_setup as inspect_provider_setup_config,
    )


REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = REPO_ROOT / "pipeline"
DEFAULT_CATALOG_RELATIVE_PATH = Path("Library/ResourceRag/resource_catalog.jsonl")
DEFAULT_DRAFT_OUTPUT_RELATIVE_PATH = Path("Library/ResourceRag/Drafts")
DEFAULT_UNITY_MCP_OPERATION_TIMEOUT_MS = 30000
DEFAULT_MENU_BRIDGE_REQUEST_RELATIVE_PATH = Path("Library/ResourceRag/Interop/menu_tool_request.json")
DEFAULT_MENU_BRIDGE_RESPONSE_RELATIVE_PATH = Path("Library/ResourceRag/Interop/menu_tool_response.json")
UNITY_RAG_MENU_BRIDGE_PATH = "Tools/Unity Resource RAG/Interop/대기 요청 실행"

PROVIDER_DESCRIPTION = (
    "Select the extraction provider. "
    "`auto`: recommended; automatically uses a gateway URL or detectable auth source. "
    "`openai`: uses an OpenAI API key or Codex OAuth. "
    "`gemini`: uses a Google API key. "
    "`antigravity`: uses Google OAuth or a gcloud token. "
    "`claude`: uses an Anthropic API key. "
    "`claude_code`: uses Claude Code credentials. "
    "`openai_compatible`: uses a custom OpenAI-compatible endpoint. "
    "`gateway`: uses the team/provider gateway. "
    "`local_heuristic`: fully local fallback."
)

ADVANCED_SETTING_SUFFIX = "Advanced setting. Most users can leave this blank and only use `provider=auto`."

CONNECTION_PRESET_DESCRIPTION = (
    "Preset for first-time connection setup. "
    "`recommended_auto`: recommended; automatically picks a detectable auth source. "
    "`codex_oauth`: connects OpenAI through Codex OAuth. "
    "`openai_api_key`: connects OpenAI with `OPENAI_API_KEY`. "
    "`gemini_api_key`: connects Gemini with `GEMINI_API_KEY` or `GOOGLE_API_KEY`. "
    "`google_oauth`: connects Google OAuth with `GOOGLE_OAUTH_ACCESS_TOKEN` or a gcloud token. "
    "`claude_api_key`: connects Claude with `ANTHROPIC_API_KEY`. "
    "`claude_code`: connects with `ANTHROPIC_AUTH_TOKEN` or Claude Code credentials. "
    "`custom_openai_compatible`: connects to a custom OpenAI-compatible endpoint. "
    "`offline_local`: only uses the local heuristic with no network access. "
    "When a preset is provided, it takes precedence over lower-level provider/auth inputs in the same category."
)

PROVIDER_ENUM = ["auto", "openai", "gemini", "antigravity", "claude", "claude_code", "openai_compatible", "gateway", "local_heuristic"]
DRAFT_TEMPLATE_MODE_ENUM = ["popup", "hud", "list"]
CONNECTION_PRESET_ENUM = [
    "recommended_auto",
    "codex_oauth",
    "openai_api_key",
    "gemini_api_key",
    "google_oauth",
    "claude_api_key",
    "claude_code",
    "custom_openai_compatible",
    "offline_local",
]

CONNECTION_PRESET_DEFAULTS: dict[str, dict[str, str]] = {
    "recommended_auto": {"provider": "auto"},
    "codex_oauth": {"provider": "openai", "auth_mode": "oauth_token"},
    "openai_api_key": {"provider": "openai", "auth_mode": "api_key"},
    "gemini_api_key": {"provider": "gemini", "auth_mode": "api_key"},
    "google_oauth": {"provider": "antigravity", "auth_mode": "oauth_token"},
    "claude_api_key": {"provider": "claude", "auth_mode": "api_key"},
    "claude_code": {"provider": "claude_code", "auth_mode": "oauth_token"},
    "custom_openai_compatible": {"provider": "openai_compatible", "auth_mode": "api_key"},
    "offline_local": {"provider": "local_heuristic"},
}
CONNECTION_PRESET_CLEAR_FIELDS: dict[str, tuple[str, ...]] = {
    "codex_oauth": ("oauth_token_env", "oauth_token_file", "oauth_token_command"),
    "openai_api_key": ("oauth_token_env", "oauth_token_file", "oauth_token_command", "codex_auth_file"),
    "gemini_api_key": ("oauth_token_env", "oauth_token_file", "oauth_token_command", "codex_auth_file"),
    "google_oauth": ("codex_auth_file",),
    "claude_api_key": ("oauth_token_env", "oauth_token_file", "oauth_token_command", "codex_auth_file"),
    "claude_code": ("codex_auth_file",),
    "custom_openai_compatible": ("oauth_token_env", "oauth_token_file", "oauth_token_command", "codex_auth_file"),
    "offline_local": ("auth_mode", "oauth_token_env", "oauth_token_file", "oauth_token_command", "codex_auth_file"),
}


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
        error_message = stderr or payload.get("error") or stdout or f"Command failed with exit code {completed.returncode}."
        raise ToolExecutionError(
            error_message,
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


def _advanced_description(base: str) -> str:
    return f"{base} {ADVANCED_SETTING_SUFFIX}"


CUSTOM_BASE_URL_DESCRIPTION = _advanced_description("Custom OpenAI-compatible endpoint or base URL override.")
API_KEY_ENV_DESCRIPTION = _advanced_description("Environment variable name used to read the API key.")
AUTH_MODE_DESCRIPTION = _advanced_description("Authentication mode for API-backed providers.")
OAUTH_TOKEN_ENV_DESCRIPTION = _advanced_description("Environment variable name used to read the OAuth bearer token.")
OAUTH_TOKEN_FILE_DESCRIPTION = _advanced_description("File path containing the OAuth bearer token.")
OAUTH_TOKEN_COMMAND_DESCRIPTION = _advanced_description("Command that prints an OAuth bearer token to stdout.")
CODEX_AUTH_FILE_DESCRIPTION = _advanced_description("Path to the Codex OAuth auth.json file.")
GATEWAY_AUTH_TOKEN_ENV_DESCRIPTION = _advanced_description("Environment variable name used to read the gateway bearer token.")


def _apply_connection_preset(args: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(args)
    preset = normalized.get("connection_preset")
    if not preset:
        return normalized

    defaults = CONNECTION_PRESET_DEFAULTS.get(str(preset))
    if defaults is None:
        raise ToolExecutionError(f"Unsupported connection_preset: {preset}.")

    normalized.update(defaults)
    for field in CONNECTION_PRESET_CLEAR_FIELDS.get(str(preset), ()):
        normalized.pop(field, None)
    return normalized


def _build_extract_reference_layout_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "image": {"type": "string", "description": "Path to the reference image."},
            "output": {"type": "string", "description": "Optional output path for the reference layout JSON."},
            "report": {"type": "string", "description": "Optional output path for the extraction report JSON."},
            "screen_name": {"type": "string"},
            "connection_preset": {"type": "string", "enum": CONNECTION_PRESET_ENUM, "description": CONNECTION_PRESET_DESCRIPTION},
            "provider": {"type": "string", "enum": PROVIDER_ENUM, "description": PROVIDER_DESCRIPTION},
            "provider_base_url": {"type": "string", "description": CUSTOM_BASE_URL_DESCRIPTION},
            "provider_api_key_env": {"type": "string", "description": API_KEY_ENV_DESCRIPTION},
            "auth_mode": {"type": "string", "enum": ["api_key", "oauth_token"], "description": AUTH_MODE_DESCRIPTION},
            "oauth_token_env": {"type": "string", "description": OAUTH_TOKEN_ENV_DESCRIPTION},
            "oauth_token_file": {"type": "string", "description": OAUTH_TOKEN_FILE_DESCRIPTION},
            "oauth_token_command": {"type": "string", "description": OAUTH_TOKEN_COMMAND_DESCRIPTION},
            "codex_auth_file": {"type": "string", "description": CODEX_AUTH_FILE_DESCRIPTION},
            "gateway_url": {"type": "string", "description": _advanced_description("Gateway base URL.")},
            "gateway_auth_token_env": {"type": "string", "description": GATEWAY_AUTH_TOKEN_ENV_DESCRIPTION},
            "gateway_timeout_ms": {"type": "integer", "minimum": 1, "description": _advanced_description("Gateway request timeout in milliseconds.")},
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
            "connection_preset": {"type": "string", "enum": CONNECTION_PRESET_ENUM, "description": CONNECTION_PRESET_DESCRIPTION},
            "provider": {"type": "string", "enum": PROVIDER_ENUM, "description": PROVIDER_DESCRIPTION},
            "provider_base_url": {"type": "string", "description": CUSTOM_BASE_URL_DESCRIPTION},
            "provider_api_key_env": {"type": "string", "description": API_KEY_ENV_DESCRIPTION},
            "auth_mode": {"type": "string", "enum": ["api_key", "oauth_token"], "description": AUTH_MODE_DESCRIPTION},
            "oauth_token_env": {"type": "string", "description": OAUTH_TOKEN_ENV_DESCRIPTION},
            "oauth_token_file": {"type": "string", "description": OAUTH_TOKEN_FILE_DESCRIPTION},
            "oauth_token_command": {"type": "string", "description": OAUTH_TOKEN_COMMAND_DESCRIPTION},
            "codex_auth_file": {"type": "string", "description": CODEX_AUTH_FILE_DESCRIPTION},
            "gateway_url": {"type": "string", "description": _advanced_description("Gateway base URL.")},
            "gateway_auth_token_env": {"type": "string", "description": GATEWAY_AUTH_TOKEN_ENV_DESCRIPTION},
            "gateway_timeout_ms": {"type": "integer", "minimum": 1, "description": _advanced_description("Gateway request timeout in milliseconds.")},
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


def _build_inspect_provider_setup_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "connection_preset": {"type": "string", "enum": CONNECTION_PRESET_ENUM, "description": CONNECTION_PRESET_DESCRIPTION},
            "provider": {"type": "string", "enum": PROVIDER_ENUM, "description": PROVIDER_DESCRIPTION},
            "provider_base_url": {"type": "string", "description": CUSTOM_BASE_URL_DESCRIPTION},
            "provider_api_key_env": {"type": "string", "description": API_KEY_ENV_DESCRIPTION},
            "auth_mode": {"type": "string", "enum": ["api_key", "oauth_token"], "description": AUTH_MODE_DESCRIPTION},
            "oauth_token_env": {"type": "string", "description": OAUTH_TOKEN_ENV_DESCRIPTION},
            "oauth_token_file": {"type": "string", "description": OAUTH_TOKEN_FILE_DESCRIPTION},
            "oauth_token_command": {"type": "string", "description": OAUTH_TOKEN_COMMAND_DESCRIPTION},
            "codex_auth_file": {"type": "string", "description": CODEX_AUTH_FILE_DESCRIPTION},
            "gateway_url": {"type": "string", "description": _advanced_description("Gateway base URL.")},
            "gateway_auth_token_env": {"type": "string", "description": GATEWAY_AUTH_TOKEN_ENV_DESCRIPTION},
            "gateway_timeout_ms": {"type": "integer", "minimum": 1, "description": _advanced_description("Gateway request timeout in milliseconds.")},
        },
        "additionalProperties": False,
    }


def _build_doctor_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "unity_project_path": {"type": "string", "description": "Unity project root path. When provided, the default catalog path is also checked."},
            "catalog": {"type": "string", "description": "Path to resource_catalog.jsonl. Relative paths are allowed when `unity_project_path` is set."},
            "reference_image": {"type": "string", "description": "Optional reference image path."},
            "resolved_blueprint": {"type": "string", "description": "Optional resolved blueprint JSON path."},
            "unity_mcp_url": {"type": "string", "description": "Unity MCP HTTP Local URL. If omitted and `unity_project_path` is provided, `http://127.0.0.1:8080/mcp` is assumed."},
            "unity_mcp_timeout_ms": {"type": "integer", "minimum": 1, "description": "Unity MCP HTTP Local probe timeout in milliseconds."},
            "connection_preset": {"type": "string", "enum": CONNECTION_PRESET_ENUM, "description": CONNECTION_PRESET_DESCRIPTION},
            "provider": {"type": "string", "enum": PROVIDER_ENUM, "description": PROVIDER_DESCRIPTION},
            "provider_base_url": {"type": "string", "description": CUSTOM_BASE_URL_DESCRIPTION},
            "provider_api_key_env": {"type": "string", "description": API_KEY_ENV_DESCRIPTION},
            "auth_mode": {"type": "string", "enum": ["api_key", "oauth_token"], "description": AUTH_MODE_DESCRIPTION},
            "oauth_token_env": {"type": "string", "description": OAUTH_TOKEN_ENV_DESCRIPTION},
            "oauth_token_file": {"type": "string", "description": OAUTH_TOKEN_FILE_DESCRIPTION},
            "oauth_token_command": {"type": "string", "description": OAUTH_TOKEN_COMMAND_DESCRIPTION},
            "codex_auth_file": {"type": "string", "description": CODEX_AUTH_FILE_DESCRIPTION},
            "gateway_url": {"type": "string", "description": _advanced_description("Gateway base URL.")},
            "gateway_auth_token_env": {"type": "string", "description": GATEWAY_AUTH_TOKEN_ENV_DESCRIPTION},
            "gateway_timeout_ms": {"type": "integer", "minimum": 1, "description": _advanced_description("Gateway request timeout in milliseconds.")},
        },
        "additionalProperties": False,
    }


def _build_run_first_pass_ui_build_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "image": {"type": "string", "description": "Path to the reference image."},
            "reference_layout": {"type": "string", "description": "Existing reference layout JSON. Use this instead of image when already extracted."},
            "unity_project_path": {"type": "string", "description": "Unity project root. Used to infer the default catalog path and validate local setup."},
            "catalog": {"type": "string", "description": "Path to resource_catalog.jsonl. If omitted and unity_project_path is set, defaults to Library/ResourceRag/resource_catalog.jsonl."},
            "vector_index": {"type": "string"},
            "output_dir": {"type": "string"},
            "screen_name": {"type": "string"},
            "unity_mcp_url": {"type": "string", "description": "Unity MCP HTTP Local URL. Defaults to http://127.0.0.1:8080/mcp when Unity apply/index is enabled."},
            "unity_mcp_timeout_ms": {"type": "integer", "minimum": 1, "description": "Unity MCP HTTP Local timeout in milliseconds."},
            "force_reindex": {"type": "boolean", "description": "Force re-running index_project_resources before binding."},
            "apply_in_unity": {"type": "boolean", "description": "When true, validate/apply the generated blueprint in Unity MCP.", "default": True},
            "validate_before_apply": {"type": "boolean", "description": "When true, call apply_ui_blueprint validate before apply.", "default": True},
            "connection_preset": {"type": "string", "enum": CONNECTION_PRESET_ENUM, "description": CONNECTION_PRESET_DESCRIPTION},
            "provider": {"type": "string", "enum": PROVIDER_ENUM, "description": PROVIDER_DESCRIPTION},
            "provider_base_url": {"type": "string", "description": CUSTOM_BASE_URL_DESCRIPTION},
            "provider_api_key_env": {"type": "string", "description": API_KEY_ENV_DESCRIPTION},
            "auth_mode": {"type": "string", "enum": ["api_key", "oauth_token"], "description": AUTH_MODE_DESCRIPTION},
            "oauth_token_env": {"type": "string", "description": OAUTH_TOKEN_ENV_DESCRIPTION},
            "oauth_token_file": {"type": "string", "description": OAUTH_TOKEN_FILE_DESCRIPTION},
            "oauth_token_command": {"type": "string", "description": OAUTH_TOKEN_COMMAND_DESCRIPTION},
            "codex_auth_file": {"type": "string", "description": CODEX_AUTH_FILE_DESCRIPTION},
            "gateway_url": {"type": "string", "description": _advanced_description("Gateway base URL.")},
            "gateway_auth_token_env": {"type": "string", "description": GATEWAY_AUTH_TOKEN_ENV_DESCRIPTION},
            "gateway_timeout_ms": {"type": "integer", "minimum": 1, "description": _advanced_description("Gateway request timeout in milliseconds.")},
            "model": {"type": "string"},
            "detail": {"type": "string", "enum": ["low", "high", "auto"]},
            "max_image_dim": {"type": "integer", "minimum": 1},
            "hint": {"type": "array", "items": {"type": "string"}},
            "safe_area_component_type": {"type": "string"},
            "safe_area_properties": {"type": "string"},
            "allow_partial": {"type": "boolean"},
        },
        "anyOf": [
            {"required": ["image"]},
            {"required": ["reference_layout"]},
        ],
        "additionalProperties": False,
    }


def _build_run_catalog_draft_ui_build_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "Short description of the UI you want to draft. Used for catalog search and fallback copy."},
            "template_mode": {"type": "string", "enum": DRAFT_TEMPLATE_MODE_ENUM, "description": "Catalog-first draft template. One of `popup`, `hud`, or `list`."},
            "screen_name": {"type": "string", "description": "Screen name used for the output blueprint and Canvas name. Defaults to `CatalogDraft`."},
            "title": {"type": "string", "description": "Header text. Defaults to `goal` when omitted."},
            "subtitle": {"type": "string", "description": "Optional subtitle."},
            "body": {"type": "string", "description": "Optional body copy. Defaults to `goal` when omitted."},
            "price_text": {"type": "string", "description": "Optional price or highlight text."},
            "primary_action_label": {"type": "string", "description": "Optional primary action label."},
            "secondary_action_label": {"type": "string", "description": "Optional secondary action label."},
            "shell_query": {"type": "string", "description": "Override query used to find shell or prefab candidates."},
            "panel_query": {"type": "string", "description": "Override query used to find background panel sprite candidates."},
            "featured_asset_query": {"type": "string", "description": "Override query used to find featured icon or sprite candidates."},
            "title_font_query": {"type": "string", "description": "Override query used to find title TMP font candidates."},
            "body_font_query": {"type": "string", "description": "Override query used to find body TMP font candidates."},
            "unity_project_path": {"type": "string", "description": "Unity project root. Used to infer the default catalog path and local draft output path."},
            "catalog": {"type": "string", "description": "Path to resource_catalog.jsonl. If omitted and unity_project_path is set, defaults to Library/ResourceRag/resource_catalog.jsonl."},
            "vector_index": {"type": "string", "description": "Optional resource_vector_index.json path for richer catalog search scoring."},
            "output_dir": {"type": "string", "description": "Optional output directory for the generated draft blueprint and search report."},
            "unity_mcp_url": {"type": "string", "description": "Unity MCP HTTP Local URL. Defaults to http://127.0.0.1:8080/mcp when Unity apply/index is enabled."},
            "unity_mcp_timeout_ms": {"type": "integer", "minimum": 1, "description": "Unity MCP HTTP Local timeout in milliseconds."},
            "force_reindex": {"type": "boolean", "description": "Force re-running index_project_resources before generating the draft."},
            "apply_in_unity": {"type": "boolean", "description": "When true, validate/apply the generated blueprint in Unity MCP.", "default": True},
            "validate_before_apply": {"type": "boolean", "description": "When true, call apply_ui_blueprint validate before apply.", "default": True},
        },
        "required": ["goal"],
        "additionalProperties": False,
    }


def _build_start_ui_build_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "image": {"type": "string", "description": "Path to the reference image. When provided, the reference-first path is selected."},
            "reference_layout": {"type": "string", "description": "Existing reference layout JSON. Can force the reference-first path even without `image`."},
            "goal": {"type": "string", "description": "UI goal used for the catalog-first draft path when no reference is provided."},
            "template_mode": {"type": "string", "enum": DRAFT_TEMPLATE_MODE_ENUM, "description": "Catalog-first draft template used when no reference is provided."},
            "screen_name": {"type": "string"},
            "title": {"type": "string"},
            "subtitle": {"type": "string"},
            "body": {"type": "string"},
            "price_text": {"type": "string"},
            "primary_action_label": {"type": "string"},
            "secondary_action_label": {"type": "string"},
            "shell_query": {"type": "string"},
            "panel_query": {"type": "string"},
            "featured_asset_query": {"type": "string"},
            "title_font_query": {"type": "string"},
            "body_font_query": {"type": "string"},
            "unity_project_path": {"type": "string", "description": "Unity project root. Used to infer the default catalog path and local setup checks."},
            "catalog": {"type": "string", "description": "Path to resource_catalog.jsonl. If omitted and unity_project_path is set, defaults to Library/ResourceRag/resource_catalog.jsonl."},
            "vector_index": {"type": "string"},
            "output_dir": {"type": "string"},
            "unity_mcp_url": {"type": "string", "description": "Unity MCP HTTP Local URL. Defaults to http://127.0.0.1:8080/mcp when Unity apply/index is enabled."},
            "unity_mcp_timeout_ms": {"type": "integer", "minimum": 1, "description": "Unity MCP HTTP Local timeout in milliseconds."},
            "force_reindex": {"type": "boolean"},
            "apply_in_unity": {"type": "boolean", "default": True},
            "validate_before_apply": {"type": "boolean", "default": True},
            "run_doctor": {"type": "boolean", "description": "Whether to run doctor diagnostics before starting the UI build.", "default": True},
            "require_doctor_ok": {"type": "boolean", "description": "Whether to stop the build when doctor returns `error`.", "default": True},
            "connection_preset": {"type": "string", "enum": CONNECTION_PRESET_ENUM, "description": CONNECTION_PRESET_DESCRIPTION},
            "provider": {"type": "string", "enum": PROVIDER_ENUM, "description": PROVIDER_DESCRIPTION},
            "provider_base_url": {"type": "string", "description": CUSTOM_BASE_URL_DESCRIPTION},
            "provider_api_key_env": {"type": "string", "description": API_KEY_ENV_DESCRIPTION},
            "auth_mode": {"type": "string", "enum": ["api_key", "oauth_token"], "description": AUTH_MODE_DESCRIPTION},
            "oauth_token_env": {"type": "string", "description": OAUTH_TOKEN_ENV_DESCRIPTION},
            "oauth_token_file": {"type": "string", "description": OAUTH_TOKEN_FILE_DESCRIPTION},
            "oauth_token_command": {"type": "string", "description": OAUTH_TOKEN_COMMAND_DESCRIPTION},
            "codex_auth_file": {"type": "string", "description": CODEX_AUTH_FILE_DESCRIPTION},
            "gateway_url": {"type": "string", "description": _advanced_description("Gateway base URL.")},
            "gateway_auth_token_env": {"type": "string", "description": GATEWAY_AUTH_TOKEN_ENV_DESCRIPTION},
            "gateway_timeout_ms": {"type": "integer", "minimum": 1, "description": _advanced_description("Gateway request timeout in milliseconds.")},
            "model": {"type": "string"},
            "detail": {"type": "string", "enum": ["low", "high", "auto"]},
            "max_image_dim": {"type": "integer", "minimum": 1},
            "hint": {"type": "array", "items": {"type": "string"}},
            "safe_area_component_type": {"type": "string"},
            "safe_area_properties": {"type": "string"},
            "allow_partial": {"type": "boolean"},
        },
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


def _format_inspection_summary(payload: dict[str, Any]) -> str:
    missing_settings = payload.get("missingSettings") or ["None"]
    next_actions = payload.get("nextActions") or ["None"]
    return "\n".join([
        f"Recommended choice: {payload['recommendedChoice']}",
        f"Resolved provider: {payload['resolvedProvider']}",
        f"Token source: {payload['tokenSourceSummary']}",
        "Missing settings:",
        *[f"- {item}" for item in missing_settings],
        "Next actions:",
        *[f"- {item}" for item in next_actions],
    ])


def _format_doctor_summary(payload: dict[str, Any]) -> str:
    lines = [f"overall: {payload['overallStatus']}"]
    for check in payload.get("checks") or []:
        lines.append(f"- [{check['status']}] {check['key']}: {check['summary']}")
    next_actions = payload.get("nextActions") or []
    if next_actions:
        lines.append("next actions:")
        lines.extend(f"- {item}" for item in next_actions)
    return "\n".join(lines)


def _extract_wrapped_payload(result: dict[str, Any]) -> dict[str, Any]:
    content = result.get("content") or []
    if not isinstance(content, list) or not content:
        return {}
    raw = content[0].get("text")
    if not isinstance(raw, str):
        return {}
    parsed = json.loads(raw)
    if isinstance(parsed, dict) and isinstance(parsed.get("payload"), dict):
        return parsed["payload"]
    if isinstance(parsed, dict):
        return parsed
    return {}


def _resolve_optional_path(raw: Any) -> Path | None:
    if raw in (None, ""):
        return None
    return Path(str(raw)).expanduser().resolve()


def _resolve_catalog_path(raw_catalog: Any, unity_project_path: Path | None) -> Path | None:
    if raw_catalog not in (None, ""):
        catalog_path = Path(str(raw_catalog)).expanduser()
        if unity_project_path is not None and not catalog_path.is_absolute():
            return (unity_project_path / catalog_path).resolve()
        return catalog_path.resolve()
    if unity_project_path is None:
        return None
    return (unity_project_path / DEFAULT_CATALOG_RELATIVE_PATH).resolve()


def _resolve_path_against_project(raw_path: Any, unity_project_path: Path | None) -> Path | None:
    if raw_path in (None, ""):
        return None
    path = Path(str(raw_path)).expanduser()
    if unity_project_path is not None and not path.is_absolute():
        return (unity_project_path / path).resolve()
    return path.resolve()


def _slugify(value: str) -> str:
    collapsed = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
    return collapsed or "catalog-draft"


def _default_catalog_draft_output_dir(screen_name: str, unity_project_path: Path | None, catalog_path: Path) -> Path:
    slug = _slugify(screen_name)
    if unity_project_path is not None:
        return (unity_project_path / DEFAULT_DRAFT_OUTPUT_RELATIVE_PATH / slug).resolve()
    return (catalog_path.parent / "drafts" / slug).resolve()


def _load_jsonl_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ToolExecutionError(
                    f"Failed to parse catalog JSONL at line {index}.",
                    details={"catalogPath": str(path), "lineNumber": index},
                ) from exc
            if isinstance(parsed, dict):
                records.append(parsed)
    return records


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _search_catalog_records(
    catalog_path: Path,
    query_text: str,
    *,
    preferred_kind: str | None = None,
    region_type: str | None = None,
    aspect_ratio: float | None = None,
    vector_index_path: Path | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    args = [
        str(catalog_path),
        "--query",
        query_text,
        "--top-k",
        str(max(1, top_k)),
    ]
    if region_type:
        args.extend(["--region-type", region_type])
    if preferred_kind:
        args.extend(["--preferred-kind", preferred_kind])
    if aspect_ratio is not None:
        args.extend(["--aspect-ratio", str(aspect_ratio)])
    if vector_index_path is not None:
        args.extend(["--vector-index", str(vector_index_path)])
    return _run_script(_script_path("retrieval", "search_catalog.py"), args)


def _candidate_from_record(record: dict[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "guid": record.get("guid"),
        "localFileId": record.get("localFileId"),
        "subAssetName": record.get("subAssetName"),
        "score": 0.0,
        "path": record.get("path"),
        "name": record.get("name"),
        "assetType": record.get("assetType"),
        "binding": record.get("binding", {}),
        "semanticText": record.get("semanticText"),
        "scoreBreakdown": {},
        "reasons": [reason],
    }


def _candidate_score(candidate: dict[str, Any] | None) -> float:
    if not isinstance(candidate, dict):
        return 0.0
    try:
        return float(candidate.get("score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _candidate_asset_type(record: dict[str, Any] | None, candidate: dict[str, Any] | None) -> str:
    asset_type = ""
    if isinstance(record, dict):
        asset_type = str(record.get("assetType") or "")
    if not asset_type and isinstance(candidate, dict):
        asset_type = str(candidate.get("assetType") or "")
    return asset_type.lower()


def _candidate_binding_kind(record: dict[str, Any] | None, candidate: dict[str, Any] | None) -> str:
    binding_kind = ""
    if isinstance(record, dict):
        binding_kind = str(((record.get("binding") or {}).get("kind")) or "")
    if not binding_kind and isinstance(candidate, dict):
        binding_kind = str(((candidate.get("binding") or {}).get("kind")) or "")
    return binding_kind.lower()


def _candidate_semantic_blob(record: dict[str, Any] | None, candidate: dict[str, Any] | None) -> str:
    parts: list[str] = []
    for source in (record, candidate):
        if not isinstance(source, dict):
            continue
        for key in ("semanticText", "name", "path", "subAssetName"):
            value = source.get(key)
            if value:
                parts.append(str(value))
        binding = source.get("binding") or {}
        if isinstance(binding, dict):
            for key in ("kind", "unityLoadPath", "subAssetName"):
                value = binding.get(key)
                if value:
                    parts.append(str(value))
    return " ".join(parts).lower()


def _select_catalog_candidate(
    search_payload: dict[str, Any],
    records_by_id: dict[str, dict[str, Any]],
    *,
    asset_types: tuple[str, ...] = (),
    binding_kinds: tuple[str, ...] = (),
    semantic_terms: tuple[str, ...] = (),
    min_score: float | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    results = search_payload.get("results") or []
    for candidate in results:
        if not isinstance(candidate, dict):
            continue
        record = records_by_id.get(str(candidate.get("id")))
        asset_type = _candidate_asset_type(record, candidate)
        binding_kind = _candidate_binding_kind(record, candidate)
        if asset_types and asset_type not in {value.lower() for value in asset_types}:
            continue
        if binding_kinds and binding_kind not in {value.lower() for value in binding_kinds}:
            continue
        semantic_blob = _candidate_semantic_blob(record, candidate)
        if semantic_terms and any(term.lower() in semantic_blob for term in semantic_terms):
            return candidate, record
        if min_score is not None and _candidate_score(candidate) >= min_score:
            return candidate, record
        if not semantic_terms and min_score is None:
            return candidate, record
    return None, None


def _fallback_catalog_record(
    records: list[dict[str, Any]],
    *,
    asset_types: tuple[str, ...] = (),
    binding_kinds: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    normalized_asset_types = {value.lower() for value in asset_types}
    normalized_binding_kinds = {value.lower() for value in binding_kinds}
    for record in records:
        asset_type = _candidate_asset_type(record, None)
        binding_kind = _candidate_binding_kind(record, None)
        if normalized_asset_types and asset_type not in normalized_asset_types:
            continue
        if normalized_binding_kinds and binding_kind not in normalized_binding_kinds:
            continue
        return record
    return None


def _asset_reference_from_candidate(
    candidate: dict[str, Any] | None,
    record: dict[str, Any] | None,
    *,
    forced_kind: str | None = None,
) -> dict[str, Any] | None:
    if not isinstance(candidate, dict) and not isinstance(record, dict):
        return None

    reference = {
        "kind": forced_kind or _candidate_binding_kind(record, candidate),
        "path": (candidate or {}).get("path") or (record or {}).get("path"),
        "guid": (candidate or {}).get("guid") or (record or {}).get("guid"),
        "localFileId": (candidate or {}).get("localFileId") or (record or {}).get("localFileId"),
        "subAssetName": (candidate or {}).get("subAssetName") or (record or {}).get("subAssetName"),
    }
    filtered = {
        key: value
        for key, value in reference.items()
        if value not in (None, "", 0)
    }
    return filtered or None


def _dedupe_strings(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _full_stretch_rect() -> dict[str, Any]:
    return {
        "anchorMin": {"x": 0, "y": 0},
        "anchorMax": {"x": 1, "y": 1},
        "offsetMin": {"x": 0, "y": 0},
        "offsetMax": {"x": 0, "y": 0},
    }


def _center_rect(width: float, height: float, *, x: float = 0, y: float = 0) -> dict[str, Any]:
    return {
        "anchorMin": {"x": 0.5, "y": 0.5},
        "anchorMax": {"x": 0.5, "y": 0.5},
        "pivot": {"x": 0.5, "y": 0.5},
        "anchoredPosition": {"x": x, "y": y},
        "sizeDelta": {"x": width, "y": height},
    }


def _make_tmp_text_node(
    *,
    node_id: str,
    name: str,
    value: str,
    width: float,
    height: float,
    x: float = 0,
    y: float,
    font_size: int,
    color: str,
    font_asset: dict[str, Any] | None,
    alignment: str = "Center",
) -> dict[str, Any]:
    text_spec: dict[str, Any] = {
        "value": value,
        "fontSize": font_size,
        "alignment": alignment,
        "enableAutoSizing": False,
        "raycastTarget": False,
        "color": color,
    }
    if font_asset:
        text_spec["fontAsset"] = font_asset
    return {
        "id": node_id,
        "name": name,
        "kind": "tmp_text",
        "text": text_spec,
        "rect": _center_rect(width, height, x=x, y=y),
    }


def _normalize_draft_template_mode(value: Any) -> str:
    normalized = str(value or "popup").strip().lower() or "popup"
    if normalized not in DRAFT_TEMPLATE_MODE_ENUM:
        raise ToolExecutionError(
            f"Unsupported template_mode: {value}.",
            details={"allowedTemplateModes": DRAFT_TEMPLATE_MODE_ENUM},
        )
    return normalized


def _catalog_draft_query_defaults(template_mode: str, goal: str) -> dict[str, str]:
    if template_mode == "hud":
        return {
            "shell": f"{goal} hud overlay top bar heads up display shell",
            "panel": f"{goal} hud bar overlay panel background",
            "featured": f"{goal} status resource icon badge",
            "title_font": f"{goal} hud title heading font",
            "body_font": f"{goal} readable hud label font",
        }
    if template_mode == "list":
        return {
            "shell": f"{goal} inventory shop list panel window shell",
            "panel": f"{goal} inventory list card row panel background",
            "featured": f"{goal} inventory item icon",
            "title_font": f"{goal} inventory list title font",
            "body_font": f"{goal} readable inventory list body font",
        }
    return {
        "shell": f"{goal} popup modal dialog window shell",
        "panel": f"{goal} popup panel frame background",
        "featured": f"{goal} reward item icon",
        "title_font": f"{goal} ui title heading font",
        "body_font": f"{goal} readable ui body font",
    }


def _catalog_draft_semantic_terms(template_mode: str) -> dict[str, tuple[str, ...]]:
    if template_mode == "hud":
        return {
            "shell": ("hud", "overlay", "bar", "status", "top"),
            "panel": ("hud", "overlay", "bar", "panel", "status"),
            "featured": ("icon", "status", "resource", "currency", "badge"),
        }
    if template_mode == "list":
        return {
            "shell": ("list", "inventory", "shop", "panel", "window"),
            "panel": ("list", "inventory", "card", "row", "panel"),
            "featured": ("icon", "item", "inventory", "reward", "shop"),
        }
    return {
        "shell": ("popup", "panel", "dialog", "window", "modal"),
        "panel": ("popup", "panel", "frame", "window", "modal"),
        "featured": ("icon", "reward", "badge", "item"),
    }


def _make_draft_image_node(
    *,
    node_id: str,
    name: str,
    asset: dict[str, Any],
    width: float,
    height: float,
    x: float = 0,
    y: float = 0,
    preserve_aspect: bool = True,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "name": name,
        "kind": "image",
        "asset": asset,
        "image": {
            "type": "Simple",
            "preserveAspect": preserve_aspect,
            "raycastTarget": False,
            "color": "#FFFFFFFF",
        },
        "rect": _center_rect(width, height, x=x, y=y),
    }


def _wrap_catalog_draft_shell(
    *,
    overlay_root: dict[str, Any],
    shell_prefab_asset: dict[str, Any] | None,
    panel_sprite_asset: dict[str, Any] | None,
    panel_is_nine_slice: bool,
    width: float,
    height: float,
    y: float = 0,
) -> tuple[dict[str, Any], str]:
    shell_source_mode = "bare_container"
    if shell_prefab_asset:
        shell_source_mode = "shell_prefab"
        shell_node: dict[str, Any] = {
            "id": "draft_shell_prefab",
            "name": "DraftShellPrefab",
            "kind": "prefab_instance",
            "asset": shell_prefab_asset,
            "children": [overlay_root],
        }
    elif panel_sprite_asset:
        shell_source_mode = "panel_sprite"
        shell_node = {
            "id": "draft_panel_sprite",
            "name": "DraftPanelSprite",
            "kind": "image",
            "asset": panel_sprite_asset,
            "image": {
                "type": "Sliced" if panel_is_nine_slice else "Simple",
                "preserveAspect": False,
                "raycastTarget": False,
                "color": "#FFFFFFFF",
            },
            "rect": _center_rect(width, height, y=y),
            "children": [overlay_root],
        }
    else:
        shell_node = {
            "id": "draft_panel_container",
            "name": "DraftPanelContainer",
            "kind": "container",
            "rect": _center_rect(width, height, y=y),
            "children": [overlay_root],
        }
    return shell_node, shell_source_mode


def _build_popup_catalog_draft_blueprint(
    *,
    title: str,
    subtitle: str | None,
    body: str,
    price_text: str | None,
    primary_action_label: str | None,
    secondary_action_label: str | None,
    featured_sprite_asset: dict[str, Any] | None,
    title_font_asset: dict[str, Any] | None,
    body_font_asset: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], float, float, float]:
    overlay_children: list[dict[str, Any]] = [
        _make_tmp_text_node(
            node_id="draft_title",
            name="DraftTitle",
            value=title,
            width=620,
            height=60,
            y=248,
            font_size=42,
            color="#F7E9AEFF",
            font_asset=title_font_asset,
        )
    ]

    if subtitle:
        overlay_children.append(
            _make_tmp_text_node(
                node_id="draft_subtitle",
                name="DraftSubtitle",
                value=subtitle,
                width=700,
                height=34,
                y=206,
                font_size=20,
                color="#C9D3DAFF",
                font_asset=body_font_asset,
            )
        )

    body_y = -24
    if featured_sprite_asset:
        overlay_children.append(
            _make_draft_image_node(
                node_id="draft_featured_icon",
                name="DraftFeaturedIcon",
                asset=featured_sprite_asset,
                width=148,
                height=148,
                y=88,
            )
        )
        body_y = -102

    overlay_children.append(
        _make_tmp_text_node(
            node_id="draft_body",
            name="DraftBody",
            value=body,
            width=680,
            height=96,
            y=body_y,
            font_size=22,
            color="#DCE4EAFF",
            font_asset=body_font_asset,
        )
    )

    footer_y = -224 if featured_sprite_asset else -188
    if price_text:
        overlay_children.extend(
            [
                _make_tmp_text_node(
                    node_id="draft_price_caption",
                    name="DraftPriceCaption",
                    value="PRICE",
                    width=160,
                    height=28,
                    y=footer_y,
                    font_size=18,
                    color="#9FB2C1FF",
                    font_asset=body_font_asset,
                ),
                _make_tmp_text_node(
                    node_id="draft_price_value",
                    name="DraftPriceValue",
                    value=price_text,
                    width=320,
                    height=40,
                    y=footer_y - 34,
                    font_size=28,
                    color="#8CE0A7FF",
                    font_asset=title_font_asset or body_font_asset,
                ),
            ]
        )

    button_y = -320 if featured_sprite_asset else -286
    if primary_action_label:
        overlay_children.append(
            _make_tmp_text_node(
                node_id="draft_primary_action",
                name="DraftPrimaryActionLabel",
                value=primary_action_label,
                width=220,
                height=36,
                x=-110,
                y=button_y,
                font_size=24,
                color="#FFFFFFFF",
                font_asset=title_font_asset or body_font_asset,
            )
        )
    if secondary_action_label:
        overlay_children.append(
            _make_tmp_text_node(
                node_id="draft_secondary_action",
                name="DraftSecondaryActionLabel",
                value=secondary_action_label,
                width=220,
                height=36,
                x=110,
                y=button_y,
                font_size=24,
                color="#FFFFFFFF",
                font_asset=title_font_asset or body_font_asset,
            )
        )
    return overlay_children, 920, 640, 0


def _build_hud_catalog_draft_blueprint(
    *,
    title: str,
    subtitle: str | None,
    body: str,
    price_text: str | None,
    primary_action_label: str | None,
    secondary_action_label: str | None,
    featured_sprite_asset: dict[str, Any] | None,
    title_font_asset: dict[str, Any] | None,
    body_font_asset: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], float, float, float]:
    overlay_children: list[dict[str, Any]] = [
        _make_tmp_text_node(
            node_id="draft_title",
            name="DraftTitle",
            value=title,
            width=520,
            height=48,
            x=-420,
            y=28,
            font_size=34,
            color="#F7E9AEFF",
            font_asset=title_font_asset,
            alignment="Left",
        ),
        _make_tmp_text_node(
            node_id="draft_body",
            name="DraftBody",
            value=body,
            width=620,
            height=32,
            x=-370,
            y=-24,
            font_size=20,
            color="#DCE4EAFF",
            font_asset=body_font_asset,
            alignment="Left",
        ),
    ]

    if subtitle:
        overlay_children.append(
            _make_tmp_text_node(
                node_id="draft_subtitle",
                name="DraftSubtitle",
                value=subtitle,
                width=520,
                height=24,
                x=-420,
                y=2,
                font_size=18,
                color="#9FB2C1FF",
                font_asset=body_font_asset,
                alignment="Left",
            )
        )

    if featured_sprite_asset:
        overlay_children.append(
            _make_draft_image_node(
                node_id="draft_featured_icon",
                name="DraftFeaturedIcon",
                asset=featured_sprite_asset,
                width=96,
                height=96,
                x=548,
                y=0,
            )
        )

    if price_text:
        overlay_children.extend(
            [
                _make_tmp_text_node(
                    node_id="draft_status_caption",
                    name="DraftStatusCaption",
                    value="STATUS",
                    width=180,
                    height=20,
                    x=228,
                    y=24,
                    font_size=16,
                    color="#9FB2C1FF",
                    font_asset=body_font_asset,
                    alignment="Right",
                ),
                _make_tmp_text_node(
                    node_id="draft_status_value",
                    name="DraftStatusValue",
                    value=price_text,
                    width=220,
                    height=32,
                    x=208,
                    y=-10,
                    font_size=28,
                    color="#8CE0A7FF",
                    font_asset=title_font_asset or body_font_asset,
                    alignment="Right",
                ),
            ]
        )

    if primary_action_label:
        overlay_children.append(
            _make_tmp_text_node(
                node_id="draft_primary_action",
                name="DraftPrimaryActionLabel",
                value=primary_action_label,
                width=160,
                height=24,
                x=410,
                y=-48,
                font_size=18,
                color="#FFFFFFFF",
                font_asset=title_font_asset or body_font_asset,
                alignment="Center",
            )
        )
    if secondary_action_label:
        overlay_children.append(
            _make_tmp_text_node(
                node_id="draft_secondary_action",
                name="DraftSecondaryActionLabel",
                value=secondary_action_label,
                width=160,
                height=24,
                x=566,
                y=-48,
                font_size=18,
                color="#FFFFFFFF",
                font_asset=title_font_asset or body_font_asset,
                alignment="Center",
            )
        )
    return overlay_children, 1520, 188, 382


def _build_list_catalog_draft_blueprint(
    *,
    title: str,
    subtitle: str | None,
    body: str,
    price_text: str | None,
    primary_action_label: str | None,
    secondary_action_label: str | None,
    featured_sprite_asset: dict[str, Any] | None,
    title_font_asset: dict[str, Any] | None,
    body_font_asset: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], float, float, float]:
    overlay_children: list[dict[str, Any]] = [
        _make_tmp_text_node(
            node_id="draft_title",
            name="DraftTitle",
            value=title,
            width=760,
            height=52,
            x=-82,
            y=292,
            font_size=38,
            color="#F7E9AEFF",
            font_asset=title_font_asset,
            alignment="Left",
        ),
    ]

    if subtitle:
        overlay_children.append(
            _make_tmp_text_node(
                node_id="draft_subtitle",
                name="DraftSubtitle",
                value=subtitle,
                width=760,
                height=24,
                x=-82,
                y=254,
                font_size=18,
                color="#9FB2C1FF",
                font_asset=body_font_asset,
                alignment="Left",
            )
        )

    row_body_value = body if len(body) <= 72 else body[:69] + "..."
    row_action_value = price_text or primary_action_label or "OPEN"
    row_icon_asset = featured_sprite_asset
    row_names = [title, f"{title} Pack", f"{title} Bonus"]
    row_ys = [126, -24, -174]
    for index, row_y in enumerate(row_ys, start=1):
        overlay_children.append(
            {
                "id": f"draft_list_row_{index}",
                "name": f"DraftListRow{index}",
                "kind": "container",
                "rect": _center_rect(920, 124, y=row_y),
                "children": [
                    *(
                        [
                            _make_draft_image_node(
                                node_id=f"draft_list_row_{index}_icon",
                                name=f"DraftListRow{index}Icon",
                                asset=row_icon_asset,
                                width=76,
                                height=76,
                                x=-382,
                                y=0,
                            )
                        ]
                        if row_icon_asset
                        else []
                    ),
                    _make_tmp_text_node(
                        node_id=f"draft_list_row_{index}_title",
                        name=f"DraftListRow{index}Title",
                        value=row_names[index - 1],
                        width=420,
                        height=32,
                        x=-118,
                        y=20,
                        font_size=24,
                        color="#FFFFFFFF",
                        font_asset=title_font_asset or body_font_asset,
                        alignment="Left",
                    ),
                    _make_tmp_text_node(
                        node_id=f"draft_list_row_{index}_body",
                        name=f"DraftListRow{index}Body",
                        value=row_body_value,
                        width=440,
                        height=24,
                        x=-108,
                        y=-16,
                        font_size=18,
                        color="#C9D3DAFF",
                        font_asset=body_font_asset,
                        alignment="Left",
                    ),
                    _make_tmp_text_node(
                        node_id=f"draft_list_row_{index}_action",
                        name=f"DraftListRow{index}Action",
                        value=row_action_value,
                        width=176,
                        height=28,
                        x=316,
                        y=0,
                        font_size=20,
                        color="#8CE0A7FF" if price_text else "#FFFFFFFF",
                        font_asset=title_font_asset or body_font_asset,
                        alignment="Right",
                    ),
                ],
            }
        )

    footer_value = secondary_action_label or primary_action_label
    if footer_value:
        overlay_children.append(
            _make_tmp_text_node(
                node_id="draft_footer_action",
                name="DraftFooterAction",
                value=footer_value,
                width=280,
                height=28,
                x=312,
                y=-314,
                font_size=20,
                color="#FFFFFFFF",
                font_asset=title_font_asset or body_font_asset,
                alignment="Right",
            )
        )
    return overlay_children, 1120, 780, 0


def _build_catalog_draft_blueprint(
    *,
    template_mode: str,
    screen_name: str,
    title: str,
    subtitle: str | None,
    body: str,
    price_text: str | None,
    primary_action_label: str | None,
    secondary_action_label: str | None,
    shell_prefab_asset: dict[str, Any] | None,
    panel_sprite_asset: dict[str, Any] | None,
    panel_is_nine_slice: bool,
    featured_sprite_asset: dict[str, Any] | None,
    title_font_asset: dict[str, Any] | None,
    body_font_asset: dict[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    if template_mode == "hud":
        overlay_children, shell_width, shell_height, shell_y = _build_hud_catalog_draft_blueprint(
            title=title,
            subtitle=subtitle,
            body=body,
            price_text=price_text,
            primary_action_label=primary_action_label,
            secondary_action_label=secondary_action_label,
            featured_sprite_asset=featured_sprite_asset,
            title_font_asset=title_font_asset,
            body_font_asset=body_font_asset,
        )
    elif template_mode == "list":
        overlay_children, shell_width, shell_height, shell_y = _build_list_catalog_draft_blueprint(
            title=title,
            subtitle=subtitle,
            body=body,
            price_text=price_text,
            primary_action_label=primary_action_label,
            secondary_action_label=secondary_action_label,
            featured_sprite_asset=featured_sprite_asset,
            title_font_asset=title_font_asset,
            body_font_asset=body_font_asset,
        )
    else:
        overlay_children, shell_width, shell_height, shell_y = _build_popup_catalog_draft_blueprint(
            title=title,
            subtitle=subtitle,
            body=body,
            price_text=price_text,
            primary_action_label=primary_action_label,
            secondary_action_label=secondary_action_label,
            featured_sprite_asset=featured_sprite_asset,
            title_font_asset=title_font_asset,
            body_font_asset=body_font_asset,
        )

    overlay_root = {
        "id": "draft_overlay_root",
        "name": "DraftOverlayRoot",
        "kind": "container",
        "rect": _full_stretch_rect(),
        "children": overlay_children,
    }

    shell_node, shell_source_mode = _wrap_catalog_draft_shell(
        overlay_root=overlay_root,
        shell_prefab_asset=shell_prefab_asset,
        panel_sprite_asset=panel_sprite_asset,
        panel_is_nine_slice=panel_is_nine_slice,
        width=shell_width,
        height=shell_height,
        y=shell_y,
    )

    blueprint = {
        "screenName": screen_name,
        "stack": "ugui",
        "root": {
            "id": "root_canvas",
            "name": f"{screen_name}Canvas",
            "kind": "canvas",
            "canvasScaler": {
                "uiScaleMode": "ScaleWithScreenSize",
                "referenceResolution": {"x": 1920, "y": 1080},
                "screenMatchMode": "MatchWidthOrHeight",
                "matchWidthOrHeight": 0.5,
            },
            "children": [
                {
                    "id": "safe_area_root",
                    "name": "SafeAreaRoot",
                    "kind": "container",
                    "rect": _full_stretch_rect(),
                    "children": [shell_node],
                }
            ],
        },
    }
    return blueprint, shell_source_mode


def _http_json_request(url: str, method: str, params: dict[str, Any] | None, timeout_ms: int, request_id: int) -> dict[str, Any]:
    try:
        data = get_unity_http_client(url, timeout_ms).request(method, params, request_id)
    except UnityMcpHttpError as exc:
        details = {"responseText": exc.response_text} if exc.response_text else {}
        raise ToolExecutionError(str(exc), details=details) from exc

    if data.get("error"):
        raise ToolExecutionError(
            "Unity MCP returned an error.",
            details={"unityMcpError": data["error"]},
        )

    result = data.get("result")
    if not isinstance(result, dict):
        raise ToolExecutionError(
            "Unity MCP returned an unexpected result shape.",
            details={"unityMcpResponse": data},
        )
    return result


def _list_unity_mcp_tools(unity_mcp_url: str, timeout_ms: int) -> list[str]:
    result = _http_json_request(unity_mcp_url, "tools/list", {}, timeout_ms, 1)
    return sorted(
        str(item.get("name"))
        for item in result.get("tools", [])
        if isinstance(item, dict) and item.get("name")
    )


def _decode_mcp_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured

    content = result.get("content")
    if isinstance(content, list):
        parsed_candidates: list[dict[str, Any]] = []
        raw_texts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            raw_texts.append(text)
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                parsed_candidates.append(parsed)
        if parsed_candidates:
            return parsed_candidates[-1]
        if raw_texts:
            return {"rawText": "\n".join(raw_texts)}

    if isinstance(result, dict):
        return result
    return {}


def _call_unity_mcp_tool(
    unity_mcp_url: str,
    available_tools: list[str],
    tool_name: str,
    arguments: dict[str, Any],
    timeout_ms: int,
    unity_project_path: Path | None = None,
) -> dict[str, Any]:
    if tool_name in available_tools:
        request_name = tool_name
        request_arguments = arguments
        invocation_mode = "direct"
    elif "execute_custom_tool" in available_tools:
        request_name = "execute_custom_tool"
        request_arguments = {
            "customToolName": tool_name,
            "parameters": arguments,
        }
        invocation_mode = "execute_custom_tool"
    elif "execute_menu_item" in available_tools and unity_project_path is not None:
        return _call_unity_menu_bridge_tool(
            unity_mcp_url=unity_mcp_url,
            tool_name=tool_name,
            arguments=arguments,
            timeout_ms=timeout_ms,
            unity_project_path=unity_project_path,
        )
    else:
        raise ToolExecutionError(
            f"Unity MCP does not expose `{tool_name}`.",
            details={"availableTools": available_tools},
        )

    result = _http_json_request(
        unity_mcp_url,
        "tools/call",
        {"name": request_name, "arguments": request_arguments},
        timeout_ms,
        2,
    )
    payload = _decode_mcp_tool_result(result)
    if payload.get("success") is False:
        raise ToolExecutionError(
            f"Unity tool `{tool_name}` failed: {payload.get('error') or payload.get('message') or 'unknown error'}",
            details={"unityResponse": payload, "invocationMode": invocation_mode},
        )

    return {
        "tool": tool_name,
        "invocationMode": invocation_mode,
        "requestName": request_name,
        "response": payload,
    }


def _call_unity_menu_bridge_tool(
    unity_mcp_url: str,
    tool_name: str,
    arguments: dict[str, Any],
    timeout_ms: int,
    unity_project_path: Path,
) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    interop_dir = unity_project_path / "Library" / "ResourceRag" / "Interop"
    request_path = unity_project_path / DEFAULT_MENU_BRIDGE_REQUEST_RELATIVE_PATH
    response_path = unity_project_path / DEFAULT_MENU_BRIDGE_RESPONSE_RELATIVE_PATH
    interop_dir.mkdir(parents=True, exist_ok=True)

    request_payload = {
        "requestId": request_id,
        "toolName": tool_name,
        "parameters": arguments,
    }
    request_path.write_text(json.dumps(request_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    client = get_unity_http_client(unity_mcp_url, timeout_ms)
    result = client.request(
        "tools/call",
        {
            "name": "execute_menu_item",
            "arguments": {
                "menu_path": UNITY_RAG_MENU_BRIDGE_PATH,
            },
        },
        99,
    )
    payload = _decode_mcp_tool_result(result.get("result", result))
    if payload.get("success") is False:
        raise ToolExecutionError(
            "Unity 메뉴 브리지 실행 요청에 실패했습니다.",
            details={"unityResponse": payload},
        )

    deadline = time.monotonic() + max(timeout_ms / 1000.0, 1.0)
    while time.monotonic() < deadline:
        if response_path.exists():
            try:
                response_payload = json.loads(response_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                response_payload = None

            if isinstance(response_payload, dict) and response_payload.get("requestId") == request_id:
                if not response_payload.get("success", False):
                    raise ToolExecutionError(
                        f"Unity 메뉴 브리지 `{tool_name}` 실행에 실패했습니다.",
                        details={"bridgeResponse": response_payload},
                    )

                tool_payload = response_payload.get("payload")
                if not isinstance(tool_payload, dict):
                    raise ToolExecutionError(
                        "Unity 메뉴 브리지가 예상하지 못한 응답 형식을 반환했습니다.",
                        details={"bridgeResponse": response_payload},
                    )

                if tool_payload.get("success") is False:
                    raise ToolExecutionError(
                        f"Unity tool `{tool_name}` failed: {tool_payload.get('error') or tool_payload.get('message') or 'unknown error'}",
                        details={"unityResponse": tool_payload, "invocationMode": "menu_bridge"},
                    )

                return {
                    "tool": tool_name,
                    "invocationMode": "menu_bridge",
                    "requestName": "execute_menu_item",
                    "response": tool_payload,
                }

        time.sleep(0.25)

    raise ToolExecutionError(
        f"Unity 메뉴 브리지 `{tool_name}` 응답 대기 시간이 초과되었습니다.",
        details={
            "requestId": request_id,
            "requestPath": str(request_path),
            "responsePath": str(response_path),
        },
    )


def extract_reference_layout(args: dict[str, Any]) -> dict[str, Any]:
    args = _apply_connection_preset(args)
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
        ("codex_auth_file", "--codex-auth-file"),
        ("gateway_url", "--gateway-url"),
        ("gateway_auth_token_env", "--gateway-auth-token-env"),
        ("gateway_timeout_ms", "--gateway-timeout-ms"),
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


def inspect_provider_setup(args: dict[str, Any]) -> dict[str, Any]:
    args = _apply_connection_preset(args)
    provider = str(args.get("provider") or "auto")
    config = ProviderConfig(
        provider=provider,
        screen_name="inspect-provider-setup",
        model=DEFAULT_MODEL,
        detail=DEFAULT_DETAIL,
        max_image_dim=DEFAULT_MAX_IMAGE_DIM,
        project_hints=[],
        api_key_env=str(args.get("provider_api_key_env") or "OPENAI_API_KEY"),
        auth_mode=str(args["auth_mode"]) if args.get("auth_mode") else None,
        oauth_token_env=str(args["oauth_token_env"]) if args.get("oauth_token_env") else None,
        oauth_token_file=str(args["oauth_token_file"]) if args.get("oauth_token_file") else None,
        oauth_token_command=str(args["oauth_token_command"]) if args.get("oauth_token_command") else None,
        codex_auth_file=str(args["codex_auth_file"]) if args.get("codex_auth_file") else None,
        base_url=str(args["provider_base_url"]) if args.get("provider_base_url") else None,
        gateway_url=str(args["gateway_url"]) if args.get("gateway_url") else None,
        gateway_auth_token_env=str(args.get("gateway_auth_token_env") or "UNITY_RESOURCE_RAG_GATEWAY_TOKEN"),
        gateway_timeout_ms=int(args.get("gateway_timeout_ms") or 30000),
    )

    inspection = inspect_provider_setup_config(config)
    token_source_summary = "Not needed (local_heuristic)" if inspection.resolved_provider == "local_heuristic" else "Unknown"
    if inspection.auth_mode == "api_key":
        token_source_summary = f"API key environment variable `{inspection.provider_api_key_env}`"
    elif inspection.resolved_provider == "gateway" and inspection.token_source_detail:
        token_source_summary = f"Optional gateway bearer env `{inspection.token_source_detail}`"
    elif inspection.token_source == "env" and inspection.token_source_detail:
        token_source_summary = f"Environment variable `{inspection.token_source_detail}`"
    elif inspection.token_source == "file" and inspection.token_source_detail:
        token_source_summary = f"Token file `{inspection.token_source_detail}`"
    elif inspection.token_source == "command" and inspection.token_source_detail:
        token_source_summary = f"Token command `{inspection.token_source_detail}`"
    elif inspection.token_source == "codex_file" and inspection.token_source_detail:
        token_source_summary = f"Codex sign-in file `{inspection.token_source_detail}`"

    payload = {
        "requestedProvider": inspection.requested_provider,
        "resolvedProvider": inspection.resolved_provider,
        "authMode": inspection.auth_mode,
        "providerBaseUrl": inspection.provider_base_url,
        "providerApiKeyEnv": inspection.provider_api_key_env,
        "tokenSource": inspection.token_source,
        "tokenSourceDetail": inspection.token_source_detail,
        "tokenSourceSummary": token_source_summary,
        "gatewayUrl": str(args["gateway_url"]) if args.get("gateway_url") else None,
        "gatewayAuthTokenEnv": str(args.get("gateway_auth_token_env") or "UNITY_RESOURCE_RAG_GATEWAY_TOKEN"),
        "gatewayTimeoutMs": int(args.get("gateway_timeout_ms") or 30000),
        "recommendedChoice": inspection.recommended_choice,
        "missingSettings": inspection.missing_settings,
        "nextActions": inspection.next_actions,
        "summary": inspection.summary,
    }
    return {
        "content": [
            {
                "type": "text",
                "text": _format_inspection_summary(payload),
            },
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=2),
            },
        ],
        "isError": False,
    }


def doctor(args: dict[str, Any]) -> dict[str, Any]:
    args = _apply_connection_preset(args)
    payload = build_doctor_payload(args)
    return {
        "content": [
            {
                "type": "text",
                "text": _format_doctor_summary(payload),
            },
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=2),
            },
        ],
        "isError": payload.get("overallStatus") == "error",
    }


def run_first_pass_ui_build(args: dict[str, Any]) -> dict[str, Any]:
    args = _apply_connection_preset(args)

    unity_project_path = _resolve_optional_path(args.get("unity_project_path"))
    catalog_path = _resolve_catalog_path(args.get("catalog"), unity_project_path)
    if catalog_path is None:
        raise ToolExecutionError("`catalog` or `unity_project_path` is required.")

    apply_in_unity = bool(args.get("apply_in_unity", True))
    validate_before_apply = bool(args.get("validate_before_apply", True))
    force_reindex = bool(args.get("force_reindex", False))

    unity_mcp_url = str(args.get("unity_mcp_url") or DEFAULT_UNITY_MCP_URL)
    unity_mcp_timeout_ms = int(args.get("unity_mcp_timeout_ms") or DEFAULT_UNITY_MCP_OPERATION_TIMEOUT_MS)
    available_tools: list[str] | None = None

    if force_reindex or not catalog_path.exists() or apply_in_unity:
        available_tools = _list_unity_mcp_tools(unity_mcp_url, unity_mcp_timeout_ms)

    index_result: dict[str, Any] | None = None
    if force_reindex or not catalog_path.exists():
        if available_tools is None:
            available_tools = _list_unity_mcp_tools(unity_mcp_url, unity_mcp_timeout_ms)
        index_result = _call_unity_mcp_tool(
            unity_mcp_url,
            available_tools,
            "index_project_resources",
            {"outputPath": str(catalog_path)},
            unity_mcp_timeout_ms,
            unity_project_path=unity_project_path,
        )

    workflow_args = dict(args)
    workflow_args["catalog"] = str(catalog_path)
    workflow_result = run_reference_to_resolved_blueprint(workflow_args)
    workflow_payload = _extract_wrapped_payload(workflow_result)
    if workflow_result.get("isError") or workflow_payload.get("hasErrors"):
        raise ToolExecutionError(
            "First-pass workflow failed before Unity apply.",
            details={"workflow": workflow_payload or workflow_result},
        )

    resolved_blueprint = str(workflow_payload.get("resolvedBlueprint") or "")
    handoff_bundle = str(workflow_payload.get("mcpHandoffBundle") or "")
    if not resolved_blueprint:
        raise ToolExecutionError(
            "Workflow completed but did not return a resolved blueprint path.",
            details={"workflow": workflow_payload},
        )

    handoff_payload: dict[str, Any] | None = None
    if handoff_bundle:
        handoff_path = Path(handoff_bundle)
        if handoff_path.exists():
            with handoff_path.open("r", encoding="utf-8") as handle:
                handoff_payload = json.load(handle)

    validate_result: dict[str, Any] | None = None
    apply_result: dict[str, Any] | None = None
    if apply_in_unity:
        if available_tools is None:
            available_tools = _list_unity_mcp_tools(unity_mcp_url, unity_mcp_timeout_ms)
        if validate_before_apply:
            validate_result = _call_unity_mcp_tool(
                unity_mcp_url,
                available_tools,
                "apply_ui_blueprint",
                {"action": "validate", "blueprintPath": resolved_blueprint},
                unity_mcp_timeout_ms,
                unity_project_path=unity_project_path,
            )
        apply_result = _call_unity_mcp_tool(
            unity_mcp_url,
            available_tools,
            "apply_ui_blueprint",
            {"action": "apply", "blueprintPath": resolved_blueprint},
            unity_mcp_timeout_ms,
            unity_project_path=unity_project_path,
        )

    next_actions: list[str] = []
    verify_request = ((handoff_payload or {}).get("requests") or {}).get("verify")
    if verify_request:
        next_actions.append("After apply, capture the first result with a `manage_camera` screenshot request.")
    next_actions.append("If the result looks off, run `unity_rag.run_verification_repair_loop` to generate a repair handoff.")

    payload = {
        "unityProjectPath": str(unity_project_path) if unity_project_path else None,
        "catalogPath": str(catalog_path),
        "catalogIndexed": index_result is not None,
        "unityMcpUrl": unity_mcp_url if (force_reindex or apply_in_unity or unity_project_path) else None,
        "indexResult": index_result,
        "workflow": workflow_payload,
        "handoffBundle": handoff_payload,
        "unityValidate": validate_result,
        "unityApply": apply_result,
        "verifyRequest": verify_request,
        "nextActions": next_actions,
    }
    return _format_tool_result("run_first_pass_ui_build", payload)


def run_catalog_draft_ui_build(args: dict[str, Any]) -> dict[str, Any]:
    goal = str(args.get("goal") or "").strip()
    if not goal:
        raise ToolExecutionError("`goal` is required.")

    template_mode = _normalize_draft_template_mode(args.get("template_mode"))
    screen_name = str(args.get("screen_name") or "CatalogDraft").strip() or "CatalogDraft"
    title = str(args.get("title") or goal).strip() or screen_name
    body = str(args.get("body") or goal).strip() or goal
    subtitle = str(args.get("subtitle") or "").strip() or None
    price_text = str(args.get("price_text") or "").strip() or None
    primary_action_label = str(args.get("primary_action_label") or "").strip() or None
    secondary_action_label = str(args.get("secondary_action_label") or "").strip() or None

    unity_project_path = _resolve_optional_path(args.get("unity_project_path"))
    catalog_path = _resolve_catalog_path(args.get("catalog"), unity_project_path)
    if catalog_path is None:
        raise ToolExecutionError("`catalog` or `unity_project_path` is required.")

    vector_index_path = _resolve_path_against_project(args.get("vector_index"), unity_project_path)
    output_dir = _resolve_path_against_project(args.get("output_dir"), unity_project_path)
    if output_dir is None:
        output_dir = _default_catalog_draft_output_dir(screen_name, unity_project_path, catalog_path)

    apply_in_unity = bool(args.get("apply_in_unity", True))
    validate_before_apply = bool(args.get("validate_before_apply", True))
    force_reindex = bool(args.get("force_reindex", False))

    unity_mcp_url = str(args.get("unity_mcp_url") or DEFAULT_UNITY_MCP_URL)
    unity_mcp_timeout_ms = int(args.get("unity_mcp_timeout_ms") or DEFAULT_UNITY_MCP_OPERATION_TIMEOUT_MS)
    available_tools: list[str] | None = None

    if force_reindex or not catalog_path.exists() or apply_in_unity:
        available_tools = _list_unity_mcp_tools(unity_mcp_url, unity_mcp_timeout_ms)

    index_result: dict[str, Any] | None = None
    if force_reindex or not catalog_path.exists():
        if available_tools is None:
            available_tools = _list_unity_mcp_tools(unity_mcp_url, unity_mcp_timeout_ms)
        index_result = _call_unity_mcp_tool(
            unity_mcp_url,
            available_tools,
            "index_project_resources",
            {"outputPath": str(catalog_path)},
            unity_mcp_timeout_ms,
            unity_project_path=unity_project_path,
        )

    if not catalog_path.exists():
        raise ToolExecutionError(
            "Catalog draft build requires an existing resource catalog after indexing.",
            details={"catalogPath": str(catalog_path)},
        )

    records = _load_jsonl_records(catalog_path)
    records_by_id = {
        str(record.get("id")): record
        for record in records
        if isinstance(record, dict) and record.get("id")
    }
    query_defaults = _catalog_draft_query_defaults(template_mode, goal)
    semantic_terms = _catalog_draft_semantic_terms(template_mode)

    shell_search = _search_catalog_records(
        catalog_path,
        str(args.get("shell_query") or query_defaults["shell"]),
        preferred_kind="prefab",
        region_type="popup_frame",
        vector_index_path=vector_index_path,
        top_k=5,
    )
    panel_search = _search_catalog_records(
        catalog_path,
        str(args.get("panel_query") or query_defaults["panel"]),
        preferred_kind="sprite",
        region_type="popup_frame",
        aspect_ratio=920.0 / 640.0,
        vector_index_path=vector_index_path,
        top_k=5,
    )
    icon_search = _search_catalog_records(
        catalog_path,
        str(args.get("featured_asset_query") or query_defaults["featured"]),
        preferred_kind="sprite",
        region_type="icon",
        aspect_ratio=1.0,
        vector_index_path=vector_index_path,
        top_k=5,
    )
    title_font_search = _search_catalog_records(
        catalog_path,
        str(args.get("title_font_query") or query_defaults["title_font"]),
        preferred_kind="tmp_font",
        vector_index_path=vector_index_path,
        top_k=5,
    )
    body_font_search = _search_catalog_records(
        catalog_path,
        str(args.get("body_font_query") or query_defaults["body_font"]),
        preferred_kind="tmp_font",
        vector_index_path=vector_index_path,
        top_k=5,
    )

    shell_candidate, shell_record = _select_catalog_candidate(
        shell_search,
        records_by_id,
        asset_types=("prefab",),
        binding_kinds=("prefab",),
        semantic_terms=semantic_terms["shell"],
        min_score=0.34,
    )
    panel_candidate, panel_record = _select_catalog_candidate(
        panel_search,
        records_by_id,
        asset_types=("sprite", "texture2d"),
        binding_kinds=("sprite",),
        semantic_terms=semantic_terms["panel"],
        min_score=0.34,
    )
    icon_candidate, icon_record = _select_catalog_candidate(
        icon_search,
        records_by_id,
        asset_types=("sprite", "texture2d"),
        binding_kinds=("sprite",),
        semantic_terms=semantic_terms["featured"],
        min_score=0.30,
    )

    title_font_candidate, title_font_record = _select_catalog_candidate(
        title_font_search,
        records_by_id,
        asset_types=("tmp_fontasset",),
        binding_kinds=("tmp_font",),
    )
    if title_font_candidate is None:
        title_font_record = _fallback_catalog_record(records, asset_types=("tmp_fontasset",), binding_kinds=("tmp_font",))
        if title_font_record is not None:
            title_font_candidate = _candidate_from_record(title_font_record, reason="font-fallback")

    body_font_candidate, body_font_record = _select_catalog_candidate(
        body_font_search,
        records_by_id,
        asset_types=("tmp_fontasset",),
        binding_kinds=("tmp_font",),
    )
    if body_font_candidate is None:
        body_font_record = title_font_record or _fallback_catalog_record(records, asset_types=("tmp_fontasset",), binding_kinds=("tmp_font",))
        if body_font_record is not None:
            body_font_candidate = _candidate_from_record(body_font_record, reason="font-fallback")

    shell_prefab_asset = _asset_reference_from_candidate(shell_candidate, shell_record, forced_kind="prefab")
    panel_sprite_asset = _asset_reference_from_candidate(panel_candidate, panel_record, forced_kind="sprite")
    featured_sprite_asset = _asset_reference_from_candidate(icon_candidate, icon_record, forced_kind="sprite")
    title_font_asset = _asset_reference_from_candidate(title_font_candidate, title_font_record, forced_kind="tmp_font")
    body_font_asset = _asset_reference_from_candidate(body_font_candidate, body_font_record, forced_kind="tmp_font")

    panel_is_nine_slice = bool(((panel_record or {}).get("uiHints") or {}).get("isNineSliceCandidate"))

    blueprint, shell_source_mode = _build_catalog_draft_blueprint(
        template_mode=template_mode,
        screen_name=screen_name,
        title=title,
        subtitle=subtitle,
        body=body,
        price_text=price_text,
        primary_action_label=primary_action_label,
        secondary_action_label=secondary_action_label,
        shell_prefab_asset=shell_prefab_asset,
        panel_sprite_asset=panel_sprite_asset,
        panel_is_nine_slice=panel_is_nine_slice,
        featured_sprite_asset=featured_sprite_asset,
        title_font_asset=title_font_asset,
        body_font_asset=body_font_asset,
    )

    blueprint_path = output_dir / "01-catalog-draft-blueprint.json"
    search_report_path = output_dir / "00-catalog-draft-searches.json"
    _save_json(blueprint_path, blueprint)
    _save_json(
        search_report_path,
        {
            "screenName": screen_name,
            "goal": goal,
            "templateMode": template_mode,
            "catalogPath": str(catalog_path),
            "vectorIndex": str(vector_index_path) if vector_index_path else None,
            "selectedAssets": {
                "shellPrefab": shell_candidate,
                "panelSprite": panel_candidate,
                "featuredSprite": icon_candidate,
                "titleFont": title_font_candidate,
                "bodyFont": body_font_candidate,
            },
            "queries": {
                "shellPrefab": shell_search,
                "panelSprite": panel_search,
                "featuredSprite": icon_search,
                "titleFont": title_font_search,
                "bodyFont": body_font_search,
            },
        },
    )

    handoff_result = build_mcp_handoff_bundle({"resolved_blueprint": str(blueprint_path)})
    handoff_payload = _extract_wrapped_payload(handoff_result)
    handoff_bundle_path = Path(str(handoff_payload.get("output") or "")).expanduser().resolve() if handoff_payload.get("output") else None
    handoff_bundle: dict[str, Any] | None = None
    if handoff_bundle_path and handoff_bundle_path.exists():
        with handoff_bundle_path.open("r", encoding="utf-8") as handle:
            handoff_bundle = json.load(handle)

    validate_result: dict[str, Any] | None = None
    apply_result: dict[str, Any] | None = None
    if apply_in_unity:
        if available_tools is None:
            available_tools = _list_unity_mcp_tools(unity_mcp_url, unity_mcp_timeout_ms)
        if validate_before_apply:
            validate_result = _call_unity_mcp_tool(
                unity_mcp_url,
                available_tools,
                "apply_ui_blueprint",
                {"action": "validate", "blueprintPath": str(blueprint_path)},
                unity_mcp_timeout_ms,
                unity_project_path=unity_project_path,
            )
        apply_result = _call_unity_mcp_tool(
            unity_mcp_url,
            available_tools,
            "apply_ui_blueprint",
            {"action": "apply", "blueprintPath": str(blueprint_path)},
            unity_mcp_timeout_ms,
            unity_project_path=unity_project_path,
        )

    verify_request = ((handoff_bundle or {}).get("requests") or {}).get("verify")
    next_actions = [
        "Once the draft appears, adjust the title, body, price copy, and spacing first.",
        "If the result looks off, capture it with `manage_camera` and then run `unity_rag.run_verification_repair_loop` to create a repair handoff.",
    ]
    if template_mode == "hud":
        next_actions.insert(0, "The HUD draft is optimized around a top bar and status information layout. Tune the width and icon density to match the pacing of your game.")
    elif template_mode == "list":
        next_actions.insert(0, "The list draft creates three sample rows. Adjust the row count and action copy to match your actual inventory or shop flow.")
    else:
        next_actions.insert(0, "The popup draft starts as a modal or panel-focused layout. First confirm that the title, body, and action hierarchy feels right.")

    if shell_source_mode == "bare_container":
        next_actions.insert(1, f"No {template_mode} shell candidate was found, so the draft was built as a bare container. Make `shell_query` more specific or confirm the representative {template_mode} prefab path.")
    elif shell_source_mode == "panel_sprite":
        next_actions.insert(1, "This draft used a panel sprite instead of a prefab shell. Affordances and button placement may need manual follow-up.")

    payload = {
        "unityProjectPath": str(unity_project_path) if unity_project_path else None,
        "catalogPath": str(catalog_path),
        "catalogIndexed": index_result is not None,
        "outputDir": str(output_dir),
        "templateMode": template_mode,
        "draftMode": shell_source_mode,
        "shellSourceMode": shell_source_mode,
        "draftBlueprint": str(blueprint_path),
        "searchReport": str(search_report_path),
        "handoffBundlePath": str(handoff_bundle_path) if handoff_bundle_path else None,
        "handoffBundle": handoff_bundle,
        "selectedAssets": {
            "shellPrefab": shell_candidate,
            "panelSprite": panel_candidate,
            "featuredSprite": icon_candidate,
            "titleFont": title_font_candidate,
            "bodyFont": body_font_candidate,
        },
        "unityMcpUrl": unity_mcp_url if (force_reindex or apply_in_unity or unity_project_path) else None,
        "indexResult": index_result,
        "unityValidate": validate_result,
        "unityApply": apply_result,
        "verifyRequest": verify_request,
        "nextActions": next_actions,
    }
    return _format_tool_result("run_catalog_draft_ui_build", payload)


def start_ui_build(args: dict[str, Any]) -> dict[str, Any]:
    args = _apply_connection_preset(args)
    template_mode = _normalize_draft_template_mode(args.get("template_mode"))

    run_doctor = bool(args.get("run_doctor", True))
    require_doctor_ok = bool(args.get("require_doctor_ok", True))
    doctor_payload = build_doctor_payload(args) if run_doctor else None
    if doctor_payload is not None and require_doctor_ok and doctor_payload.get("overallStatus") == "error":
        raise ToolExecutionError(
            "Doctor detected blocking setup issues before starting the UI build.",
            details={"doctor": doctor_payload},
        )

    has_reference_input = bool(args.get("image") or args.get("reference_layout"))
    route = "reference_first_pass" if has_reference_input else "catalog_draft"
    route_reason = (
        "reference input (`image` or `reference_layout`) was provided."
        if has_reference_input
        else f"no reference input was provided, so the catalog-first draft path was selected with template_mode `{template_mode}`."
    )

    route_args = dict(args)
    if route == "catalog_draft":
        inferred_goal = (
            str(route_args.get("goal") or "").strip()
            or str(route_args.get("title") or "").strip()
            or str(route_args.get("body") or "").strip()
            or str(route_args.get("screen_name") or "").strip()
            or "catalog draft ui"
        )
        route_args["goal"] = inferred_goal
        execution_result = run_catalog_draft_ui_build(route_args)
    else:
        execution_result = run_first_pass_ui_build(route_args)

    execution_payload = _extract_wrapped_payload(execution_result)
    doctor_next_actions = doctor_payload.get("nextActions") or [] if isinstance(doctor_payload, dict) else []
    execution_next_actions = execution_payload.get("nextActions") or [] if isinstance(execution_payload, dict) else []
    next_actions = _dedupe_strings([*doctor_next_actions, *execution_next_actions])

    payload = {
        "selectedPath": route,
        "routeReason": route_reason,
        "doctor": doctor_payload,
        "execution": execution_payload,
        "nextActions": next_actions,
    }
    return _format_tool_result("start_ui_build", payload)


def run_reference_to_resolved_blueprint(args: dict[str, Any]) -> dict[str, Any]:
    args = _apply_connection_preset(args)
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
        ("codex_auth_file", "--codex-auth-file"),
        ("gateway_url", "--gateway-url"),
        ("gateway_auth_token_env", "--gateway-auth-token-env"),
        ("gateway_timeout_ms", "--gateway-timeout-ms"),
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
        name="unity_rag.start_ui_build",
        description="Shortest single entrypoint. Runs doctor diagnostics first, then automatically chooses the reference-first path when `image` or `reference_layout` is present, or the catalog-first draft path otherwise, and continues through Unity apply.",
        input_schema=_build_start_ui_build_schema(),
        handler=start_ui_build,
    ),
    ToolSpec(
        name="unity_rag.doctor",
        description="Diagnoses the current configuration and local runtime in one pass. Checks provider/auth, the Unity project path, catalog presence, gateway health, and Unity MCP HTTP Local custom tool/resource exposure.",
        input_schema=_build_doctor_schema(),
        handler=doctor,
    ),
    ToolSpec(
        name="unity_rag.inspect_provider_setup",
        description="Inspects only provider/auth setup before you run the full workflow. Useful for checking the recommended preset, resolved provider, token source, missing settings, and next actions during first-time setup.",
        input_schema=_build_inspect_provider_setup_schema(),
        handler=inspect_provider_setup,
    ),
    ToolSpec(
        name="unity_rag.run_first_pass_ui_build",
        description="Runs the first-success path end to end. If the catalog is missing, it calls `index_project_resources` in Unity, creates a resolved blueprint through the sidecar workflow, and continues through Unity `apply_ui_blueprint` validate/apply.",
        input_schema=_build_run_first_pass_ui_build_schema(),
        handler=run_first_pass_ui_build,
    ),
    ToolSpec(
        name="unity_rag.run_catalog_draft_ui_build",
        description="Builds a first UI draft from the catalog even without a reference image. Searches for shell, panel, icon, and font candidates, creates a draft blueprint, and can continue through Unity `apply_ui_blueprint` validate/apply.",
        input_schema=_build_run_catalog_draft_ui_build_schema(),
        handler=run_catalog_draft_ui_build,
    ),
    ToolSpec(
        name="unity_rag.extract_reference_layout",
        description="Extracts a reference layout plan JSON from a reference image. For first-time setup, `connection_preset=recommended_auto` is recommended; use `codex_oauth` to force Codex OAuth or `offline_local` for a fully offline check.",
        input_schema=_build_extract_reference_layout_schema(),
        handler=extract_reference_layout,
    ),
    ToolSpec(
        name="unity_rag.run_reference_to_resolved_blueprint",
        description="Runs the full workflow from a reference image or existing reference layout through the resolved blueprint and MCP handoff bundle. For first-time setup, `connection_preset=recommended_auto` is recommended; use `openai_api_key`, `gemini_api_key`, `claude_api_key`, or `claude_code` when you want an explicit provider route.",
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
