from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request


DEFAULT_MCP_PROTOCOL_VERSION = "2024-11-05"
STREAMABLE_HTTP_ACCEPT = "application/json, text/event-stream"
SESSION_HEADER = "mcp-session-id"


@dataclass
class UnityMcpHttpError(RuntimeError):
    message: str
    status_code: int | None = None
    response_text: str | None = None

    def __str__(self) -> str:
        return self.message


def _headers_get(headers: Any, name: str) -> str | None:
    if headers is None:
        return None

    for key in (name, name.lower(), name.upper(), name.title()):
        try:
            value = headers.get(key)
        except Exception:
            value = None
        if value:
            return str(value)
    return None


def _parse_streamable_http_body(raw: str) -> dict[str, Any]:
    payloads: list[str] = []
    current_data_lines: list[str] = []

    for line in raw.splitlines():
        if line.startswith("data:"):
            current_data_lines.append(line[5:].lstrip())
            continue

        if not line.strip() and current_data_lines:
            payloads.append("\n".join(current_data_lines))
            current_data_lines = []

    if current_data_lines:
        payloads.append("\n".join(current_data_lines))

    for payload in reversed(payloads):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise UnityMcpHttpError(
        "Unity MCP returned an unreadable streamable HTTP payload.",
        response_text=raw,
    )


def _decode_json_rpc_response(raw: str, content_type: str | None) -> dict[str, Any]:
    normalized_content_type = (content_type or "").lower()
    if "text/event-stream" in normalized_content_type:
        return _parse_streamable_http_body(raw)

    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise UnityMcpHttpError(
            "Unity MCP returned invalid JSON.",
            response_text=raw,
        ) from exc

    if not isinstance(parsed, dict):
        raise UnityMcpHttpError(
            "Unity MCP returned an unexpected response shape.",
            response_text=raw,
        )

    return parsed


def _perform_http_post(url: str, payload: dict[str, Any], headers: dict[str, str], timeout_ms: int) -> tuple[Any, dict[str, Any]]:
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib_request.Request(
        url,
        data=encoded,
        headers=headers,
        method="POST",
    )

    try:
        with urllib_request.urlopen(request, timeout=max(timeout_ms / 1000.0, 1.0)) as response:
            raw = response.read().decode("utf-8")
            parsed = _decode_json_rpc_response(raw, _headers_get(response.headers, "content-type"))
            return response.headers, parsed
    except urllib_error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise UnityMcpHttpError(
            f"Unity MCP request failed: HTTP Error {exc.code}: {exc.reason}",
            status_code=exc.code,
            response_text=raw,
        ) from exc
    except urllib_error.URLError as exc:
        raise UnityMcpHttpError(f"Unity MCP request failed: {exc}") from exc
    except (socket.timeout, TimeoutError) as exc:
        raise UnityMcpHttpError(
            f"Unity MCP request timed out after {timeout_ms}ms.",
        ) from exc


class UnityMcpHttpClient:
    def __init__(self, url: str, timeout_ms: int):
        self._url = url
        self._timeout_ms = timeout_ms
        self._session_id: str | None = None

    def request(self, method: str, params: dict[str, Any] | None, request_id: int) -> dict[str, Any]:
        if self._session_id is None:
            self._initialize_session()

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        retried = False

        while True:
            headers = {
                "Content-Type": "application/json",
                "Accept": STREAMABLE_HTTP_ACCEPT,
                SESSION_HEADER: self._session_id or "",
            }
            try:
                _, response = _perform_http_post(self._url, payload, headers, self._timeout_ms)
                return response
            except UnityMcpHttpError as exc:
                if retried or not self._is_session_related_error(exc):
                    raise

                self._session_id = None
                self._initialize_session()
                retried = True

    def _initialize_session(self) -> None:
        headers = {
            "Content-Type": "application/json",
            "Accept": STREAMABLE_HTTP_ACCEPT,
        }
        payload = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": DEFAULT_MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {
                    "name": "unity-resource-rag",
                    "version": "0.6.1",
                },
            },
        }

        response_headers, response = _perform_http_post(self._url, payload, headers, self._timeout_ms)
        error_payload = response.get("error")
        if error_payload:
            raise UnityMcpHttpError(f"Unity MCP initialize returned an error: {error_payload}")

        session_id = _headers_get(response_headers, SESSION_HEADER)
        if not session_id:
            raise UnityMcpHttpError(
                "Unity MCP initialize response did not include an MCP session ID.",
                response_text=json.dumps(response, ensure_ascii=False),
            )

        self._session_id = session_id

    @staticmethod
    def _is_session_related_error(exc: UnityMcpHttpError) -> bool:
        return exc.status_code in {400, 401, 403, 404, 409, 410}


_CLIENT_CACHE: dict[tuple[str, int], UnityMcpHttpClient] = {}


def get_unity_http_client(url: str, timeout_ms: int) -> UnityMcpHttpClient:
    cache_key = (url, timeout_ms)
    client = _CLIENT_CACHE.get(cache_key)
    if client is None:
        client = UnityMcpHttpClient(url, timeout_ms)
        _CLIENT_CACHE[cache_key] = client
    return client
