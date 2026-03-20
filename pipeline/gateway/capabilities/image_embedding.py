from __future__ import annotations

import base64
import math
from collections import Counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..models import GatewayRequestEnvelope, GatewayRunOptions
from ..router import GatewayCapabilityRouter


CAPABILITY_NAME = "image_embedding"
ADAPTER_ID = "local_image_embedding_preview"
PROVIDER_FAMILY = "local_retrieval"
PREVIEW_SCHEME = "visual-token-sparse-v1"


class ImageEmbeddingInputItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    imageDataUrl: str | None = None
    visualTokens: list[str] = Field(default_factory=list)
    label: str | None = None


class ImageEmbeddingInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    images: list[ImageEmbeddingInputItem] = Field(min_length=1)


class ImageEmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    capability: str = CAPABILITY_NAME
    providerPreference: list[str] = Field(default_factory=list)
    input: ImageEmbeddingInput
    outputSchema: str
    options: GatewayRunOptions = Field(default_factory=GatewayRunOptions)


def _normalize_request(request: GatewayRequestEnvelope | dict[str, Any]) -> ImageEmbeddingRequest:
    if isinstance(request, dict):
        return ImageEmbeddingRequest.model_validate(request)
    return ImageEmbeddingRequest.model_validate(
        {
            "capability": request.capability,
            "providerPreference": request.providerPreference,
            "input": request.input,
            "outputSchema": request.outputSchema,
            "options": request.options.model_dump(mode="python"),
        }
    )


def _parse_data_url(data_url: str) -> tuple[str, bytes]:
    if not data_url.startswith("data:") or "," not in data_url:
        raise ValueError("image_embedding preview currently expects a base64 data URL.")
    header, encoded = data_url.split(",", 1)
    if ";base64" not in header:
        raise ValueError("image_embedding preview currently supports base64 data URLs only.")
    media_type = header[5:].split(";", 1)[0].strip().lower() or "text/plain"
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError("image_embedding preview could not decode the data URL payload.") from exc
    return media_type, raw


def _portable_tokens(raw: bytes) -> list[str]:
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "image_embedding preview currently supports ASCII PPM/PGM payloads or caller-supplied visualTokens."
        ) from exc

    cleaned_lines: list[str] = []
    for line in text.splitlines():
        cleaned_lines.append(line.split("#", 1)[0])
    return [token for token in " ".join(cleaned_lines).split() if token]


def _load_portable_image(raw: bytes) -> tuple[int, int, list[tuple[int, int, int]]]:
    tokens = _portable_tokens(raw)
    if len(tokens) < 4:
        raise ValueError("image_embedding preview could not parse the portable image header.")

    magic = tokens[0]
    if magic not in {"P2", "P3"}:
        raise ValueError(
            "image_embedding preview currently supports ASCII P2/P3 portable image payloads only."
        )

    try:
        width = int(tokens[1])
        height = int(tokens[2])
        max_value = int(tokens[3])
    except ValueError as exc:
        raise ValueError("image_embedding preview received an invalid portable image size or range.") from exc

    if width <= 0 or height <= 0 or max_value <= 0:
        raise ValueError("image_embedding preview requires positive image dimensions and max value.")

    sample_values = tokens[4:]
    channels = 1 if magic == "P2" else 3
    expected_values = width * height * channels
    if len(sample_values) != expected_values:
        raise ValueError(
            f"image_embedding preview expected {expected_values} portable image values but received {len(sample_values)}."
        )

    scale = 255.0 / float(max_value)
    numeric_values: list[int] = []
    for raw_value in sample_values:
        try:
            parsed = int(raw_value)
        except ValueError as exc:
            raise ValueError("image_embedding preview received a non-numeric portable image sample.") from exc
        numeric_values.append(max(0, min(255, int(round(parsed * scale)))))

    pixels: list[tuple[int, int, int]] = []
    if channels == 1:
        for value in numeric_values:
            pixels.append((value, value, value))
    else:
        for index in range(0, len(numeric_values), 3):
            pixels.append(tuple(numeric_values[index:index + 3]))  # type: ignore[arg-type]
    return width, height, pixels


