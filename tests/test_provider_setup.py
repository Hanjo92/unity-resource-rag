from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.mcp.tools import inspect_provider_setup as inspect_provider_setup_tool
from pipeline.planner.extract_reference_layout import (
    ProviderConfig,
    inspect_provider_setup as inspect_provider_setup_config,
)


def _tool_payload(result: dict[str, object]) -> dict[str, object]:
    content = result["content"]
    assert isinstance(content, list)
    raw = content[1]["text"]
    assert isinstance(raw, str)
    return json.loads(raw)


def _make_token_file() -> str:
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    try:
        json.dump({"access_token": "fake-token"}, handle)
        handle.flush()
        return handle.name
    finally:
        handle.close()


class ProviderSetupTests(unittest.TestCase):
    def test_openai_api_key_preset_clears_leftover_oauth_inputs(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            payload = _tool_payload(
                inspect_provider_setup_tool(
                    {
                        "connection_preset": "openai_api_key",
                        "oauth_token_env": "LEFTOVER_TOKEN_ENV",
                    }
                )
            )

        self.assertEqual(payload["requestedProvider"], "openai")
        self.assertEqual(payload["authMode"], "api_key")
        self.assertIn("OPENAI_API_KEY", " ".join(payload["missingSettings"]))
        self.assertNotIn("LEFTOVER_TOKEN_ENV", " ".join(payload["missingSettings"]))

    def test_custom_openai_compatible_preset_requires_api_key(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            payload = _tool_payload(
                inspect_provider_setup_tool(
                    {
                        "connection_preset": "custom_openai_compatible",
                        "provider_base_url": "https://example.com/v1",
                        "provider_api_key_env": "EXAMPLE_API_KEY",
                        "oauth_token_env": "LEFTOVER_TOKEN_ENV",
                    }
                )
            )

        self.assertEqual(payload["requestedProvider"], "openai_compatible")
        self.assertEqual(payload["authMode"], "api_key")
        self.assertIn("EXAMPLE_API_KEY", " ".join(payload["missingSettings"]))
        self.assertNotIn("LEFTOVER_TOKEN_ENV", " ".join(payload["missingSettings"]))

    def test_openai_compatible_does_not_reuse_codex_auth_file(self) -> None:
        token_file = _make_token_file()
        try:
            with mock.patch.dict(os.environ, {}, clear=True):
                inspection = inspect_provider_setup_config(
                    ProviderConfig(
                        provider="openai_compatible",
                        screen_name="custom-endpoint",
                        model="gpt-4.1-mini",
                        detail="high",
                        max_image_dim=1600,
                        project_hints=[],
                        api_key_env="EXAMPLE_API_KEY",
                        auth_mode=None,
                        oauth_token_env=None,
                        oauth_token_file=None,
                        oauth_token_command=None,
                        codex_auth_file=token_file,
                        base_url="https://example.com/v1",
                        gateway_url=None,
                        gateway_auth_token_env="UNITY_RESOURCE_RAG_GATEWAY_TOKEN",
                        gateway_timeout_ms=30000,
                    )
                )
        finally:
            Path(token_file).unlink(missing_ok=True)

        self.assertEqual(inspection.auth_mode, "api_key")
        self.assertIn("EXAMPLE_API_KEY", " ".join(inspection.missing_settings))

    def test_openai_still_supports_codex_auth_file(self) -> None:
        token_file = _make_token_file()
        try:
            with mock.patch.dict(os.environ, {}, clear=True):
                inspection = inspect_provider_setup_config(
                    ProviderConfig(
                        provider="openai",
                        screen_name="openai",
                        model="gpt-4.1-mini",
                        detail="high",
                        max_image_dim=1600,
                        project_hints=[],
                        api_key_env="OPENAI_API_KEY",
                        auth_mode=None,
                        oauth_token_env=None,
                        oauth_token_file=None,
                        oauth_token_command=None,
                        codex_auth_file=token_file,
                        base_url=None,
                        gateway_url=None,
                        gateway_auth_token_env="UNITY_RESOURCE_RAG_GATEWAY_TOKEN",
                        gateway_timeout_ms=30000,
                    )
                )
        finally:
            Path(token_file).unlink(missing_ok=True)

        self.assertEqual(inspection.auth_mode, "oauth_token")
        self.assertEqual(inspection.token_source, "codex_file")
        self.assertEqual(inspection.missing_settings, [])

    def test_openai_compatible_accepts_explicit_oauth_token_file(self) -> None:
        token_file = _make_token_file()
        try:
            with mock.patch.dict(os.environ, {}, clear=True):
                inspection = inspect_provider_setup_config(
                    ProviderConfig(
                        provider="openai_compatible",
                        screen_name="custom-endpoint",
                        model="gpt-4.1-mini",
                        detail="high",
                        max_image_dim=1600,
                        project_hints=[],
                        api_key_env="EXAMPLE_API_KEY",
                        auth_mode="oauth_token",
                        oauth_token_env=None,
                        oauth_token_file=token_file,
                        oauth_token_command=None,
                        codex_auth_file=None,
                        base_url="https://example.com/v1",
                        gateway_url=None,
                        gateway_auth_token_env="UNITY_RESOURCE_RAG_GATEWAY_TOKEN",
                        gateway_timeout_ms=30000,
                    )
                )
        finally:
            Path(token_file).unlink(missing_ok=True)

        self.assertEqual(inspection.auth_mode, "oauth_token")
        self.assertEqual(inspection.token_source, "file")
        self.assertEqual(inspection.missing_settings, [])


if __name__ == "__main__":
    unittest.main()
