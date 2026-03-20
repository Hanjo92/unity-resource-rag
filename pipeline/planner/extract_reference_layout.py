#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from pydantic import ValidationError

from reference_layout_models import ComponentSpec, ReferenceLayoutPlan


DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_DETAIL = "high"
DEFAULT_MAX_IMAGE_DIM = 1600
DEFAULT_PROVIDER = "auto"
SUPPORTED_PROVIDERS = ("auto", "openai", "gemini", "antigravity", "claude", "claude_code", "openai_compatible", "local_heuristic")
DEFAULT_CODEX_AUTH_FILE = "auth.json"
DEFAULT_CLAUDE_CODE_AUTH_FILE = ".credentials.json"
DEFAULT_GOOGLE_OAUTH_COMMAND = "gcloud auth application-default print-access-token"
PROVIDER_DEFAULTS: dict[str, dict[str, str | None]] = {
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "base_url": None,
        "default_model": DEFAULT_MODEL,
        "default_auth_mode": "api_key",
        "default_oauth_token_env": None,
        "default_oauth_token_file": None,
        "default_oauth_token_command": None,
    },
    "gemini": {
        "api_key_env": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.5-flash",
        "default_auth_mode": "api_key",
        "default_oauth_token_env": None,
        "default_oauth_token_file": None,
        "default_oauth_token_command": None,
    },
    "antigravity": {
        "api_key_env": "GOOGLE_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.5-flash",
        "default_auth_mode": "oauth_token",
        "default_oauth_token_env": "GOOGLE_OAUTH_ACCESS_TOKEN",
        "default_oauth_token_file": None,
        "default_oauth_token_command": DEFAULT_GOOGLE_OAUTH_COMMAND,
    },
    "claude": {
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com/v1/",
        "default_model": "claude-opus-4-6",
        "default_auth_mode": "api_key",
        "default_oauth_token_env": None,
        "default_oauth_token_file": None,
        "default_oauth_token_command": None,
    },
    "claude_code": {
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com/v1/",
        "default_model": "claude-opus-4-6",
        "default_auth_mode": "oauth_token",
        "default_oauth_token_env": "ANTHROPIC_AUTH_TOKEN",
        "default_oauth_token_file": None,
        "default_oauth_token_command": None,
    },
    "openai_compatible": {
        "api_key_env": "OPENAI_API_KEY",
        "base_url": None,
        "default_model": DEFAULT_MODEL,
        "default_auth_mode": "api_key",
        "default_oauth_token_env": None,
        "default_oauth_token_file": None,
        "default_oauth_token_command": None,
    },
}
TOKEN_KEY_CANDIDATES = (
    ("access_token",),
    ("accessToken",),
    ("tokens", "access_token"),
    ("tokens", "accessToken"),
    ("credentials", "access_token"),
    ("credentials", "accessToken"),
    ("auth", "access_token"),
    ("auth", "accessToken"),
    ("claudeAiOauth", "accessToken"),
    ("claudeAiOauth", "access_token"),
    ("oauth", "accessToken"),
    ("oauth", "access_token"),
)


SYSTEM_PROMPT = """
You extract a Unity UI reference layout plan from a single reference image.

Return only structured JSON that matches the provided schema.

Planning rules:
- Build a region-level plan, not a pixel-perfect render recipe.
- Prefer 3 to 12 meaningful regions.
- Start from major shells and containers before smaller content.
- Preserve single-image frames and backgrounds as one `image` region when they visually read as one asset.
- Use `container` for pure layout/grouping regions.
- Use `prefab_instance` only when a repeated/reusable widget is clearly intended.
- For repeated structures, create one reusable region and set `repeatCount` instead of duplicating many copies.
- Use `tmp_text` only for readable text that should become a TextMeshPro object.
- Put visible text content into `text.value`.
- For `image` and `prefab_instance` nodes, write retrieval-friendly `queryText` describing the actual visual asset to search for.
- `normalizedBounds` are relative to the parent, origin is top-left, values are between 0 and 1.
- Use `stretchToParent: true` only when the region should fill the parent.
- Keep hierarchy intentional and shallow.
- Do not hallucinate project-specific safe area components.
- When uncertain, choose fewer larger regions rather than over-segmenting decorative details.
- Prefer regionType values such as popup_frame, panel_frame, content_column, title_text, button, badge_icon, inventory_slot, list_item, header, footer, dialog_body.
""".strip()


@dataclass
class ProviderConfig:
    provider: str
    screen_name: str
    model: str
    detail: str
    max_image_dim: int
    project_hints: list[str]
    api_key_env: str
    auth_mode: str | None
    oauth_token_env: str | None
    oauth_token_file: str | None
    oauth_token_command: str | None
    codex_auth_file: str | None
    base_url: str | None


