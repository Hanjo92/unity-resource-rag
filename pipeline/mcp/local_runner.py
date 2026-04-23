from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

if __package__ in (None, ""):
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from pipeline.mcp.doctor import DEFAULT_UNITY_MCP_URL, build_doctor_payload
    from pipeline.mcp.tools import ToolExecutionError, _decode_mcp_tool_result, _extract_wrapped_payload, run_verification_repair_loop, start_ui_build
    from pipeline.mcp.unity_http import UnityMcpHttpError, get_unity_http_client
else:
    from .doctor import DEFAULT_UNITY_MCP_URL, build_doctor_payload
    from .tools import ToolExecutionError, _decode_mcp_tool_result, _extract_wrapped_payload, run_verification_repair_loop, start_ui_build
    from .unity_http import UnityMcpHttpError, get_unity_http_client


ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


def _format_exception_message(exc: Exception) -> str:
    message = str(exc).strip()
    type_name = type(exc).__name__
    if not message:
        return type_name
    return f"{type_name}: {message}"


def _load_payload(payload_file: str | None, payload_json: str | None) -> dict[str, Any]:
    if payload_file:
        raw = Path(payload_file).expanduser().read_text(encoding="utf-8")
    elif payload_json:
        raw = payload_json
    else:
        raw = "{}"

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object.")
    return payload


def _doctor_tool(args: dict[str, Any]) -> dict[str, Any]:
    return build_doctor_payload(args)


def _start_ui_build_tool(args: dict[str, Any]) -> dict[str, Any]:
    result = start_ui_build(args)
    return _extract_wrapped_payload(result)


def _resolve_project_path(raw_path: Any) -> Path | None:
    if raw_path in (None, ""):
        return None
    return Path(str(raw_path)).expanduser().resolve()


def _resolve_captured_path(path_value: Any, unity_project_path: Path | None) -> str | None:
    raw_path = str(path_value or "").strip()
    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    if not path.is_absolute() and unity_project_path is not None:
        path = (unity_project_path / raw_path).resolve()
    else:
        path = path.resolve()
    return str(path)


def _capture_result_tool(args: dict[str, Any]) -> dict[str, Any]:
    unity_mcp_url = str(args.get("unity_mcp_url") or DEFAULT_UNITY_MCP_URL)
    timeout_ms = int(args.get("unity_mcp_timeout_ms") or 30000)
    unity_project_path = _resolve_project_path(args.get("unity_project_path"))

    verify_request = args.get("verify_request")
    if verify_request is not None and not isinstance(verify_request, dict):
        raise ToolExecutionError("`verify_request` must be a JSON object.")

    request_tool = str((verify_request or {}).get("tool") or args.get("tool_name") or "manage_camera")
    request_arguments = dict((verify_request or {}).get("parameters") or {})
    if not request_arguments:
        request_arguments = {
            key: value
            for key, value in args.items()
            if key
            in {
                "action",
                "capture_source",
                "view_target",
                "camera_name",
                "include_image",
                "includeImage",
                "max_resolution",
                "maxResolution",
                "file_name",
                "fileName",
            }
            and value not in (None, "")
        }

    if not request_arguments:
        raise ToolExecutionError("Capture requires `verify_request` or screenshot arguments such as `view_target`.")

    request_arguments.setdefault("action", "screenshot")
    request_arguments.setdefault("include_image", bool(args.get("include_image", False)))

    try:
        response_payload = get_unity_http_client(unity_mcp_url, timeout_ms).request(
            "tools/call",
            {"name": request_tool, "arguments": request_arguments},
            1,
        )
    except UnityMcpHttpError as exc:
        raise ToolExecutionError(str(exc), details={"responseText": exc.response_text} if exc.response_text else {}) from exc

    if response_payload.get("error"):
        raise ToolExecutionError(
            "Unity MCP returned an error while capturing a screenshot.",
            details={"unityMcpError": response_payload["error"]},
        )

    result = response_payload.get("result")
    if not isinstance(result, dict):
        raise ToolExecutionError(
            "Unity MCP returned an unexpected screenshot result.",
            details={"unityMcpResponse": response_payload},
        )

    payload = _decode_mcp_tool_result(result)
    if payload.get("success") is False:
        raise ToolExecutionError(
            f"Unity tool `{request_tool}` failed: {payload.get('error') or payload.get('message') or 'unknown error'}",
            details={"unityResponse": payload},
        )

    response_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    captured_relative_path = response_data.get("path") or payload.get("path")
    captured_path = _resolve_captured_path(captured_relative_path, unity_project_path)
    return {
        "tool": request_tool,
        "request": request_arguments,
        "response": payload,
        "capturedPath": captured_path,
        "capturedPathRelative": captured_relative_path,
        "screenshotsFolder": response_data.get("screenshotsFolder"),
    }


def _run_verification_repair_tool(args: dict[str, Any]) -> dict[str, Any]:
    result = run_verification_repair_loop(args)
    return _extract_wrapped_payload(result)


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "doctor": _doctor_tool,
    "capture_result": _capture_result_tool,
    "run_verification_repair_loop": _run_verification_repair_tool,
    "start_ui_build": _start_ui_build_tool,
}


def run_tool(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return {
            "ok": False,
            "tool": tool_name,
            "error": f"Unsupported tool: {tool_name}",
        }

    try:
        payload = handler(args)
    except ToolExecutionError as exc:
        return {
            "ok": False,
            "tool": tool_name,
            "error": str(exc),
            "details": exc.details,
        }
    except Exception as exc:  # pragma: no cover - defensive fallback for Unity-side logs
        return {
            "ok": False,
            "tool": tool_name,
            "error": _format_exception_message(exc),
        }

    return {
        "ok": True,
        "tool": tool_name,
        "payload": payload,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local CLI bridge for Unity Resource RAG editor tooling.")
    parser.add_argument("tool", choices=sorted(TOOL_HANDLERS))
    parser.add_argument("--payload-file", help="Path to a JSON file containing tool arguments.")
    parser.add_argument("--payload-json", help="Inline JSON object containing tool arguments.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(argv)

    try:
        payload = _load_payload(parsed.payload_file, parsed.payload_json)
        result = run_tool(parsed.tool, payload)
    except Exception as exc:
        result = {
            "ok": False,
            "tool": getattr(parsed, "tool", "unknown"),
            "error": _format_exception_message(exc),
        }

    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
