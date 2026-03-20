from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from pydantic import ValidationError

from .adapters.gemini_direct import GatewayAdapterError, run_gemini_layout_extraction
from .auth import GatewayAuthConfig, validate_bearer_token
from .models import GatewayErrorResponse, GatewayOkResponse, GatewayRunRequest


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_TOKEN_ENV = "UNITY_RESOURCE_RAG_GATEWAY_TOKEN"


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _error_payload(
    *,
    code: str,
    message: str,
    retryable: bool,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return GatewayErrorResponse(
        code=code,
        message=message,
        retryable=retryable,
        details=details or {},
    ).model_dump(mode="json")


def _select_adapter(request: GatewayRunRequest) -> str:
    preferences = request.providerPreference or []
    if any(item in {"gateway:gemini_direct", "gemini_direct"} for item in preferences):
        return "gemini_direct"
    if any(item in {"gateway:auto", "auto"} for item in preferences):
        return "gemini_direct"
    return "gemini_direct"


class GatewayRequestHandler(BaseHTTPRequestHandler):
    server_version = "UnityResourceRagGateway/0.2.1"

    def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
        encoded = _json_bytes(payload)
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return
        self._write_json(
            HTTPStatus.NOT_FOUND,
            _error_payload(
                code="invalid_request",
                message=f"Unknown path: {self.path}",
                retryable=False,
            ),
        )

    def do_POST(self) -> None:
        if self.path != "/v1/capabilities/run":
            self._write_json(
                HTTPStatus.NOT_FOUND,
                _error_payload(
                    code="invalid_request",
                    message=f"Unknown path: {self.path}",
                    retryable=False,
                ),
            )
            return

        ok, auth_error = validate_bearer_token(
            config=GatewayAuthConfig(bearer_token=os.getenv(DEFAULT_TOKEN_ENV)),
            authorization_header=self.headers.get("Authorization"),
        )
        if not ok:
            self._write_json(
                HTTPStatus.UNAUTHORIZED,
                _error_payload(
                    code="auth_required",
                    message=auth_error or "Authentication is required.",
                    retryable=False,
                ),
            )
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        body = self.rfile.read(length)

        try:
            payload = json.loads(body.decode("utf-8"))
            request = GatewayRunRequest.model_validate(payload)
        except json.JSONDecodeError as exc:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                _error_payload(
                    code="invalid_request",
                    message=f"Request body was not valid JSON: {exc}",
                    retryable=False,
                ),
            )
            return
        except ValidationError as exc:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                _error_payload(
                    code="invalid_request",
                    message="Request body did not match GatewayRunRequest.",
                    retryable=False,
                    details={"errors": exc.errors()},
                ),
            )
            return

        adapter_id = _select_adapter(request)
        try:
            if adapter_id == "gemini_direct":
                result = run_gemini_layout_extraction(request)
            else:
                raise GatewayAdapterError(
                    "unsupported_capability",
                    f"No adapter is available for {adapter_id}.",
                    retryable=False,
                )
        except GatewayAdapterError as exc:
            self._write_json(
                HTTPStatus.BAD_GATEWAY if exc.retryable else HTTPStatus.BAD_REQUEST,
                _error_payload(
                    code=exc.code,
                    message=str(exc),
                    retryable=exc.retryable,
                    details=exc.details,
                ),
            )
            return
        except Exception as exc:
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                _error_payload(
                    code="internal_error",
                    message=f"Unhandled gateway failure: {exc}",
                    retryable=False,
                ),
            )
            return

        response = GatewayOkResponse(
            capability=request.capability,
            adapterId=result["adapterId"],
            authMode=result["authMode"],
            providerFamily=result["providerFamily"],
            output=result["output"],
            usage=result.get("usage"),
            trace=result.get("trace"),
        ).model_dump(mode="json", exclude_none=True)
        self._write_json(HTTPStatus.OK, response)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> int:
    host = os.getenv("UNITY_RESOURCE_RAG_GATEWAY_HOST", DEFAULT_HOST)
    port = int(os.getenv("UNITY_RESOURCE_RAG_GATEWAY_PORT", str(DEFAULT_PORT)))
    server = ThreadingHTTPServer((host, port), GatewayRequestHandler)
    print(
        json.dumps(
            {
                "status": "listening",
                "host": host,
                "port": port,
                "authTokenEnv": DEFAULT_TOKEN_ENV,
                "supportedAdapters": ["gemini_direct"],
                "supportedCapabilities": ["vision_layout_extraction"],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        ,
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