@dataclass
class ProviderAuth:
    auth_mode: str
    bearer_token: str | None
    token_source: str


@dataclass(frozen=True)
class ResolvedProviderConfig:
    requested_provider: str
    provider: str
    api_key_env: str
    base_url: str | None
    model: str
    auth_mode: str | None
    oauth_token_env: str | None
    oauth_token_file: str | None
    oauth_token_command: str | None


def _die(message: str) -> None:
    raise SystemExit(message)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "region"


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def load_original_image_meta(image_path: Path) -> dict[str, int]:
    with Image.open(image_path) as image:
        width, height = image.size
    return {
        "originalWidth": width,
        "originalHeight": height,
    }


def prepare_analysis_image(image_path: Path, max_dim: int) -> tuple[Image.Image, dict[str, int | str]]:
    with Image.open(image_path) as image:
        original_width, original_height = image.size
        analysis = image.convert("RGBA") if image.mode in {"RGBA", "LA"} else image.convert("RGB")
        analysis.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        sent_width, sent_height = analysis.size

        return analysis.copy(), {
            "originalWidth": original_width,
            "originalHeight": original_height,
            "sentWidth": sent_width,
            "sentHeight": sent_height,
            "mimeType": "image/png" if "A" in analysis.getbands() else "image/jpeg",
        }


def encode_image_data_url(image_path: Path, max_dim: int) -> tuple[str, dict[str, int | str]]:
    working, image_meta = prepare_analysis_image(image_path, max_dim)
    has_alpha = "A" in working.getbands()
    output_format = "PNG" if has_alpha else "JPEG"
    mime_type = "image/png" if has_alpha else "image/jpeg"

    buffer = BytesIO()
    save_kwargs = {}
    if output_format == "JPEG":
        working = working.convert("RGB")
        save_kwargs["quality"] = 90
        save_kwargs["optimize"] = True
    working.save(buffer, format=output_format, **save_kwargs)

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    image_meta["mimeType"] = mime_type
    return f"data:{mime_type};base64,{encoded}", image_meta


def build_user_prompt(
    *,
    screen_name: str,
    image_meta: dict[str, int | str],
    project_hints: list[str],
) -> str:
    lines = [
        f"Screen name: {screen_name}",
        f"Original image size: {image_meta['originalWidth']}x{image_meta['originalHeight']}",
        "Extract a valid reference layout plan.",
        "Use the image itself as the source of truth.",
        "If the image shows a dialog or popup, capture the shell frame as a major region.",
        "If text is readable, transcribe it into tmp_text nodes.",
        "If a content area clearly fills its parent, use stretchToParent instead of tiny offsets.",
    ]
    if project_hints:
        lines.append("Project hints:")
        lines.extend(f"- {hint}" for hint in project_hints)
    return "\n".join(lines)


def inject_safe_area_component(
    plan: ReferenceLayoutPlan,
    component_type: str | None,
    properties_json: str | None,
) -> ReferenceLayoutPlan:
    if not component_type:
        return plan

    properties: dict[str, Any] = {}
    if properties_json:
        parsed = json.loads(properties_json)
        if not isinstance(parsed, dict):
            _die("--safe-area-properties must decode to a JSON object.")
        properties = parsed

    component = ComponentSpec(typeName=component_type, properties=properties)
    existing = [item for item in plan.safeAreaRoot.components if item.typeName != component_type]
    plan.safeAreaRoot.components = [*existing, component]
    return plan


def normalize_plan(plan: ReferenceLayoutPlan, *, screen_name: str, image_meta: dict[str, int | str]) -> ReferenceLayoutPlan:
    data = plan.model_dump(mode="python")
    data["screenName"] = screen_name
    data["referenceResolution"] = {
        "x": int(image_meta["originalWidth"]),
        "y": int(image_meta["originalHeight"]),
    }

    used_ids: dict[str, int] = {}
    normalized_regions: list[dict[str, Any]] = []
    for raw_region in data.get("regions", []):
        region = dict(raw_region)
        base_id = _slugify(region.get("id") or region.get("name") or region.get("regionType") or region.get("kind") or "region")
        suffix = used_ids.get(base_id, 0)
        used_ids[base_id] = suffix + 1
        region["id"] = base_id if suffix == 0 else f"{base_id}_{suffix + 1}"
        region["name"] = region.get("name") or region["id"]
        region["parentId"] = region.get("parentId") or "safe_area_root"

        bounds = region.get("normalizedBounds")
        if bounds:
            region["normalizedBounds"] = {
                key: round(max(0.0, min(1.0, float(bounds[key]))), 4)
                for key in ("x", "y", "w", "h")
            }

        normalized_regions.append(region)

    data["regions"] = normalized_regions
    return ReferenceLayoutPlan.model_validate(data)


