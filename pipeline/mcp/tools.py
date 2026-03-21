from __future__ import annotations

import json
import os
import subprocess
import sys
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
    from pipeline.planner.extract_reference_layout import (
        DEFAULT_DETAIL,
        DEFAULT_MAX_IMAGE_DIM,
        DEFAULT_MODEL,
        ProviderConfig,
        inspect_provider_setup as inspect_provider_setup_config,
    )
else:
    from .doctor import DEFAULT_UNITY_MCP_TIMEOUT_MS, DEFAULT_UNITY_MCP_URL, build_doctor_payload
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

PROVIDER_DESCRIPTION = (
    "추출 provider 선택. "
    "`auto`: 권장값, gateway URL이나 감지 가능한 인증을 자동 선택. "
    "`openai`: OpenAI API key 또는 Codex OAuth 사용. "
    "`gemini`: Google API key 사용. "
    "`antigravity`: Google OAuth/gcloud 토큰 사용. "
    "`claude`: Anthropic API key 사용. "
    "`claude_code`: Claude Code credential 사용. "
    "`openai_compatible`: 사용자 지정 OpenAI-compatible endpoint 사용. "
    "`gateway`: team/provider gateway 사용. "
    "`local_heuristic`: 완전 로컬 fallback."
)

ADVANCED_SETTING_SUFFIX = "고급 설정. 대부분의 사용자는 비워두고 `provider=auto`만 선택하면 됨."

CONNECTION_PRESET_DESCRIPTION = (
    "초기 연결 설정용 프리셋. "
    "`recommended_auto`: 권장값, 감지 가능한 인증을 자동 선택. "
    "`codex_oauth`: Codex OAuth로 OpenAI 연결. "
    "`openai_api_key`: OPENAI_API_KEY로 OpenAI 연결. "
    "`gemini_api_key`: GEMINI_API_KEY 또는 GOOGLE_API_KEY로 Gemini 연결. "
    "`google_oauth`: GOOGLE_OAUTH_ACCESS_TOKEN 또는 gcloud 토큰으로 Google OAuth 연결. "
    "`claude_api_key`: ANTHROPIC_API_KEY로 Claude 연결. "
    "`claude_code`: ANTHROPIC_AUTH_TOKEN 또는 Claude Code credential로 연결. "
    "`custom_openai_compatible`: 사용자 지정 OpenAI-compatible endpoint 연결. "
    "`offline_local`: 네트워크 없이 local heuristic만 사용. "
    "프리셋이 지정되면 같은 범주의 저수준 provider/auth 입력보다 프리셋이 우선한다."
)

