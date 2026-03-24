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
    from pipeline.mcp.unity_http import UnityMcpHttpError, get_unity_http_client
    from pipeline.planner.extract_reference_layout import (
        DEFAULT_DETAIL,
        DEFAULT_MAX_IMAGE_DIM,
        DEFAULT_MODEL,
        ProviderConfig,
        inspect_provider_setup as inspect_provider_setup_config,
    )
else:
    from .unity_http import UnityMcpHttpError, get_unity_http_client
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
REQUIRED_UNITY_BUILD_TOOLS = ("index_project_resources", "apply_ui_blueprint")
OPTIONAL_UNITY_TOOLS = ("query_ui_asset_catalog",)
OPTIONAL_UNITY_RESOURCES = ("ui_asset_catalog",)


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
        return "Not needed (local_heuristic)"
    if inspection.auth_mode == "api_key":
        return f"API key environment variable `{inspection.provider_api_key_env}`"
    if inspection.resolved_provider == "gateway" and inspection.token_source_detail:
        return f"Optional gateway bearer env `{inspection.token_source_detail}`"
    if inspection.token_source == "env" and inspection.token_source_detail:
        return f"Environment variable `{inspection.token_source_detail}`"
    if inspection.token_source == "file" and inspection.token_source_detail:
        return f"Token file `{inspection.token_source_detail}`"
    if inspection.token_source == "command" and inspection.token_source_detail:
        return f"Token command `{inspection.token_source_detail}`"
    if inspection.token_source == "codex_file" and inspection.token_source_detail:
        return f"Codex sign-in file `{inspection.token_source_detail}`"
    return "Unknown"


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
            summary=f"Provider setup needs additional input ({inspection.resolved_provider}).",
            details=details,
            next_actions=list(inspection.next_actions),
        )
    return DoctorCheck(
        key="provider_setup",
        status="ok",
        summary=f"Provider setup is ready to run ({inspection.resolved_provider}).",
        details=details,
        next_actions=[],
    )


def _check_unity_project(project_path: Path | None) -> DoctorCheck:
    if project_path is None:
        return DoctorCheck(
            key="unity_project",
            status="skipped",
            summary="Skipped project structure checks because no Unity project path was provided.",
            details={},
            next_actions=[],
        )
    if not project_path.exists():
        return DoctorCheck(
            key="unity_project",
            status="error",
            summary="The Unity project path could not be found.",
            details={"unityProjectPath": str(project_path)},
            next_actions=["Set `unity_project_path` to the actual Unity project root."],
        )
    if not project_path.is_dir():
        return DoctorCheck(
            key="unity_project",
            status="error",
            summary="The Unity project path is not a directory.",
            details={"unityProjectPath": str(project_path)},
            next_actions=["Set `unity_project_path` to the actual Unity project root."],
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
            summary="The path does not look like a Unity project root.",
            details={"unityProjectPath": str(project_path), "missingDirectories": missing_dirs},
            next_actions=["Point to a Unity project root that contains `Assets`, `Packages`, and `ProjectSettings`."],
        )

    return DoctorCheck(
        key="unity_project",
        status="ok",
        summary="The Unity project structure looks valid.",
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
            summary="Skipped the catalog check because no catalog path was available.",
            details={},
            next_actions=[],
        )
    if not catalog_path.exists():
        next_actions = ["Run `index_project_resources` in Unity to generate the catalog."]
        if project_path is None:
            next_actions.append("Pass `catalog` or `unity_project_path` so the default catalog path can be inferred.")
        return DoctorCheck(
            key="catalog",
            status="warn",
            summary="The catalog file could not be found.",
            details={"catalogPath": str(catalog_path)},
            next_actions=next_actions,
        )

    try:
        stats = _load_catalog_stats(catalog_path)
    except ValueError as exc:
        return DoctorCheck(
            key="catalog",
            status="error",
            summary="The catalog file exists but could not be read.",
            details={"catalogPath": str(catalog_path), "error": str(exc)},
            next_actions=["Re-run `index_project_resources` in Unity to regenerate the catalog."],
        )

    if stats["recordCount"] == 0:
        return DoctorCheck(
            key="catalog",
            status="warn",
            summary="The catalog exists but is empty.",
            details={"catalogPath": str(catalog_path), **stats},
            next_actions=["Check that the project contains real UI assets, then re-run `index_project_resources`."],
        )

    return DoctorCheck(
        key="catalog",
        status="ok",
        summary=f"The catalog can be read (records={stats['recordCount']}).",
        details={"catalogPath": str(catalog_path), **stats},
        next_actions=[],
    )


