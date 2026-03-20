#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
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
SUPPORTED_PROVIDERS = ("auto", "openai", "openai_compatible", "local_heuristic")
SUPPORTED_AUTH_MODES = ("auto", "api_key_env", "oauth_token_env", "oauth_token_file", "oauth_token_command")


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
    auth_mode: str
    oauth_token_env: str | None
    oauth_token_file: str | None
    oauth_token_command: str | None
    base_url: str | None


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


def _read_token_file(path_value: str) -> str | None:
    token_path = Path(path_value).expanduser()
    if not token_path.exists():
        return None
    token = token_path.read_text(encoding="utf-8").strip()
    return token or None


def _run_token_command(command: str) -> str | None:
    completed = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        _die(f"OAuth token command failed with exit code {completed.returncode}: {completed.stderr.strip() or command}")
    token = completed.stdout.strip()
    return token or None


def resolve_auth_mode(config: ProviderConfig) -> str:
    if config.auth_mode != "auto":
        return config.auth_mode
    if os.getenv(config.api_key_env):
        return "api_key_env"
    if config.oauth_token_env and os.getenv(config.oauth_token_env):
        return "oauth_token_env"
    if config.oauth_token_file and _read_token_file(config.oauth_token_file):
        return "oauth_token_file"
    if config.oauth_token_command:
        return "oauth_token_command"
    return "api_key_env"


def has_auth_material(config: ProviderConfig, auth_mode: str) -> bool:
    if auth_mode == "api_key_env":
        return bool(os.getenv(config.api_key_env))
    if auth_mode == "oauth_token_env":
        return bool(config.oauth_token_env and os.getenv(config.oauth_token_env))
    if auth_mode == "oauth_token_file":
        return bool(config.oauth_token_file and _read_token_file(config.oauth_token_file))
    if auth_mode == "oauth_token_command":
        return bool(config.oauth_token_command)
    return False


def resolve_provider(config: ProviderConfig) -> str:
    if config.provider != "auto":
        return config.provider
    return "openai" if has_auth_material(config, resolve_auth_mode(config)) else "local_heuristic"


def resolve_auth_value(config: ProviderConfig) -> tuple[str, str]:
    auth_mode = resolve_auth_mode(config)

    if auth_mode == "api_key_env":
        api_key = os.getenv(config.api_key_env)
        if not api_key:
            _die(f"{config.api_key_env} is not set.")
        return auth_mode, api_key

    if auth_mode == "oauth_token_env":
        if not config.oauth_token_env:
            _die("--oauth-token-env is required for --auth-mode oauth_token_env.")
        token = os.getenv(config.oauth_token_env)
        if not token:
            _die(f"{config.oauth_token_env} is not set.")
        return auth_mode, token

    if auth_mode == "oauth_token_file":
        if not config.oauth_token_file:
            _die("--oauth-token-file is required for --auth-mode oauth_token_file.")
        token = _read_token_file(config.oauth_token_file)
        if not token:
            _die(f"OAuth token file is missing or empty: {config.oauth_token_file}")
        return auth_mode, token

    if auth_mode == "oauth_token_command":
        if not config.oauth_token_command:
            _die("--oauth-token-command is required for --auth-mode oauth_token_command.")
        token = _run_token_command(config.oauth_token_command)
        if not token:
            _die("OAuth token command produced an empty token.")
        return auth_mode, token

    _die(f"Unsupported auth mode: {auth_mode}")


def create_openai_client(*, credential: str, base_url: str | None):
    try:
        from openai import OpenAI
    except ImportError:
        _die("openai SDK not installed. Install with `uv pip install openai`.")

    return OpenAI(api_key=credential, base_url=base_url)


def extract_with_openai_like(
    *,
    image_path: Path,
    config: ProviderConfig,
    provider_name: str,
    base_url: str | None,
) -> tuple[ReferenceLayoutPlan, dict[str, Any]]:
    data_url, image_meta = encode_image_data_url(image_path, config.max_image_dim)
    resolved_auth_mode, credential = resolve_auth_value(config)
    client = create_openai_client(credential=credential, base_url=base_url)

    response = client.responses.parse(
        model=config.model,
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
        "provider": provider_name,
        "model": config.model,
        "responseId": getattr(response, "id", None),
        "usage": getattr(response, "usage", None),
        "image": image_meta,
        "screenName": config.screen_name,
        "projectHints": config.project_hints,
        "baseUrl": base_url,
        "apiKeyEnv": config.api_key_env,
        "authMode": resolved_auth_mode,
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
    resolved_provider = resolve_provider(config)

    if resolved_provider == "openai":
        plan, report = extract_with_openai_like(
            image_path=image_path,
            config=config,
            provider_name="openai",
            base_url=None,
        )
    elif resolved_provider == "openai_compatible":
        if not config.base_url:
            _die("--provider-base-url is required for --provider openai_compatible.")
        plan, report = extract_with_openai_like(
            image_path=image_path,
            config=config,
            provider_name="openai_compatible",
            base_url=config.base_url,
        )
    elif resolved_provider == "local_heuristic":
        plan, report = extract_with_local_heuristic(
            image_path=image_path,
            config=config,
        )
    else:
        _die(f"Unsupported provider: {resolved_provider}")

    report["resolvedProvider"] = resolved_provider
    report["requestedProvider"] = config.provider
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
    resolved_provider = resolve_provider(config)
    resolved_auth_mode = resolve_auth_mode(config)
    preview = {
        "mode": "dry-run",
        "requestedProvider": config.provider,
        "resolvedProvider": resolved_provider,
        "model": config.model,
        "screenName": config.screen_name,
        "imagePath": str(image_path),
        "image": image_meta,
        "detail": config.detail,
        "projectHints": config.project_hints,
        "providerBaseUrl": config.base_url,
        "providerApiKeyEnv": config.api_key_env,
        "authMode": resolved_auth_mode,
    }

    if resolved_provider in {"openai", "openai_compatible"}:
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
    parser.add_argument("--provider-base-url", help="Base URL for openai_compatible providers.")
    parser.add_argument("--provider-api-key-env", default="OPENAI_API_KEY", help="Environment variable that stores the provider API key.")
    parser.add_argument("--auth-mode", choices=SUPPORTED_AUTH_MODES, default="auto", help="Authentication mode for API-backed providers.")
    parser.add_argument("--oauth-token-env", help="Environment variable containing an OAuth bearer token for API-backed providers.")
    parser.add_argument("--oauth-token-file", help="File containing an OAuth bearer token for API-backed providers.")
    parser.add_argument("--oauth-token-command", help="Shell command that prints an OAuth bearer token for API-backed providers.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model to use for API-backed providers. Default: {DEFAULT_MODEL}")
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