def _provider_defaults(provider: str) -> dict[str, str | None]:
    return PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["openai"])


def _default_claude_code_auth_file() -> Path:
    claude_config_dir = os.getenv("CLAUDE_CONFIG_DIR")
    base_dir = Path(claude_config_dir).expanduser() if claude_config_dir else Path.home() / ".claude"
    return base_dir / DEFAULT_CLAUDE_CODE_AUTH_FILE


def _default_token_file_for_provider(provider: str) -> str | None:
    if provider == "claude_code":
        return str(_default_claude_code_auth_file())
    return None


def _command_exists(command: str) -> bool:
    argv = shlex.split(command)
    if not argv:
        return False
    return shutil.which(argv[0]) is not None


def _has_command_token(command: str) -> bool:
    if not _command_exists(command):
        return False
    try:
        return bool(_read_token_from_command(command))
    except SystemExit:
        return False


def resolve_runtime_provider_config(config: ProviderConfig) -> ResolvedProviderConfig:
    requested_provider = config.provider

    if requested_provider == "auto":
        if has_provider_auth(config):
            return ResolvedProviderConfig(
                requested_provider=requested_provider,
                provider="openai",
                api_key_env=config.api_key_env,
                base_url=None,
                model=config.model,
                auth_mode=config.auth_mode,
                oauth_token_env=config.oauth_token_env,
                oauth_token_file=config.oauth_token_file,
                oauth_token_command=config.oauth_token_command,
            )
        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            defaults = _provider_defaults("gemini")
            return ResolvedProviderConfig(
                requested_provider=requested_provider,
                provider="gemini",
                api_key_env="GOOGLE_API_KEY" if os.getenv("GOOGLE_API_KEY") else str(defaults["api_key_env"]),
                base_url=defaults["base_url"],
                model=str(defaults["default_model"]),
                auth_mode=defaults["default_auth_mode"],
                oauth_token_env=defaults["default_oauth_token_env"],
                oauth_token_file=_default_token_file_for_provider("gemini"),
                oauth_token_command=defaults["default_oauth_token_command"],
            )
        if os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN") or _has_command_token(DEFAULT_GOOGLE_OAUTH_COMMAND):
            defaults = _provider_defaults("antigravity")
            return ResolvedProviderConfig(
                requested_provider=requested_provider,
                provider="antigravity",
                api_key_env=str(defaults["api_key_env"]),
                base_url=defaults["base_url"],
                model=str(defaults["default_model"]),
                auth_mode=defaults["default_auth_mode"],
                oauth_token_env=defaults["default_oauth_token_env"],
                oauth_token_file=_default_token_file_for_provider("antigravity"),
                oauth_token_command=defaults["default_oauth_token_command"],
            )
        if os.getenv("ANTHROPIC_API_KEY"):
            defaults = _provider_defaults("claude")
            return ResolvedProviderConfig(
                requested_provider=requested_provider,
                provider="claude",
                api_key_env=str(defaults["api_key_env"]),
                base_url=defaults["base_url"],
                model=str(defaults["default_model"]),
                auth_mode=defaults["default_auth_mode"],
                oauth_token_env=defaults["default_oauth_token_env"],
                oauth_token_file=_default_token_file_for_provider("claude"),
                oauth_token_command=defaults["default_oauth_token_command"],
            )
        if os.getenv("ANTHROPIC_AUTH_TOKEN") or _has_readable_token_file(_default_token_file_for_provider("claude_code")):
            defaults = _provider_defaults("claude_code")
            return ResolvedProviderConfig(
                requested_provider=requested_provider,
                provider="claude_code",
                api_key_env=str(defaults["api_key_env"]),
                base_url=defaults["base_url"],
                model=str(defaults["default_model"]),
                auth_mode=defaults["default_auth_mode"],
                oauth_token_env=defaults["default_oauth_token_env"],
                oauth_token_file=_default_token_file_for_provider("claude_code"),
                oauth_token_command=defaults["default_oauth_token_command"],
            )
        return ResolvedProviderConfig(
            requested_provider=requested_provider,
            provider="local_heuristic",
            api_key_env=config.api_key_env,
            base_url=None,
            model=config.model,
            auth_mode=config.auth_mode,
            oauth_token_env=config.oauth_token_env,
            oauth_token_file=config.oauth_token_file,
            oauth_token_command=config.oauth_token_command,
        )

    if requested_provider == "local_heuristic":
        return ResolvedProviderConfig(
            requested_provider=requested_provider,
            provider="local_heuristic",
            api_key_env=config.api_key_env,
            base_url=None,
            model=config.model,
            auth_mode=config.auth_mode,
            oauth_token_env=config.oauth_token_env,
            oauth_token_file=config.oauth_token_file,
            oauth_token_command=config.oauth_token_command,
        )

    defaults = _provider_defaults(requested_provider)
    base_url = config.base_url if config.base_url else defaults["base_url"]
    api_key_env = config.api_key_env
    if api_key_env == "OPENAI_API_KEY" and defaults["api_key_env"]:
        api_key_env = str(defaults["api_key_env"])

    model = config.model
    if model == DEFAULT_MODEL and defaults["default_model"]:
        model = str(defaults["default_model"])

    auth_mode = config.auth_mode or defaults["default_auth_mode"]
    oauth_token_env = config.oauth_token_env or defaults["default_oauth_token_env"]
    oauth_token_file = config.oauth_token_file or _default_token_file_for_provider(requested_provider)
    oauth_token_command = config.oauth_token_command or defaults["default_oauth_token_command"]

    return ResolvedProviderConfig(
        requested_provider=requested_provider,
        provider=requested_provider,
        api_key_env=api_key_env,
        base_url=base_url,
        model=model,
        auth_mode=auth_mode,
        oauth_token_env=oauth_token_env,
        oauth_token_file=oauth_token_file,
        oauth_token_command=oauth_token_command,
    )


