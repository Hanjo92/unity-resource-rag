from __future__ import annotations

import sys
import unittest
from unittest import mock


REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.mcp.unity_http import (
    SESSION_HEADER,
    STREAMABLE_HTTP_ACCEPT,
    UnityMcpHttpClient,
    _parse_streamable_http_body,
)


class _FakeResponse:
    def __init__(self, body: str, headers: dict[str, str]):
        self._body = body.encode("utf-8")
        self.headers = headers

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class UnityHttpTests(unittest.TestCase):
    def test_parse_streamable_http_body_extracts_json_message(self) -> None:
        raw = (
            "event: message\n"
            "data: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"tools\":[]}}\n"
            "\n"
        )
        payload = _parse_streamable_http_body(raw)
        self.assertEqual(payload["result"]["tools"], [])

    def test_client_initializes_once_and_reuses_session_id(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_urlopen(request, timeout=0):
            headers = dict(request.header_items())
            body = request.data.decode("utf-8")
            calls.append({"headers": headers, "body": body})

            if "\"method\": \"initialize\"" in body:
                return _FakeResponse(
                    "event: message\r\ndata: {\"jsonrpc\":\"2.0\",\"id\":0,\"result\":{\"protocolVersion\":\"2024-11-05\"}}\r\n\r\n",
                    {"content-type": "text/event-stream", "mcp-session-id": "session-123"},
                )

            return _FakeResponse(
                "event: message\r\ndata: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"tools\":[{\"name\":\"apply_ui_blueprint\"}]}}\r\n\r\n",
                {"content-type": "text/event-stream", "mcp-session-id": "session-123"},
            )

        client = UnityMcpHttpClient("http://127.0.0.1:8080/mcp", 3000)
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            first = client.request("tools/list", {}, 1)
            second = client.request("tools/list", {}, 2)

        second_headers = {str(key).lower(): value for key, value in calls[1]["headers"].items()}
        third_headers = {str(key).lower(): value for key, value in calls[2]["headers"].items()}
        self.assertEqual(first["result"]["tools"][0]["name"], "apply_ui_blueprint")
        self.assertEqual(second["result"]["tools"][0]["name"], "apply_ui_blueprint")
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0]["headers"]["Accept"], STREAMABLE_HTTP_ACCEPT)
        self.assertNotIn(SESSION_HEADER, {str(key).lower(): value for key, value in calls[0]["headers"].items()})
        self.assertEqual(second_headers[SESSION_HEADER], "session-123")
        self.assertEqual(third_headers[SESSION_HEADER], "session-123")