def _luminance(pixel: tuple[int, int, int]) -> float:
    red, green, blue = pixel
    return (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255.0


def _bucket(value: float, *, low: float, high: float, labels: tuple[str, str, str]) -> str:
    if value < low:
        return labels[0]
    if value < high:
        return labels[1]
    return labels[2]


def _orientation_token(width: int, height: int) -> str:
    aspect_ratio = width / float(height)
    if aspect_ratio > 1.2:
        return "orientation_landscape"
    if aspect_ratio < 0.8:
        return "orientation_portrait"
    return "orientation_balanced"


def _palette_token(pixels: list[tuple[int, int, int]]) -> str:
    red = sum(pixel[0] for pixel in pixels) / len(pixels)
    green = sum(pixel[1] for pixel in pixels) / len(pixels)
    blue = sum(pixel[2] for pixel in pixels) / len(pixels)
    spread = max(red, green, blue) - min(red, green, blue)
    if spread < 18.0:
        return "palette_neutral"
    if red >= green and red >= blue:
        return "palette_warm"
    if blue >= red and blue >= green:
        return "palette_cool"
    return "palette_green"


def _grid_cell_pixels(
    pixels: list[tuple[int, int, int]],
    width: int,
    height: int,
    row: int,
    col: int,
    *,
    rows: int = 3,
    cols: int = 3,
) -> list[tuple[int, int, int]]:
    x0 = col * width // cols
    x1 = max(x0 + 1, (col + 1) * width // cols)
    y0 = row * height // rows
    y1 = max(y0 + 1, (row + 1) * height // rows)

    cell_pixels: list[tuple[int, int, int]] = []
    for y in range(y0, min(y1, height)):
        for x in range(x0, min(x1, width)):
            cell_pixels.append(pixels[y * width + x])
    return cell_pixels or [pixels[min((height - 1) * width + (width - 1), len(pixels) - 1)]]


def _edge_density(pixels: list[tuple[int, int, int]], width: int, height: int) -> float:
    if width == 1 and height == 1:
        return 0.0

    total = 0.0
    comparisons = 0
    luma_cache = [_luminance(pixel) for pixel in pixels]
    for y in range(height):
        for x in range(width):
            current = luma_cache[y * width + x]
            if x + 1 < width:
                total += abs(current - luma_cache[y * width + (x + 1)])
                comparisons += 1
            if y + 1 < height:
                total += abs(current - luma_cache[(y + 1) * width + x])
                comparisons += 1
    if comparisons == 0:
        return 0.0
    return total / comparisons


def _visual_tokens_from_pixels(width: int, height: int, pixels: list[tuple[int, int, int]]) -> list[str]:
    luma_values = [_luminance(pixel) for pixel in pixels]
    mean_luma = sum(luma_values) / len(luma_values)
    contrast = math.sqrt(sum((value - mean_luma) ** 2 for value in luma_values) / len(luma_values))
    edge_density = _edge_density(pixels, width, height)

    tokens = [
        _orientation_token(width, height),
        _orientation_token(width, height),
        _bucket(width / float(height), low=0.8, high=1.25, labels=("aspect_tall", "aspect_balanced", "aspect_wide")),
        _bucket(mean_luma, low=0.35, high=0.68, labels=("brightness_dark", "brightness_mid", "brightness_bright")),
        _bucket(contrast, low=0.12, high=0.24, labels=("contrast_low", "contrast_mid", "contrast_high")),
        _bucket(edge_density, low=0.08, high=0.18, labels=("edges_low", "edges_mid", "edges_high")),
        _palette_token(pixels),
    ]

    center_pixels = _grid_cell_pixels(pixels, width, height, 1, 1)
    border_pixels = []
    for row in range(3):
        for col in range(3):
            if row == 1 and col == 1:
                continue
            border_pixels.extend(_grid_cell_pixels(pixels, width, height, row, col))
    center_luma = sum(_luminance(pixel) for pixel in center_pixels) / len(center_pixels)
    border_luma = sum(_luminance(pixel) for pixel in border_pixels) / len(border_pixels)
    if center_luma > border_luma + 0.08:
        tokens.append("focus_center_bright")
    elif border_luma > center_luma + 0.08:
        tokens.append("focus_border_bright")
    else:
        tokens.append("focus_balanced")

    for row in range(3):
        for col in range(3):
            cell_pixels = _grid_cell_pixels(pixels, width, height, row, col)
            cell_luma = sum(_luminance(pixel) for pixel in cell_pixels) / len(cell_pixels)
            tokens.append(
                f"cell_{row}_{col}_"
                + _bucket(cell_luma, low=0.35, high=0.68, labels=("dark", "mid", "bright"))
            )
    return tokens


def _normalize_token_weights(tokens: list[str]) -> dict[str, float]:
    normalized_tokens = [token.strip().lower() for token in tokens if isinstance(token, str) and token.strip()]
    if not normalized_tokens:
        raise ValueError("image_embedding preview needs at least one usable visual token.")
    counts = Counter(normalized_tokens)
    total = sum(counts.values())
    return {
        token: round(count / total, 6)
        for token, count in sorted(counts.items())
    }


def _embed_item(item: ImageEmbeddingInputItem) -> dict[str, Any]:
    if item.visualTokens:
        token_weights = _normalize_token_weights(item.visualTokens)
        return {
            "sourceType": "visual_tokens",
            "tokenWeights": token_weights,
            "tokenCount": len(item.visualTokens),
            "label": item.label,
        }

    if not item.imageDataUrl:
        raise ValueError("image_embedding preview needs imageDataUrl or visualTokens for every item.")

    media_type, raw = _parse_data_url(item.imageDataUrl)
    width, height, pixels = _load_portable_image(raw)
    token_list = _visual_tokens_from_pixels(width, height, pixels)
    return {
        "sourceType": "image_data_url",
        "sourceMediaType": media_type,
        "width": width,
        "height": height,
        "tokenWeights": _normalize_token_weights(token_list),
        "tokenCount": len(token_list),
        "label": item.label,
    }


def run_image_embedding(request: GatewayRequestEnvelope | dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_request(request)
    items: list[dict[str, Any]] = []
    total_tokens = 0

    for index, item in enumerate(normalized.input.images):
        embedded = _embed_item(item)
        total_tokens += embedded["tokenCount"]
        items.append(
            {
                "index": index,
                **embedded,
            }
        )

    return {
        "adapterId": ADAPTER_ID,
        "authMode": "none",
        "providerFamily": PROVIDER_FAMILY,
        "output": {
            "scheme": PREVIEW_SCHEME,
            "preview": True,
            "embedding": items[0]["tokenWeights"] if len(items) == 1 else None,
            "items": items,
        },
        "usage": {
            "inputImages": len(items),
            "totalTokens": total_tokens,
        },
        "trace": {
            "capability": CAPABILITY_NAME,
            "outputSchema": normalized.outputSchema,
            "preview": True,
        },
    }


def handle(request: GatewayRequestEnvelope) -> dict[str, Any]:
    return run_image_embedding(request)


def register(router: GatewayCapabilityRouter) -> None:
    router.register(
        CAPABILITY_NAME,
        handle,
        adapter_id=ADAPTER_ID,
    )