def _configured_auth_mode(config: ProviderConfig) -> str:
    if config.auth_mode and config.auth_mode not in {"api_key", "oauth_token"}:
        _die(f"Unsupported auth mode: {config.auth_mode}")
    if config.oauth_token_env or config.oauth_token_file or config.oauth_token_command or config.codex_auth_file:
        return "oauth_token"
    if config.auth_mode:
        return config.auth_mode
    if os.getenv(config.api_key_env):
        return "api_key"
    if config.provider in {"auto", "openai", "openai_compatible"} and _has_readable_codex_auth_file(None):
        return "oauth_token"
    return "api_key"


def _default_codex_auth_file() -> Path:
    codex_home = os.getenv("CODEX_HOME")
    base_dir = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return base_dir / DEFAULT_CODEX_AUTH_FILE


def _extract_nested_string(payload: Any, key_path: tuple[str, ...]) -> str | None:
    current = payload
    for key in key_path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if isinstance(current, str):
        token = current.strip()
        return token or None
    return None


def _extract_access_token(payload: Any) -> str | None:
    for key_path in TOKEN_KEY_CANDIDATES:
        token = _extract_nested_string(payload, key_path)
        if token:
            return token
    return None


def _resolve_oauth_token_source(config: ProviderConfig) -> tuple[str, str | None]:
    sources = [
        ("env", config.oauth_token_env),
        ("file", config.oauth_token_file),
        ("command", config.oauth_token_command),
        ("codex_file", config.codex_auth_file),
    ]
    configured = [(name, value) for name, value in sources if value]
    if configured:
        return configured[0]

    if config.provider == "claude_code":
        default_claude_file = _default_claude_code_auth_file()
        if _has_readable_token_file(str(default_claude_file)):
            return ("file", str(default_claude_file))

    if config.provider == "antigravity" and _has_command_token(DEFAULT_GOOGLE_OAUTH_COMMAND):
        return ("command", DEFAULT_GOOGLE_OAUTH_COMMAND)

    if config.provider in {"auto", "openai", "openai_compatible"}:
        default_codex_auth_file = _default_codex_auth_file()
        if _has_readable_codex_auth_file(str(default_codex_auth_file)):
            return ("codex_file", str(default_codex_auth_file))

    _die("OAuth token auth requires --oauth-token-env, --oauth-token-file, --oauth-token-command, or a readable auth file/default token source.")


def _read_token_from_file(path_value: str) -> str:
    raw = Path(path_value).expanduser().read_text(encoding="utf-8").strip()
    if not raw:
        _die(f"OAuth token file is empty: {path_value}")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw

    token = _extract_access_token(payload)
    if not token:
        _die(f"OAuth token file does not contain an access token: {path_value}")
    return token


def _has_readable_token_file(path_value: str | None) -> bool:
    if not path_value:
        return False

    token_file = Path(path_value).expanduser()
    if not token_file.exists() or not token_file.is_file():
        return False

    try:
        return bool(_read_token_from_file(str(token_file)))
    except OSError:
        return False
    except SystemExit:
        return False