def _check_file_path(key: str, label: str, raw_path: Any) -> DoctorCheck:
    path = _resolve_optional_path(raw_path)
    if path is None:
        return DoctorCheck(
            key=key,
            status="skipped",
            summary=f"Skipped this check because no {label} path was provided.",
            details={},
            next_actions=[],
        )
    if not path.exists():
        return DoctorCheck(
            key=key,
            status="warn",
            summary=f"The {label} file could not be found.",
            details={"path": str(path)},
            next_actions=[f"Set `{key}` to the actual {label} file path or verify the file location."],
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
                summary="The resolved blueprint JSON could not be parsed.",
                details={"path": str(path), "error": str(exc)},
                next_actions=["Regenerate the resolved blueprint or confirm that the file is not corrupted."],
            )
        if isinstance(payload, dict):
            details["topLevelKeys"] = sorted(str(item) for item in payload.keys())

    return DoctorCheck(
        key=key,
        status="ok",
        summary=f"The {label} file is available.",
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
            summary="Skipped the gateway check because no gateway URL was provided.",
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
            summary="The gateway could not be reached.",
            details={"gatewayUrl": gateway_url, "healthUrl": health_url, "error": str(exc)},
            next_actions=[
                "Start the gateway with `python3 -m pipeline.gateway`.",
                "Confirm that the gateway URL and port are correct.",
            ],
        )

    status = str(payload.get("status") or "")
    if status != "ok":
        return DoctorCheck(
            key="gateway",
            status="warn",
            summary="The gateway responded, but the health payload was not in the expected shape.",
            details={"gatewayUrl": gateway_url, "healthUrl": health_url, "payload": payload},
            next_actions=["Inspect the gateway health payload and runtime logs."],
        )

    return DoctorCheck(
        key="gateway",
        status="ok",
        summary="The gateway `/health` response looks healthy.",
        details={"gatewayUrl": gateway_url, "healthUrl": health_url, "payload": payload},
        next_actions=[],
    )


def _post_json_rpc(url: str, method: str, params: dict[str, Any] | None, timeout_ms: int, request_id: int) -> dict[str, Any]:
    try:
        response_payload = get_unity_http_client(url, timeout_ms).request(method, params, request_id)
    except UnityMcpHttpError as exc:
        raise RuntimeError(str(exc)) from exc
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
            summary="Skipped the Unity MCP check because no Unity MCP URL was available.",
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
            summary="Unity MCP HTTP Local could not be reached.",
            details={"unityMcpUrl": unity_mcp_url, "error": str(exc)},
            next_actions=[
                "Open `Window > MCP for Unity` in Unity and start the Local HTTP Server.",
                "If the client uses a different port, update `unity_mcp_url` to the actual URL.",
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

    missing_tools = [tool for tool in REQUIRED_UNITY_BUILD_TOOLS if tool not in tool_names]
    missing_optional_tools = [tool for tool in OPTIONAL_UNITY_TOOLS if tool not in tool_names]
    missing_resources = [
        resource_name
        for resource_name in OPTIONAL_UNITY_RESOURCES
        if not any(resource_name in identifier for identifier in resource_ids)
    ]
    project_scoped_symptom = "execute_custom_tool" in tool_names and missing_tools == list(REQUIRED_UNITY_BUILD_TOOLS)
    menu_bridge_fallback = "execute_menu_item" in tool_names and bool(missing_tools)

    details = {
        "unityMcpUrl": unity_mcp_url,
        "toolNames": tool_names,
        "resourceIdentifiers": resource_ids,
        "missingTools": missing_tools,
        "missingOptionalTools": missing_optional_tools,
        "missingResources": missing_resources,
        "projectScopedSymptom": project_scoped_symptom,
        "menuBridgeFallback": menu_bridge_fallback,
    }

    if project_scoped_symptom:
        return DoctorCheck(
            key="unity_mcp",
            status="warn",
            summary="Unity MCP is reachable, but custom tools are not directly exposed.",
            details=details,
            next_actions=[
                "Turn off `Project Scoped Tools` in Unity MCP HTTP Local and restart the Local HTTP Server.",
                "Refresh the tool list in the client.",
            ],
        )

    if missing_tools:
        if menu_bridge_fallback:
            return DoctorCheck(
                key="unity_mcp",
                status="ok",
                summary="Unity MCP does not expose the custom build tools directly, but the execute_menu_item fallback is available.",
                details=details,
                next_actions=[
                    "You can continue with the Unity Resource RAG menu bridge fallback.",
                    "If you want direct exposure later, keep checking `index_project_resources` and `apply_ui_blueprint` in the tool list.",
                ],
            )

        return DoctorCheck(
            key="unity_mcp",
            status="warn",
            summary="Some required Unity MCP custom tools are still missing.",
            details=details,
            next_actions=[
                "Confirm that `index_project_resources` and `apply_ui_blueprint` are registered in Unity.",
                "If needed, restart the Local HTTP Server and refresh the tool list.",
            ],
        )

    if missing_optional_tools or missing_resources:
        return DoctorCheck(
            key="unity_mcp",
            status="ok",
            summary="Unity MCP exposes the required build tools. Optional catalog browsing endpoints are not fully visible.",
            details=details,
            next_actions=[
                "You can continue with build/apply even if `query_ui_asset_catalog` or `ui_asset_catalog` is not exposed.",
                "If you want catalog browsing support, check whether `query_ui_asset_catalog` and `ui_asset_catalog` are exposed after restarting the Local HTTP Server.",
            ],
        )

    return DoctorCheck(
        key="unity_mcp",
        status="ok",
        summary="Unity MCP is directly exposing the required build tools.",
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