PROVIDER_ENUM = ["auto", "openai", "gemini", "antigravity", "claude", "claude_code", "openai_compatible", "gateway", "local_heuristic"]
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
            "provider_base_url": {"type": "string", "description": _advanced_description("사용자 지정 OpenAI-compatible endpoint나 base URL override.")},
            "provider_api_key_env": {"type": "string", "description": _advanced_description("API key를 읽을 환경 변수 이름.")},
            "auth_mode": {"type": "string", "enum": ["api_key", "oauth_token"], "description": _advanced_description("API-backed provider 인증 방식.")},
            "oauth_token_env": {"type": "string", "description": _advanced_description("OAuth bearer token을 읽을 환경 변수 이름.")},
            "oauth_token_file": {"type": "string", "description": _advanced_description("OAuth bearer token이 들어 있는 파일 경로.")},
            "oauth_token_command": {"type": "string", "description": _advanced_description("OAuth bearer token을 stdout으로 출력하는 명령.")},
            "codex_auth_file": {"type": "string", "description": _advanced_description("Codex OAuth auth.json 파일 경로.")},
            "gateway_url": {"type": "string", "description": _advanced_description("Gateway base URL.")},
            "gateway_auth_token_env": {"type": "string", "description": _advanced_description("Gateway bearer token을 읽을 환경 변수 이름.")},
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
            "provider_base_url": {"type": "string", "description": _advanced_description("사용자 지정 OpenAI-compatible endpoint나 base URL override.")},
            "provider_api_key_env": {"type": "string", "description": _advanced_description("API key를 읽을 환경 변수 이름.")},
            "auth_mode": {"type": "string", "enum": ["api_key", "oauth_token"], "description": _advanced_description("API-backed provider 인증 방식.")},
            "oauth_token_env": {"type": "string", "description": _advanced_description("OAuth bearer token을 읽을 환경 변수 이름.")},
            "oauth_token_file": {"type": "string", "description": _advanced_description("OAuth bearer token이 들어 있는 파일 경로.")},
            "oauth_token_command": {"type": "string", "description": _advanced_description("OAuth bearer token을 stdout으로 출력하는 명령.")},
            "codex_auth_file": {"type": "string", "description": _advanced_description("Codex OAuth auth.json 파일 경로.")},
            "gateway_url": {"type": "string", "description": _advanced_description("Gateway base URL.")},
            "gateway_auth_token_env": {"type": "string", "description": _advanced_description("Gateway bearer token을 읽을 환경 변수 이름.")},
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
            "provider_base_url": {"type": "string", "description": _advanced_description("사용자 지정 OpenAI-compatible endpoint나 base URL override.")},
            "provider_api_key_env": {"type": "string", "description": _advanced_description("API key를 읽을 환경 변수 이름.")},
            "auth_mode": {"type": "string", "enum": ["api_key", "oauth_token"], "description": _advanced_description("API-backed provider 인증 방식.")},
            "oauth_token_env": {"type": "string", "description": _advanced_description("OAuth bearer token을 읽을 환경 변수 이름.")},
            "oauth_token_file": {"type": "string", "description": _advanced_description("OAuth bearer token이 들어 있는 파일 경로.")},
            "oauth_token_command": {"type": "string", "description": _advanced_description("OAuth bearer token을 stdout으로 출력하는 명령.")},
            "codex_auth_file": {"type": "string", "description": _advanced_description("Codex OAuth auth.json 파일 경로.")},
            "gateway_url": {"type": "string", "description": _advanced_description("Gateway base URL.")},
            "gateway_auth_token_env": {"type": "string", "description": _advanced_description("Gateway bearer token을 읽을 환경 변수 이름.")},
            "gateway_timeout_ms": {"type": "integer", "minimum": 1, "description": _advanced_description("Gateway request timeout in milliseconds.")},
        },
        "additionalProperties": False,
    }