def _read_token_from_codex_auth_file(path_value: str | None) -> str:
    auth_file = Path(path_value).expanduser() if path_value else _default_codex_auth_file()
    try:
        payload = json.loads(auth_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _die(f"Codex auth file not found: {auth_file}")
    except json.JSONDecodeError as exc:
        _die(f"Codex auth file is not valid JSON: {auth_file} ({exc})")
    except OSError as exc:
        _die(f"Failed to read Codex auth file: {auth_file} ({exc})")

    token = _extract_access_token(payload)
    if not token:
        _die(f"Codex auth file does not contain an access token: {auth_file}")
    return token


def _has_readable_codex_auth_file(path_value: str | None) -> bool:
    try:
        return bool(_read_token_from_codex_auth_file(path_value))
    except SystemExit:
        return False


def _read_token_from_command(command: str) -> str:
    argv = shlex.split(command)
    if not argv:
        _die("OAuth token command is empty.")

    completed = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        _die(f"OAuth token command failed with exit code {completed.returncode}.")
    token = completed.stdout.strip()
    if not token:
        _die("OAuth token command returned an empty token.")
    return token


def resolve_provider_auth(config: ProviderConfig, *, require_token: bool = True) -> ProviderAuth:
    auth_mode = _configured_auth_mode(config)
    if auth_mode == "api_key":
        token = os.getenv(config.api_key_env)
        if require_token and not token:
            _die(f"{config.api_key_env} is not set.")
        return ProviderAuth(auth_mode="api_key", bearer_token=token, token_source="env")

    token_source, source_value = _resolve_oauth_token_source(config)
    token: str | None = None
    if require_token:
        if token_source == "env":
            assert source_value is not None
            token = os.getenv(source_value)
            if not token:
                _die(f"{source_value} is not set.")
        elif token_source == "file":
            assert source_value is not None
            token = _read_token_from_file(source_value)
        elif token_source == "command":
            assert source_value is not None
            token = _read_token_from_command(source_value)
        elif token_source == "codex_file":
            token = _read_token_from_codex_auth_file(source_value)
        else:
            _die(f"Unsupported OAuth token source: {token_source}")

    return ProviderAuth(auth_mode="oauth_token", bearer_token=token, token_source=token_source)


def has_provider_auth(config: ProviderConfig) -> bool:
    auth_mode = _configured_auth_mode(config)
    if auth_mode == "api_key":
        return bool(os.getenv(config.api_key_env))

    token_source, source_value = _resolve_oauth_token_source(config)
    if token_source == "env":
        assert source_value is not None
        return bool(os.getenv(source_value))
    if token_source == "file":
        return _has_readable_token_file(source_value)
    if token_source == "codex_file":
        return _has_readable_codex_auth_file(source_value)
    return bool(source_value)


def resolve_provider(config: ProviderConfig) -> str:
    return resolve_runtime_provider_config(config).provider


def create_openai_client(*, auth: ProviderAuth, base_url: str | None):
    try:
        from openai import OpenAI
    except ImportError:
        _die("openai SDK not installed. Install with `uv pip install openai`.")

    if not auth.bearer_token:
        _die("Resolved provider auth did not return a bearer token.")

    return OpenAI(api_key=auth.bearer_token, base_url=base_url)


def extract_with_openai_like(
    *,
    image_path: Path,
    config: ProviderConfig,
    runtime: ResolvedProviderConfig,
) -> tuple[ReferenceLayoutPlan, dict[str, Any]]:
    data_url, image_meta = encode_image_data_url(image_path, config.max_image_dim)
    runtime_config = ProviderConfig(
        provider=runtime.provider,
        screen_name=config.screen_name,
        model=runtime.model,
        detail=config.detail,
        max_image_dim=config.max_image_dim,
        project_hints=config.project_hints,
        api_key_env=runtime.api_key_env,
        auth_mode=runtime.auth_mode,
        oauth_token_env=runtime.oauth_token_env,
        oauth_token_file=runtime.oauth_token_file,
        oauth_token_command=runtime.oauth_token_command,
        codex_auth_file=config.codex_auth_file,
        base_url=runtime.base_url,
    )
    auth = resolve_provider_auth(runtime_config)
    client = create_openai_client(auth=auth, base_url=runtime.base_url)

    response = client.responses.parse(
        model=runtime.model,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": build_user_prompt(
                            screen_name=config.screen_name,
                            image_meta=image_meta,
                            project_hints=config.project_hints,
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": data_url,
                        "detail": config.detail,
                    },
                ],
            }
        ],
        instructions=SYSTEM_PROMPT,
        text_format=ReferenceLayoutPlan,
        temperature=0.2,
        max_output_tokens=4000,
        store=False,
    )

    parsed = response.output_parsed
    if parsed is None:
        _die("Model returned no parsed output.")

    plan = normalize_plan(parsed, screen_name=config.screen_name, image_meta=image_meta)
    report = {
        "provider": runtime.provider,
        "model": runtime.model,
        "responseId": getattr(response, "id", None),
        "usage": getattr(response, "usage", None),
        "image": image_meta,
        "screenName": config.screen_name,
        "projectHints": config.project_hints,
        "baseUrl": runtime.base_url,
        "apiKeyEnv": runtime.api_key_env,
        "authMode": auth.auth_mode,
        "tokenSource": auth.token_source,
    }
    return plan, report


