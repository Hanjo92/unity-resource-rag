from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

if __package__ in (None, ""):
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from pipeline.mcp.tools import TOOL_BY_NAME, TOOLS, ToolExecutionError
else:
    from .tools import TOOL_BY_NAME, TOOLS, ToolExecutionError


SUPPORTED_PROTOCOL_VERSIONS = [
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
]


@dataclass
class JsonRpcRequest:
    method: str
    params: dict[str, Any]
    id: Any


class ProtocolError(RuntimeError):
    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.data = data or {}


def _write_message(message: dict[str, Any]) -> None:
    payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def _read_headers() -> dict[str, str] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        stripped = line.strip()
        if not stripped:
            return headers
        decoded = stripped.decode("utf-8", errors="replace")
        if ":" not in decoded:
            continue
        key, value = decoded.split(":", 1)
        headers[key.strip().lower()] = value.strip()


def _read_message() -> dict[str, Any] | None:
    headers = _read_headers()
    if headers is None:
        return None
    if "content-length" not in headers:
        return None

    length = int(headers["content-length"])
    body = sys.stdin.buffer.read(length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _protocol_result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def _protocol_error(request_id: Any, code: int, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if data:
        error["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": error,
    }


def _supports_version(requested: str) -> str:
    if requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return SUPPORTED_PROTOCOL_VERSIONS[0]


def _handle_initialize(request: JsonRpcRequest) -> dict[str, Any]:
    params = request.params or {}
    requested = str(params.get("protocolVersion") or SUPPORTED_PROTOCOL_VERSIONS[0])
    negotiated = _supports_version(requested)
    if requested not in SUPPORTED_PROTOCOL_VERSIONS:
        print(f"[mcp] requested unsupported protocolVersion={requested}, using {negotiated}", file=sys.stderr)
    return _protocol_result(
        request.id,
        {
            "protocolVersion": negotiated,
            "capabilities": {
                "tools": {
                    "listChanged": True,
                },
                "logging": {},
            },
            "serverInfo": {
                "name": "unity-resource-rag-pipeline-mcp",
                "version": "0.4.0-beta",
            },
            "instructions": "Use the Unity Resource RAG pipeline tools to extract layouts, bind assets, build handoff bundles, and verify screenshots.",
        },
    )


def _handle_tools_list(request: JsonRpcRequest) -> dict[str, Any]:
    return _protocol_result(
        request.id,
        {
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.input_schema,
                }
                for tool in TOOLS
            ]
        },
    )


def _handle_tools_call(request: JsonRpcRequest) -> dict[str, Any]:
    params = request.params or {}
    name = str(params.get("name") or "")
    tool = TOOL_BY_NAME.get(name)
    if tool is None:
        raise ProtocolError(-32602, f"Unknown tool: {name}", {"tool": name})

    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ProtocolError(-32602, "Tool arguments must be an object.", {"tool": name})

    try:
        result = tool.handler(arguments)
    except ToolExecutionError as exc:
        return _protocol_result(request.id, exc.details | {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({
                        "error": str(exc),
                        "details": exc.details or None,
                    }, ensure_ascii=False, indent=2),
                }
            ],
            "isError": True,
        })
    except Exception as exc:
        return _protocol_result(request.id, {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps({
                        "error": f"Unhandled tool failure: {exc}",
                    }, ensure_ascii=False, indent=2),
                }
            ],
            "isError": True,
        })

    return _protocol_result(request.id, result)


def _handle_ping(request: JsonRpcRequest) -> dict[str, Any]:
    return _protocol_result(request.id, {})


def _dispatch(request: JsonRpcRequest) -> dict[str, Any] | None:
    if request.method == "initialize":
        return _handle_initialize(request)
    if request.method == "initialized":
        return None
    if request.method == "ping":
        return _handle_ping(request)
    if request.method == "tools/list":
        return _handle_tools_list(request)
    if request.method == "tools/call":
        return _handle_tools_call(request)
    raise ProtocolError(-32601, f"Method not found: {request.method}")


def serve() -> int:
    while True:
        raw = _read_message()
        if raw is None:
            return 0

        try:
            request = JsonRpcRequest(
                method=str(raw.get("method") or ""),
                params=raw.get("params") or {},
                id=raw.get("id"),
            )
            response = _dispatch(request)
            if response is not None and request.id is not None:
                _write_message(response)
        except ProtocolError as exc:
            _write_message(_protocol_error(raw.get("id"), exc.code, str(exc), exc.data))
        except Exception as exc:
            _write_message(_protocol_error(raw.get("id"), -32603, f"Internal error: {exc}"))


def main() -> int:
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
