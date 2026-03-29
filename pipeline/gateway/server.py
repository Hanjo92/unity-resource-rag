from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .auth import GatewayAuthConfig, validate_bearer_token
from .adapters.gemini_direct import GatewayAdapterError
from .models import GatewayErrorResponse, GatewayOkResponse
from .router import GatewayCapabilityRouter, GatewayRouteError, create_default_gateway_router


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8090
DEFAULT_TOKEN_ENV = "UNITY_RESOURCE_RAG_GATEWAY_TOKEN"
DEFAULT_ROUTER = create_default_gateway_router()


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


class GatewayRequestHandler(BaseHTTPRequestHandler):
    server_version = "UnityResourceRagGateway/0.6.1"
    router: GatewayCapabilityRouter = DEFAULT_ROUTER

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

        capability = ""
        if isinstance(payload, dict):
            capability = str(payload.get("capability") or "")

        try:
            result = self.router.handle_payload(payload)
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
        except GatewayRouteError as exc:
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
            capability=capability,
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
                "supportedAdapters": list(DEFAULT_ROUTER.supported_adapters),
                "supportedCapabilities": list(DEFAULT_ROUTER.supported_capabilities),
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