def build_local_heuristic_query(region_type: str, project_hints: list[str]) -> str:
    hints_blob = " ".join(project_hints).lower()
    if region_type == "popup_frame" or "popup" in hints_blob or "dialog" in hints_blob:
        return "popup dialog panel frame window background"
    if region_type == "header":
        return "header bar panel background ui"
    if region_type == "footer":
        return "footer bar panel background ui"
    return "panel frame background ui container"


def detect_foreground_box(image: Image.Image) -> tuple[dict[str, float], dict[str, Any]]:
    rgb = image.convert("RGB")
    arr = np.asarray(rgb, dtype=np.uint8)
    height, width, _ = arr.shape

    border = np.concatenate([
        arr[0, :, :],
        arr[-1, :, :],
        arr[:, 0, :],
        arr[:, -1, :],
    ], axis=0)
    background = np.median(border, axis=0)

    diff = np.linalg.norm(arr.astype(np.float32) - background.astype(np.float32), axis=2)
    threshold = max(28.0, float(np.percentile(diff, 92)) * 0.45)
    mask = diff > threshold

    min_row_count = max(4, int(width * 0.02))
    min_col_count = max(4, int(height * 0.02))
    valid_rows = np.where(mask.sum(axis=1) > min_row_count)[0]
    valid_cols = np.where(mask.sum(axis=0) > min_col_count)[0]

    if valid_rows.size == 0 or valid_cols.size == 0:
        bounds = {"x": 0.18, "y": 0.18, "w": 0.64, "h": 0.64}
        diagnostics = {
            "backgroundColor": background.astype(int).tolist(),
            "threshold": round(threshold, 2),
            "coverage": 0.0,
            "usedFallbackBounds": True,
        }
        return bounds, diagnostics

    x0 = max(0, int(valid_cols[0] - width * 0.02))
    x1 = min(width, int(valid_cols[-1] + 1 + width * 0.02))
    y0 = max(0, int(valid_rows[0] - height * 0.02))
    y1 = min(height, int(valid_rows[-1] + 1 + height * 0.02))

    bounds = {
        "x": round(x0 / width, 4),
        "y": round(y0 / height, 4),
        "w": round((x1 - x0) / width, 4),
        "h": round((y1 - y0) / height, 4),
    }
    diagnostics = {
        "backgroundColor": background.astype(int).tolist(),
        "threshold": round(threshold, 2),
        "coverage": round(float(mask.mean()), 4),
        "usedFallbackBounds": False,
    }
    return bounds, diagnostics


def classify_region(bounds: dict[str, float], project_hints: list[str]) -> tuple[str, float]:
    cx = bounds["x"] + bounds["w"] * 0.5
    cy = bounds["y"] + bounds["h"] * 0.5
    hints_blob = " ".join(project_hints).lower()

    centered = abs(cx - 0.5) <= 0.18 and abs(cy - 0.5) <= 0.18
    if ("popup" in hints_blob or "dialog" in hints_blob) or (centered and 0.25 <= bounds["w"] <= 0.85 and 0.18 <= bounds["h"] <= 0.85):
        return "popup_frame", 0.46

    if bounds["y"] <= 0.12 and bounds["h"] <= 0.24:
        return "header", 0.34

    if bounds["y"] + bounds["h"] >= 0.78 and bounds["h"] <= 0.24:
        return "footer", 0.34

    return "panel_frame", 0.3


