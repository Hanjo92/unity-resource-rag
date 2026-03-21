from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

if __package__ in (None, ""):
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from pipeline.planner.extract_reference_layout import (
        DEFAULT_DETAIL,
        DEFAULT_MAX_IMAGE_DIM,
        DEFAULT_MODEL,
        ProviderConfig,
        inspect_provider_setup as inspect_provider_setup_config,
    )
else:
    from ..planner.extract_reference_layout import (
        DEFAULT_DETAIL,
        DEFAULT_MAX_IMAGE_DIM,
        DEFAULT_MODEL,
        ProviderConfig,
        inspect_provider_setup as inspect_provider_setup_config,
    )


DEFAULT_UNITY_MCP_URL = "http://127.0.0.1:8080/mcp"
DEFAULT_UNITY_MCP_TIMEOUT_MS = 3000
DEFAULT_CATALOG_RELATIVE_PATH = Path("Library/ResourceRag/resource_catalog.jsonl")
EXPECTED_UNITY_TOOLS = ("index_project_resources", "apply_ui_blueprint")
EXPECTED_UNITY_RESOURCES = ("ui_asset_catalog",)


@dataclass(frozen=True)
class DoctorCheck:
    key: str
    status: str
    summary: str
    details: dict[str, Any]
    next_actions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "status": self.status,
            "summary": self.summary,
            "details": self.details,
            "nextActions": self.next_actions,
        }


def _resolve_optional_path(raw: Any) -> Path | None:
    if raw in (None, ""):
        return None
    return Path(str(raw)).expanduser().resolve()


def _resolve_catalog_path(raw_catalog: Any, project_path: Path | None) -> Path | None:
    if raw_catalog not in (None, ""):
        raw_path = Path(str(raw_catalog)).expanduser()
        if project_path is not None and not raw_path.is_absolute():
            return (project_path / raw_path).resolve()
        return raw_path.resolve()
    if project_path is None:
        return None
    return (project_path / DEFAULT_CATALOG_RELATIVE_PATH).resolve()