def _build_doctor_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "unity_project_path": {"type": "string", "description": "Unity 프로젝트 루트 경로. 주면 기본 catalog 경로를 함께 진단한다."},
            "catalog": {"type": "string", "description": "resource_catalog.jsonl 경로. unity_project_path가 있으면 상대 경로도 허용한다."},
            "reference_image": {"type": "string", "description": "선택적 reference image 경로."},
            "resolved_blueprint": {"type": "string", "description": "선택적 resolved blueprint JSON 경로."},
            "unity_mcp_url": {"type": "string", "description": "Unity MCP HTTP Local URL. 생략 시 unity_project_path가 있으면 기본값 `http://127.0.0.1:8080/mcp`를 가정한다."},
            "unity_mcp_timeout_ms": {"type": "integer", "minimum": 1, "description": "Unity MCP HTTP Local probe timeout in milliseconds."},
            "connection_preset": {"type": "string", "enum": CONNECTION_PRESET_ENUM, "description": CONNECTION_PRESET_DESCRIPTION},
            "provider": {"type": "string", "enum": PROVIDER_ENUM, "description": PROVIDER_DESCRIPTION},
            "provider_base_url": {"type": "string", "description": _advanced_description("사용자 지정 OpenAI-compatible endpoint나 base URL override.")},
            "provider_api_key_env": {"type": "string", "description": _advanced_description("API key를 읽을 환경 변수 이름.")},
            "auth_mode": {"type": "string", "enum": ["api_key", "oauth_token"], "description": _advanced_description("API-backed provider 인증 방식.")},
            "oauth_token_env": {"type": "string", "description": _advanced_description("OAuth bearer token을 읽을 환경 변수 이름.")},
            "oauth_token_file": {"type": "string", "description": _advanced_description("OAuth bearer token이 들어 있는 파일 경로.")},
            "oauth_token_command": {"type": "string", "description": _advanced_description("OAuth bearer token을 stdout으로 출력하는 명령.")},
            "codex_auth_file": {"type": "string", "description": _advanced_description("Codex OAuth auth.json 파일 경로.")},
            "gateway_url": {"type": "string", "description": _advanced_description("Gateway base URL.")},
            "gateway_auth_token_env": {"type": "string", "description": _advanced_description("Gateway bearer token을 읽을 환경 변수 이름.")},
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
            "provider_base_url": {"type": "string", "description": _advanced_description("사용자 지정 OpenAI-compatible endpoint나 base URL override.")},
            "provider_api_key_env": {"type": "string", "description": _advanced_description("API key를 읽을 환경 변수 이름.")},
            "auth_mode": {"type": "string", "enum": ["api_key", "oauth_token"], "description": _advanced_description("API-backed provider 인증 방식.")},
            "oauth_token_env": {"type": "string", "description": _advanced_description("OAuth bearer token을 읽을 환경 변수 이름.")},
            "oauth_token_file": {"type": "string", "description": _advanced_description("OAuth bearer token이 들어 있는 파일 경로.")},
            "oauth_token_command": {"type": "string", "description": _advanced_description("OAuth bearer token을 stdout으로 출력하는 명령.")},
            "codex_auth_file": {"type": "string", "description": _advanced_description("Codex OAuth auth.json 파일 경로.")},
            "gateway_url": {"type": "string", "description": _advanced_description("Gateway base URL.")},
            "gateway_auth_token_env": {"type": "string", "description": _advanced_description("Gateway bearer token을 읽을 환경 변수 이름.")},
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
    missing_settings = payload.get("missingSettings") or ["없음"]
    next_actions = payload.get("nextActions") or ["없음"]
    return "\n".join([
        f"현재 권장 선택: {payload['recommendedChoice']}",
        f"실제로 해석된 provider: {payload['resolvedProvider']}",
        f"토큰 소스: {payload['tokenSourceSummary']}",
        "누락된 설정:",
        *[f"- {item}" for item in missing_settings],
        "다음 액션:",
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


def _http_json_request(url: str, method: str, params: dict[str, Any] | None, timeout_ms: int, request_id: int) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params or {},
    }
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib_request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=max(timeout_ms / 1000.0, 1.0)) as response:
            raw = response.read().decode("utf-8")
    except (urllib_error.URLError, urllib_error.HTTPError) as exc:
        raise ToolExecutionError(f"Unity MCP request failed: {exc}") from exc

    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ToolExecutionError(
            "Unity MCP returned invalid JSON.",
            details={"rawResponse": raw},
        ) from exc

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
    token_source_summary = "불필요 (local_heuristic)" if inspection.resolved_provider == "local_heuristic" else "미확인"
    if inspection.auth_mode == "api_key":
        token_source_summary = f"API key 환경 변수 `{inspection.provider_api_key_env}`"
    elif inspection.resolved_provider == "gateway" and inspection.token_source_detail:
        token_source_summary = f"선택적 gateway bearer env `{inspection.token_source_detail}`"
    elif inspection.token_source == "env" and inspection.token_source_detail:
        token_source_summary = f"환경 변수 `{inspection.token_source_detail}`"
    elif inspection.token_source == "file" and inspection.token_source_detail:
        token_source_summary = f"토큰 파일 `{inspection.token_source_detail}`"
    elif inspection.token_source == "command" and inspection.token_source_detail:
        token_source_summary = f"토큰 명령 `{inspection.token_source_detail}`"
    elif inspection.token_source == "codex_file" and inspection.token_source_detail:
        token_source_summary = f"Codex 로그인 파일 `{inspection.token_source_detail}`"

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
        raise ToolExecutionError("`catalog` 또는 `unity_project_path`가 필요합니다.")

    apply_in_unity = bool(args.get("apply_in_unity", True))
    validate_before_apply = bool(args.get("validate_before_apply", True))
    force_reindex = bool(args.get("force_reindex", False))

    unity_mcp_url = str(args.get("unity_mcp_url") or DEFAULT_UNITY_MCP_URL)
    unity_mcp_timeout_ms = int(args.get("unity_mcp_timeout_ms") or DEFAULT_UNITY_MCP_TIMEOUT_MS)
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
            )
        apply_result = _call_unity_mcp_tool(
            unity_mcp_url,
            available_tools,
            "apply_ui_blueprint",
            {"action": "apply", "blueprintPath": resolved_blueprint},
            unity_mcp_timeout_ms,
        )

    next_actions: list[str] = []
    verify_request = ((handoff_payload or {}).get("requests") or {}).get("verify")
    if verify_request:
        next_actions.append("적용 후 `manage_camera` screenshot 요청으로 첫 결과를 캡처합니다.")
    next_actions.append("결과가 다르면 `unity_rag.run_verification_repair_loop`로 repair handoff를 생성합니다.")

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
        name="unity_rag.doctor",
        description="현재 설정과 로컬 실행 환경을 한 번에 진단한다. provider/auth, Unity 프로젝트 경로, catalog 존재 여부, gateway health, Unity MCP HTTP Local custom tool/resource 노출 상태를 함께 점검한다.",
        input_schema=_build_doctor_schema(),
        handler=doctor,
    ),
    ToolSpec(
        name="unity_rag.inspect_provider_setup",
        description="실제 workflow 실행 전 provider/auth 설정만 진단한다. 처음 연결할 때는 이 tool로 권장 preset, 해석된 provider, 토큰 소스, 누락된 설정, 다음 액션을 먼저 확인하는 것이 좋다.",
        input_schema=_build_inspect_provider_setup_schema(),
        handler=inspect_provider_setup,
    ),
    ToolSpec(
        name="unity_rag.run_first_pass_ui_build",
        description="첫 성공 경로를 한 번에 실행한다. catalog가 없으면 Unity에서 `index_project_resources`를 호출하고, sidecar workflow로 resolved blueprint를 만든 뒤, Unity의 `apply_ui_blueprint` validate/apply까지 이어서 실행한다.",
        input_schema=_build_run_first_pass_ui_build_schema(),
        handler=run_first_pass_ui_build,
    ),
    ToolSpec(
        name="unity_rag.extract_reference_layout",
        description="레퍼런스 이미지에서 reference layout plan JSON을 추출한다. 처음 설정할 때는 `connection_preset=recommended_auto`를 고르는 것이 권장되고, Codex OAuth를 확실히 쓰고 싶으면 `codex_oauth`, 완전 오프라인 점검이면 `offline_local`을 고르면 된다.",
        input_schema=_build_extract_reference_layout_schema(),
        handler=extract_reference_layout,
    ),
    ToolSpec(
        name="unity_rag.run_reference_to_resolved_blueprint",
        description="레퍼런스 이미지 또는 기존 reference layout에서 시작해 resolved blueprint와 MCP handoff bundle까지 전체 workflow를 실행한다. 처음 설정할 때는 `connection_preset=recommended_auto`를 권장하며, OpenAI 키는 `openai_api_key`, Gemini 키는 `gemini_api_key`, Claude는 `claude_api_key` 또는 `claude_code`를 고르면 된다.",
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