def extract_with_local_heuristic(
    *,
    image_path: Path,
    config: ProviderConfig,
) -> tuple[ReferenceLayoutPlan, dict[str, Any]]:
    working_image, image_meta = prepare_analysis_image(image_path, config.max_image_dim)
    bounds, diagnostics = detect_foreground_box(working_image)
    region_type, confidence = classify_region(bounds, config.project_hints)

    plan_dict = {
        "screenName": config.screen_name,
        "referenceResolution": {
            "x": int(image_meta["originalWidth"]),
            "y": int(image_meta["originalHeight"]),
        },
        "safeAreaRoot": {
            "name": "SafeAreaRoot",
            "components": [],
        },
        "regions": [
            {
                "id": region_type,
                "name": "PopupFrame" if region_type == "popup_frame" else "MainPanel",
                "kind": "image",
                "parentId": "safe_area_root",
                "regionType": region_type,
                "queryText": build_local_heuristic_query(region_type, config.project_hints),
                "preferredKind": "sprite",
                "bindingPolicy": "best_match",
                "minScore": 0.3,
                "normalizedBounds": bounds,
                "confidence": confidence,
                "image": {
                    "type": "Sliced" if region_type in {"popup_frame", "panel_frame"} else "Simple",
                    "raycastTarget": False,
                },
            },
            {
                "id": "content_column",
                "name": "ContentColumn",
                "kind": "container",
                "parentId": region_type,
                "stretchToParent": True,
                "confidence": round(max(confidence - 0.06, 0.2), 2),
            },
        ],
    }

    plan = normalize_plan(
        ReferenceLayoutPlan.model_validate(plan_dict),
        screen_name=config.screen_name,
        image_meta=image_meta,
    )
    report = {
        "provider": "local_heuristic",
        "image": image_meta,
        "screenName": config.screen_name,
        "projectHints": config.project_hints,
        "heuristics": {
            "bounds": bounds,
            "classification": region_type,
            **diagnostics,
        },
        "limitations": [
            "No OCR is performed.",
            "Semantic query text is heuristic and generic.",
            "Best for centered popup/panel layouts and rough shell extraction.",
        ],
    }
    return plan, report


def extract_plan(
    *,
    image_path: Path,
    config: ProviderConfig,
) -> tuple[ReferenceLayoutPlan, dict[str, Any]]:
    runtime = resolve_runtime_provider_config(config)
    resolved_provider = runtime.provider

    if resolved_provider in {"openai", "gemini", "antigravity", "claude", "claude_code", "openai_compatible"}:
        if resolved_provider == "openai_compatible" and not runtime.base_url:
            _die("--provider-base-url is required for --provider openai_compatible.")
        plan, report = extract_with_openai_like(
            image_path=image_path,
            config=config,
            runtime=runtime,
        )
    elif resolved_provider == "local_heuristic":
        plan, report = extract_with_local_heuristic(
            image_path=image_path,
            config=config,
        )
    else:
        _die(f"Unsupported provider: {resolved_provider}")

    report["resolvedProvider"] = resolved_provider
    report["requestedProvider"] = runtime.requested_provider
    return plan, report


def default_output_path(image_path: Path) -> Path:
    return image_path.with_name(f"{image_path.stem}.reference-layout.json")


def default_report_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}.extract-report.json")