def _build_provider_config(args: dict[str, Any]) -> ProviderConfig:
    return ProviderConfig(
        provider=str(args.get("provider") or "auto"),
        screen_name="doctor",
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


def _token_source_summary(inspection: Any) -> str:
    if inspection.resolved_provider == "local_heuristic":
        return "불필요 (local_heuristic)"
    if inspection.auth_mode == "api_key":
        return f"API key 환경 변수 `{inspection.provider_api_key_env}`"
    if inspection.resolved_provider == "gateway" and inspection.token_source_detail:
        return f"선택적 gateway bearer env `{inspection.token_source_detail}`"
    if inspection.token_source == "env" and inspection.token_source_detail:
        return f"환경 변수 `{inspection.token_source_detail}`"
    if inspection.token_source == "file" and inspection.token_source_detail:
        return f"토큰 파일 `{inspection.token_source_detail}`"
    if inspection.token_source == "command" and inspection.token_source_detail:
        return f"토큰 명령 `{inspection.token_source_detail}`"
    if inspection.token_source == "codex_file" and inspection.token_source_detail:
        return f"Codex 로그인 파일 `{inspection.token_source_detail}`"
    return "미확인"


def _check_provider_setup(args: dict[str, Any]) -> DoctorCheck:
    inspection = inspect_provider_setup_config(_build_provider_config(args))
    details = {
        "requestedProvider": inspection.requested_provider,
        "resolvedProvider": inspection.resolved_provider,
        "authMode": inspection.auth_mode,
        "providerBaseUrl": inspection.provider_base_url,
        "providerApiKeyEnv": inspection.provider_api_key_env,
        "tokenSource": inspection.token_source,
        "tokenSourceDetail": inspection.token_source_detail,
        "tokenSourceSummary": _token_source_summary(inspection),
        "recommendedChoice": inspection.recommended_choice,
        "missingSettings": inspection.missing_settings,
        "nextActions": inspection.next_actions,
        "summary": inspection.summary,
    }
    if inspection.missing_settings:
        return DoctorCheck(
            key="provider_setup",
            status="warn",
            summary=f"provider 설정에 추가 입력이 필요합니다 ({inspection.resolved_provider}).",
            details=details,
            next_actions=list(inspection.next_actions),
        )
    return DoctorCheck(
        key="provider_setup",
        status="ok",
        summary=f"provider 설정이 실행 가능한 상태입니다 ({inspection.resolved_provider}).",
        details=details,
        next_actions=[],
    )


def _check_unity_project(project_path: Path | None) -> DoctorCheck:
    if project_path is None:
        return DoctorCheck(
            key="unity_project",
            status="skipped",
            summary="Unity 프로젝트 경로가 없어 프로젝트 구조 검사를 건너뜁니다.",
            details={},
            next_actions=[],
        )
    if not project_path.exists():
        return DoctorCheck(
            key="unity_project",
            status="error",
            summary="Unity 프로젝트 경로를 찾을 수 없습니다.",
            details={"unityProjectPath": str(project_path)},
            next_actions=["`unity_project_path`에 실제 Unity 프로젝트 루트를 넣습니다."],
        )
    if not project_path.is_dir():
        return DoctorCheck(
            key="unity_project",
            status="error",
            summary="Unity 프로젝트 경로가 디렉터리가 아닙니다.",
            details={"unityProjectPath": str(project_path)},
            next_actions=["`unity_project_path`에 실제 Unity 프로젝트 루트를 넣습니다."],
        )

    missing_dirs = [
        name
        for name in ("Assets", "ProjectSettings", "Packages")
        if not (project_path / name).is_dir()
    ]
    if missing_dirs:
        return DoctorCheck(
            key="unity_project",
            status="error",
            summary="Unity 프로젝트 기본 폴더 구조가 아닙니다.",
            details={"unityProjectPath": str(project_path), "missingDirectories": missing_dirs},
            next_actions=["`Assets`, `Packages`, `ProjectSettings`가 있는 Unity 프로젝트 루트를 지정합니다."],
        )

    return DoctorCheck(
        key="unity_project",
        status="ok",
        summary="Unity 프로젝트 구조가 확인되었습니다.",
        details={"unityProjectPath": str(project_path)},
        next_actions=[],
    )


def _load_catalog_stats(catalog_path: Path) -> dict[str, Any]:
    asset_counts: Counter[str] = Counter()
    sample: list[dict[str, Any]] = []
    record_count = 0

    with catalog_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc

            record_count += 1
            asset_type = str(record.get("assetType") or "Unknown")
            asset_counts[asset_type] += 1
            if len(sample) < 5:
                sample.append(
                    {
                        "name": record.get("name"),
                        "assetType": asset_type,
                        "path": record.get("path"),
                    }
                )

    return {
        "recordCount": record_count,
        "assetCounts": dict(sorted(asset_counts.items())),
        "sample": sample,
    }


def _check_catalog(catalog_path: Path | None, project_path: Path | None) -> DoctorCheck:
    if catalog_path is None:
        return DoctorCheck(
            key="catalog",
            status="skipped",
            summary="카탈로그 경로가 없어 catalog 검사를 건너뜁니다.",
            details={},
            next_actions=[],
        )
    if not catalog_path.exists():
        next_actions = ["Unity에서 `index_project_resources`를 실행해 카탈로그를 생성합니다."]
        if project_path is None:
            next_actions.append("`catalog` 또는 `unity_project_path`를 넘겨 기본 catalog 경로를 추론할 수 있게 합니다.")
        return DoctorCheck(
            key="catalog",
            status="warn",
            summary="카탈로그 파일을 찾지 못했습니다.",
            details={"catalogPath": str(catalog_path)},
            next_actions=next_actions,
        )

    try:
        stats = _load_catalog_stats(catalog_path)
    except ValueError as exc:
        return DoctorCheck(
            key="catalog",
            status="error",
            summary="카탈로그 파일은 있지만 읽을 수 없습니다.",
            details={"catalogPath": str(catalog_path), "error": str(exc)},
            next_actions=["Unity에서 `index_project_resources`를 다시 실행해 카탈로그를 재생성합니다."],
        )

    if stats["recordCount"] == 0:
        return DoctorCheck(
            key="catalog",
            status="warn",
            summary="카탈로그가 비어 있습니다.",
            details={"catalogPath": str(catalog_path), **stats},
            next_actions=["프로젝트에 실제 UI 자산이 포함되어 있는지 확인하고 `index_project_resources`를 다시 실행합니다."],
        )

    return DoctorCheck(
        key="catalog",
        status="ok",
        summary=f"카탈로그를 읽을 수 있습니다 (records={stats['recordCount']}).",
        details={"catalogPath": str(catalog_path), **stats},
        next_actions=[],
    )


def _check_file_path(key: str, label: str, raw_path: Any) -> DoctorCheck:
    path = _resolve_optional_path(raw_path)
    if path is None:
        return DoctorCheck(
            key=key,
            status="skipped",
            summary=f"{label} 경로가 없어 검사를 건너뜁니다.",
            details={},
            next_actions=[],
        )
    if not path.exists():
        return DoctorCheck(
            key=key,
            status="warn",
            summary=f"{label} 파일을 찾지 못했습니다.",
            details={"path": str(path)},
            next_actions=[f"`{key}`에 실제 {label} 파일 경로를 넣거나 파일 위치를 확인합니다."],
        )

    details: dict[str, Any] = {
        "path": str(path),
        "sizeBytes": path.stat().st_size,
    }
    if key == "resolved_blueprint":
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except json.JSONDecodeError as exc:
            return DoctorCheck(
                key=key,
                status="error",
                summary="resolved blueprint JSON을 파싱할 수 없습니다.",
                details={"path": str(path), "error": str(exc)},
                next_actions=["resolved blueprint를 다시 생성하거나 파일이 손상되지 않았는지 확인합니다."],
            )
        if isinstance(payload, dict):
            details["topLevelKeys"] = sorted(str(item) for item in payload.keys())

    return DoctorCheck(
        key=key,
        status="ok",
        summary=f"{label} 파일이 준비되어 있습니다.",
        details=details,
        next_actions=[],
    )


def _normalize_url(url: str) -> str:
    return url.rstrip("/")


def _load_json_response(request: urllib_request.Request, timeout_ms: int) -> dict[str, Any]:
    with urllib_request.urlopen(request, timeout=max(timeout_ms / 1000.0, 1.0)) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw or "{}")