def dry_run_payload(
    *,
    image_path: Path,
    config: ProviderConfig,
) -> dict[str, Any]:
    _, image_meta = prepare_analysis_image(image_path, config.max_image_dim)
    runtime = resolve_runtime_provider_config(config)
    resolved_provider = runtime.provider
    preview = {
        "mode": "dry-run",
        "requestedProvider": config.provider,
        "resolvedProvider": resolved_provider,
        "model": runtime.model,
        "screenName": config.screen_name,
        "imagePath": str(image_path),
        "image": image_meta,
        "detail": config.detail,
        "projectHints": config.project_hints,
        "providerBaseUrl": runtime.base_url,
        "providerApiKeyEnv": runtime.api_key_env,
    }

    if resolved_provider in {"openai", "gemini", "antigravity", "claude", "claude_code", "openai_compatible"}:
        runtime_config = ProviderConfig(
            provider=runtime.provider,
            screen_name=config.screen_name,
            model=runtime.model,
            detail=config.detail,
            max_image_dim=config.max_image_dim,
            project_hints=config.project_hints,
            api_key_env=runtime.api_key_env,
            auth_mode=runtime.auth_mode,
            oauth_token_env=runtime.oauth_token_env,
            oauth_token_file=runtime.oauth_token_file,
            oauth_token_command=runtime.oauth_token_command,
            codex_auth_file=config.codex_auth_file,
            base_url=runtime.base_url,
        )
        auth = resolve_provider_auth(runtime_config, require_token=False)
        preview["authMode"] = auth.auth_mode
        preview["tokenSource"] = auth.token_source
        preview["instructionsPreview"] = SYSTEM_PROMPT
        preview["userPromptPreview"] = build_user_prompt(
            screen_name=config.screen_name,
            image_meta=image_meta,
            project_hints=config.project_hints,
        )
    else:
        preview["heuristicPreview"] = {
            "description": "Detect a dominant non-background foreground box and convert it into a generic popup/panel shell plan.",
            "limitations": [
                "No OCR",
                "Generic query text only",
                "Best effort bounding box detection",
            ],
        }

    return preview


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract a reference layout plan JSON from a UI screenshot/mockup using pluggable providers."
    )
    parser.add_argument("image", type=Path, help="Path to the reference image")
    parser.add_argument("--output", type=Path, help="Path to write the reference layout JSON")
    parser.add_argument("--report", type=Path, help="Path to write the extraction report JSON")
    parser.add_argument("--screen-name", help="Screen name override. Defaults to the image file stem.")
    parser.add_argument("--provider", choices=SUPPORTED_PROVIDERS, default=DEFAULT_PROVIDER, help=f"Extraction provider. Default: {DEFAULT_PROVIDER}")
    parser.add_argument("--provider-base-url", help="Base URL override for openai_compatible, gemini/antigravity, or claude/claude_code providers.")
    parser.add_argument("--provider-api-key-env", default="OPENAI_API_KEY", help="Environment variable that stores the provider API key. Defaults are OPENAI_API_KEY/openai, GEMINI_API_KEY or GOOGLE_API_KEY/gemini, ANTHROPIC_API_KEY/claude.")
    parser.add_argument("--auth-mode", choices=["api_key", "oauth_token"], help="Authentication mode for API-backed providers. Defaults to api_key unless any OAuth input is provided.")
    parser.add_argument("--oauth-token-env", help="Environment variable that stores an OAuth bearer token.")
    parser.add_argument("--oauth-token-file", help="File path that contains an OAuth bearer token.")
    parser.add_argument("--oauth-token-command", help="Command that prints an OAuth bearer token to stdout. Use shell wrapping explicitly if needed, e.g. `bash -lc ...`.")
    parser.add_argument("--codex-auth-file", help="Path to a Codex OAuth auth.json file. Defaults to $CODEX_HOME/auth.json or ~/.codex/auth.json when available.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model to use for API-backed providers. Default: {DEFAULT_MODEL} (provider presets override this when you keep the default value).")
    parser.add_argument("--detail", choices=["low", "high", "auto"], default=DEFAULT_DETAIL, help="Image detail hint for API-backed providers.")
    parser.add_argument("--max-image-dim", type=int, default=DEFAULT_MAX_IMAGE_DIM, help="Maximum width/height sent to extraction or heuristic analysis.")
    parser.add_argument("--hint", action="append", default=[], help="Optional project or UI hints to include in the extraction context.")
    parser.add_argument("--safe-area-component-type", help="Optional project-specific safe area component type to inject after extraction.")
    parser.add_argument("--safe-area-properties", help="JSON object string for the injected safe area component properties.")
    parser.add_argument("--dry-run", action="store_true", help="Build the provider request or heuristic preview without writing a layout output.")
    args = parser.parse_args()

    image_path = args.image.expanduser().resolve()
    if not image_path.exists():
        _die(f"Image not found: {image_path}")

    config = ProviderConfig(
        provider=args.provider,
        screen_name=args.screen_name or image_path.stem,
        model=args.model,
        detail=args.detail,
        max_image_dim=args.max_image_dim,
        project_hints=args.hint,
        api_key_env=args.provider_api_key_env,
        auth_mode=args.auth_mode,
        oauth_token_env=args.oauth_token_env,
        oauth_token_file=args.oauth_token_file,
        oauth_token_command=args.oauth_token_command,
        codex_auth_file=args.codex_auth_file,
        base_url=args.provider_base_url,
    )

    output_path = args.output or default_output_path(image_path)
    report_path = args.report or default_report_path(output_path)

    if args.dry_run:
        preview = dry_run_payload(
            image_path=image_path,
            config=config,
        )
        save_json(report_path, preview)
        print(json.dumps({
            "report": str(report_path),
            "mode": "dry-run",
            "screenName": config.screen_name,
            "resolvedProvider": preview["resolvedProvider"],
        }, ensure_ascii=False, indent=2))
        return 0

    try:
        plan, report = extract_plan(
            image_path=image_path,
            config=config,
        )
        plan = inject_safe_area_component(
            plan,
            component_type=args.safe_area_component_type,
            properties_json=args.safe_area_properties,
        )
    except ValidationError as exc:
        errors = [{"location": list(item["loc"]), "message": item["msg"]} for item in exc.errors()]
        save_json(report_path, {"validationErrors": errors})
        print(json.dumps({"report": str(report_path), "errors": errors}, ensure_ascii=False, indent=2))
        return 1

    save_json(output_path, plan.model_dump(mode="json", exclude_none=True))
    save_json(report_path, report)
    print(json.dumps({
        "output": str(output_path),
        "report": str(report_path),
        "screenName": plan.screenName,
        "regionCount": len(plan.regions),
        "resolvedProvider": report["resolvedProvider"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