def _check_gateway(args: dict[str, Any]) -> DoctorCheck:
    gateway_url = str(args.get("gateway_url") or "").strip()
    if not gateway_url:
        return DoctorCheck(
            key="gateway",
            status="skipped",
            summary="gateway URL이 없어 gateway 검사를 건너뜁니다.",
            details={},
            next_actions=[],
        )

    health_url = f"{_normalize_url(gateway_url)}/health"
    timeout_ms = int(args.get("gateway_timeout_ms") or 30000)
    request = urllib_request.Request(health_url, method="GET")

    try:
        payload = _load_json_response(request, timeout_ms)
    except (urllib_error.URLError, urllib_error.HTTPError, json.JSONDecodeError) as exc:
        return DoctorCheck(
            key="gateway",
            status="error",
            summary="gateway에 연결할 수 없습니다.",
            details={"gatewayUrl": gateway_url, "healthUrl": health_url, "error": str(exc)},
            next_actions=[
                "`python3 -m pipeline.gateway`로 gateway를 실행합니다.",
                "gateway URL과 포트가 맞는지 확인합니다.",
            ],
        )

    status = str(payload.get("status") or "")
    if status != "ok":
        return DoctorCheck(
            key="gateway",
            status="warn",
            summary="gateway는 응답했지만 health payload가 예상과 다릅니다.",
            details={"gatewayUrl": gateway_url, "healthUrl": health_url, "payload": payload},
            next_actions=["gateway 응답 payload와 실행 로그를 확인합니다."],
        )

    return DoctorCheck(
        key="gateway",
        status="ok",
        summary="gateway `/health` 응답이 정상입니다.",
        details={"gatewayUrl": gateway_url, "healthUrl": health_url, "payload": payload},
        next_actions=[],
    )


def _post_json_rpc(url: str, method: str, params: dict[str, Any] | None, timeout_ms: int, request_id: int) -> dict[str, Any]:
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
    response_payload = _load_json_response(request, timeout_ms)
    error_payload = response_payload.get("error")
    if error_payload:
        raise RuntimeError(str(error_payload))
    result = response_payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"Unexpected JSON-RPC result: {response_payload}")
    return result


def _inventory_identifiers(items: list[dict[str, Any]]) -> list[str]:
    identifiers: list[str] = []
    for item in items:
        for key in ("name", "uri", "title"):
            value = item.get(key)
            if value:
                identifiers.append(str(value))
    return sorted(dict.fromkeys(identifiers))


def _check_unity_mcp(args: dict[str, Any], project_path: Path | None) -> DoctorCheck:
    raw_url = args.get("unity_mcp_url")
    if raw_url in (None, "") and project_path is None:
        return DoctorCheck(
            key="unity_mcp",
            status="skipped",
            summary="Unity MCP URL이 없어 Unity MCP 검사를 건너뜁니다.",
            details={},
            next_actions=[],
        )

    unity_mcp_url = str(raw_url or DEFAULT_UNITY_MCP_URL)
    timeout_ms = int(args.get("unity_mcp_timeout_ms") or DEFAULT_UNITY_MCP_TIMEOUT_MS)

    try:
        tools_result = _post_json_rpc(unity_mcp_url, "tools/list", {}, timeout_ms, 1)
        resources_result = _post_json_rpc(unity_mcp_url, "resources/list", {}, timeout_ms, 2)
    except Exception as exc:
        return DoctorCheck(
            key="unity_mcp",
            status="warn",
            summary="Unity MCP HTTP Local에 연결할 수 없습니다.",
            details={"unityMcpUrl": unity_mcp_url, "error": str(exc)},
            next_actions=[
                "Unity에서 `Window > MCP for Unity`를 열고 Local HTTP Server를 시작합니다.",
                "클라이언트가 다른 포트를 쓰고 있다면 `unity_mcp_url`을 실제 URL로 맞춥니다.",
            ],
        )

    tool_names = sorted(
        str(item.get("name"))
        for item in tools_result.get("tools", [])
        if isinstance(item, dict) and item.get("name")
    )
    resource_ids = _inventory_identifiers(
        [
            item
            for item in resources_result.get("resources", [])
            if isinstance(item, dict)
        ]
    )

    missing_tools = [tool for tool in EXPECTED_UNITY_TOOLS if tool not in tool_names]
    missing_resources = [
        resource_name
        for resource_name in EXPECTED_UNITY_RESOURCES
        if not any(resource_name in identifier for identifier in resource_ids)
    ]
    project_scoped_symptom = "execute_custom_tool" in tool_names and missing_tools == list(EXPECTED_UNITY_TOOLS)

    details = {
        "unityMcpUrl": unity_mcp_url,
        "toolNames": tool_names,
        "resourceIdentifiers": resource_ids,
        "missingTools": missing_tools,
        "missingResources": missing_resources,
        "projectScopedSymptom": project_scoped_symptom,
    }

    if project_scoped_symptom:
        return DoctorCheck(
            key="unity_mcp",
            status="warn",
            summary="Unity MCP는 reachable하지만 custom tool이 직접 노출되지 않았습니다.",
            details=details,
            next_actions=[
                "Unity MCP HTTP Local에서 `Project Scoped Tools`를 끄고 Local HTTP Server를 다시 시작합니다.",
                "클라이언트에서 tool 목록을 다시 읽습니다.",
            ],
        )

    if missing_tools:
        return DoctorCheck(
            key="unity_mcp",
            status="warn",
            summary="Unity MCP에 필요한 custom tool 일부가 보이지 않습니다.",
            details=details,
            next_actions=[
                "Unity에서 `index_project_resources`와 `apply_ui_blueprint`가 등록됐는지 확인합니다.",
                "필요하면 Local HTTP Server를 다시 시작하고 tool 목록을 다시 읽습니다.",
            ],
        )

    if missing_resources:
        return DoctorCheck(
            key="unity_mcp",
            status="warn",
            summary="Unity MCP tool은 보이지만 `ui_asset_catalog` resource가 확인되지 않았습니다.",
            details=details,
            next_actions=[
                "resource 목록에서 `ui_asset_catalog`가 노출되는지 확인합니다.",
                "패키지 로딩 후 Unity MCP Local HTTP Server를 다시 시작합니다.",
            ],
        )

    return DoctorCheck(
        key="unity_mcp",
        status="ok",
        summary="Unity MCP가 필요한 custom tool과 resource를 직접 노출하고 있습니다.",
        details=details,
        next_actions=[],
    )


def _overall_status(checks: list[DoctorCheck]) -> str:
    statuses = {check.status for check in checks}
    if "error" in statuses:
        return "error"
    if "warn" in statuses:
        return "warn"
    if "ok" in statuses:
        return "ok"
    return "skipped"


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def build_doctor_payload(args: dict[str, Any]) -> dict[str, Any]:
    project_path = _resolve_optional_path(args.get("unity_project_path"))
    catalog_path = _resolve_catalog_path(args.get("catalog"), project_path)

    checks = [
        _check_provider_setup(args),
        _check_unity_project(project_path),
        _check_catalog(catalog_path, project_path),
        _check_file_path("reference_image", "reference image", args.get("reference_image") or args.get("image")),
        _check_file_path("resolved_blueprint", "resolved blueprint", args.get("resolved_blueprint")),
        _check_gateway(args),
        _check_unity_mcp(args, project_path),
    ]

    next_actions = _dedupe(
        [
            action
            for check in checks
            if check.status in {"warn", "error"}
            for action in check.next_actions
        ]
    )

    return {
        "overallStatus": _overall_status(checks),
        "detectedPaths": {
            "unityProjectPath": str(project_path) if project_path else None,
            "catalogPath": str(catalog_path) if catalog_path else None,
            "gatewayUrl": str(args.get("gateway_url")) if args.get("gateway_url") else None,
            "unityMcpUrl": str(args.get("unity_mcp_url") or DEFAULT_UNITY_MCP_URL) if (args.get("unity_mcp_url") or project_path) else None,
        },
        "checks": [check.to_dict() for check in checks],
        "nextActions": next_actions,
    }
