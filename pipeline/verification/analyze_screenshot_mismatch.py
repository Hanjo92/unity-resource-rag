#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def load_rgb_array(path: Path, size: tuple[int, int] | None = None) -> tuple[np.ndarray, tuple[int, int]]:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        original_size = rgb.size
        if size is not None and rgb.size != size:
            rgb = rgb.resize(size, Image.Resampling.LANCZOS)
        arr = np.asarray(rgb, dtype=np.float32)
    return arr, original_size


def compute_background_color(arr: np.ndarray) -> np.ndarray:
    border = np.concatenate([
        arr[0, :, :],
        arr[-1, :, :],
        arr[:, 0, :],
        arr[:, -1, :],
    ], axis=0)
    return np.median(border, axis=0)


def compute_foreground_mask(arr: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    background = compute_background_color(arr)
    diff = np.linalg.norm(arr - background, axis=2)
    threshold = max(28.0, float(np.percentile(diff, 92)) * 0.45)
    mask = diff > threshold
    diagnostics = {
        "backgroundColor": [round(float(value), 2) for value in background.tolist()],
        "threshold": round(threshold, 2),
        "coverage": round(float(mask.mean()), 4),
    }
    return mask, diagnostics


def bbox_from_mask(mask: np.ndarray) -> dict[str, float] | None:
    ys, xs = np.where(mask)
    if ys.size == 0 or xs.size == 0:
        return None
    height, width = mask.shape
    x0 = int(xs.min())
    x1 = int(xs.max()) + 1
    y0 = int(ys.min())
    y1 = int(ys.max()) + 1
    return {
        "x": round(x0 / width, 4),
        "y": round(y0 / height, 4),
        "w": round((x1 - x0) / width, 4),
        "h": round((y1 - y0) / height, 4),
    }


def compute_diff_bbox(reference: np.ndarray, captured: np.ndarray) -> tuple[np.ndarray, dict[str, float] | None, float]:
    diff = np.mean(np.abs(reference - captured), axis=2)
    threshold = max(18.0, float(np.percentile(diff, 90)) * 0.5)
    mask = diff > threshold
    bbox = bbox_from_mask(mask)
    return mask, bbox, threshold


def box_center(box: dict[str, float] | None) -> tuple[float, float]:
    if not box:
        return 0.5, 0.5
    return box["x"] + box["w"] * 0.5, box["y"] + box["h"] * 0.5


def iou(left: dict[str, float] | None, right: dict[str, float] | None) -> float:
    if not left or not right:
        return 0.0
    x1 = max(left["x"], right["x"])
    y1 = max(left["y"], right["y"])
    x2 = min(left["x"] + left["w"], right["x"] + right["w"])
    y2 = min(left["y"] + left["h"], right["y"] + right["h"])
    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter = inter_w * inter_h
    if inter <= 0.0:
        return 0.0
    left_area = left["w"] * left["h"]
    right_area = right["w"] * right["h"]
    denom = left_area + right_area - inter
    return 0.0 if denom <= 0.0 else inter / denom


def mean_color(arr: np.ndarray, mask: np.ndarray | None) -> list[float]:
    if mask is None or not np.any(mask):
        values = arr.reshape(-1, 3)
    else:
        values = arr[mask]
    if values.size == 0:
        values = arr.reshape(-1, 3)
    return [round(float(v), 2) for v in np.mean(values, axis=0).tolist()]


def normalized_center_delta(reference_box: dict[str, float] | None, captured_box: dict[str, float] | None) -> dict[str, float]:
    rx, ry = box_center(reference_box)
    cx, cy = box_center(captured_box)
    return {
        "x": round(cx - rx, 4),
        "y": round(cy - ry, 4),
    }


def normalized_size_delta(reference_box: dict[str, float] | None, captured_box: dict[str, float] | None) -> dict[str, float]:
    if not reference_box or not captured_box:
        return {"w": 0.0, "h": 0.0}
    return {
        "w": round(captured_box["w"] - reference_box["w"], 4),
        "h": round(captured_box["h"] - reference_box["h"], 4),
    }


def compute_node_boxes(blueprint: dict[str, Any]) -> list[dict[str, Any]]:
    resolution = ((blueprint.get("root") or {}).get("canvasScaler") or {}).get("referenceResolution") or {}
    root_box = {
        "x": 0.0,
        "y": 0.0,
        "w": float(resolution.get("x", 1920)),
        "h": float(resolution.get("y", 1080)),
    }

    nodes: list[dict[str, Any]] = []

    def resolve_box(rect: dict[str, Any] | None, parent_box: dict[str, float]) -> dict[str, float]:
        if not rect:
            return parent_box

        anchor_min = rect.get("anchorMin") or {"x": 0.5, "y": 0.5}
        anchor_max = rect.get("anchorMax") or anchor_min
        pivot = rect.get("pivot") or {"x": 0.5, "y": 0.5}
        offset_min = rect.get("offsetMin")
        offset_max = rect.get("offsetMax")

        stretch = (
            offset_min is not None and
            offset_max is not None and
            (
                abs(float(anchor_min.get("x", 0.0)) - float(anchor_max.get("x", 0.0))) > 1e-6 or
                abs(float(anchor_min.get("y", 0.0)) - float(anchor_max.get("y", 0.0))) > 1e-6
            )
        )

        if stretch:
            left = parent_box["x"] + parent_box["w"] * float(anchor_min.get("x", 0.0)) + float(offset_min.get("x", 0.0))
            right = parent_box["x"] + parent_box["w"] * float(anchor_max.get("x", 1.0)) + float(offset_max.get("x", 0.0))
            top = parent_box["y"] + parent_box["h"] * (1.0 - float(anchor_max.get("y", 1.0))) - float(offset_max.get("y", 0.0))
            bottom = parent_box["y"] + parent_box["h"] * (1.0 - float(anchor_min.get("y", 0.0))) - float(offset_min.get("y", 0.0))
            return {
                "x": left,
                "y": top,
                "w": max(0.0, right - left),
                "h": max(0.0, bottom - top),
            }

        size_delta = rect.get("sizeDelta") or {"x": parent_box["w"], "y": parent_box["h"]}
        anchored_position = rect.get("anchoredPosition") or {"x": 0.0, "y": 0.0}
        anchor_x = parent_box["x"] + parent_box["w"] * float(anchor_min.get("x", 0.5))
        anchor_y = parent_box["y"] + parent_box["h"] * (1.0 - float(anchor_min.get("y", 0.5)))
        width = float(size_delta.get("x", parent_box["w"]))
        height = float(size_delta.get("y", parent_box["h"]))
        x = anchor_x + float(anchored_position.get("x", 0.0)) - width * float(pivot.get("x", 0.5))
        y = anchor_y - float(anchored_position.get("y", 0.0)) - height * (1.0 - float(pivot.get("y", 0.5)))
        return {"x": x, "y": y, "w": width, "h": height}

    def walk(node: dict[str, Any], parent_box: dict[str, float], hierarchy_path: str) -> None:
        node_box = resolve_box(node.get("rect"), parent_box)
        current_path = f"{hierarchy_path}/{node.get('name')}" if hierarchy_path else (node.get("name") or "Node")
        normalized = {
            "x": round(node_box["x"] / root_box["w"], 4),
            "y": round(node_box["y"] / root_box["h"], 4),
            "w": round(node_box["w"] / root_box["w"], 4),
            "h": round(node_box["h"] / root_box["h"], 4),
        }
        nodes.append({
            "id": node.get("id"),
            "name": node.get("name"),
            "kind": node.get("kind"),
            "hierarchyPath": current_path,
            "bounds": normalized,
            "assetPath": (node.get("asset") or {}).get("path"),
        })
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child, node_box, current_path)

    root = blueprint.get("root")
    if isinstance(root, dict):
        walk(root, root_box, "")
    return nodes


def node_overlap_score(node_bounds: dict[str, float], target_box: dict[str, float] | None) -> float:
    if not target_box:
        return 0.0
    return round(iou(node_bounds, target_box), 4)


def find_suspect_nodes(blueprint: dict[str, Any] | None, target_box: dict[str, float] | None) -> list[dict[str, Any]]:
    if blueprint is None or target_box is None:
        return []
    nodes = compute_node_boxes(blueprint)
    ranked = []
    for node in nodes:
        score = node_overlap_score(node["bounds"], target_box)
        if score > 0.0:
            ranked.append({**node, "overlapScore": score})
    ranked.sort(key=lambda item: item["overlapScore"], reverse=True)
    return ranked[:5]


def build_issue(
    *,
    issue_type: str,
    severity: str,
    title: str,
    details: str,
    likely_fixes: list[str],
    suspect_nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "type": issue_type,
        "severity": severity,
        "title": title,
        "details": details,
        "likelyFixes": likely_fixes,
        "suspectNodes": [
            {
                "id": node.get("id"),
                "name": node.get("name"),
                "kind": node.get("kind"),
                "hierarchyPath": node.get("hierarchyPath"),
                "overlapScore": node.get("overlapScore"),
                "assetPath": node.get("assetPath"),
            }
            for node in suspect_nodes
        ],
    }


def severity_rank(severity: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(severity, 0)


def analyze(
    *,
    reference_path: Path,
    captured_path: Path,
    blueprint: dict[str, Any] | None,
) -> dict[str, Any]:
    reference_arr, reference_size = load_rgb_array(reference_path)
    captured_arr, captured_original_size = load_rgb_array(captured_path, size=reference_size)

    reference_mask, reference_diag = compute_foreground_mask(reference_arr)
    captured_mask, captured_diag = compute_foreground_mask(captured_arr)
    diff_mask, diff_bbox, diff_threshold = compute_diff_bbox(reference_arr, captured_arr)

    reference_box = bbox_from_mask(reference_mask)
    captured_box = bbox_from_mask(captured_mask)
    center_delta = normalized_center_delta(reference_box, captured_box)
    size_delta = normalized_size_delta(reference_box, captured_box)
    bbox_iou = round(iou(reference_box, captured_box), 4)

    mean_abs_error = float(np.mean(np.abs(reference_arr - captured_arr)))
    normalized_error = round(mean_abs_error / 255.0, 4)
    diff_coverage = round(float(diff_mask.mean()), 4)

    reference_color = mean_color(reference_arr, reference_mask)
    captured_color = mean_color(captured_arr, captured_mask)
    color_delta = round(math.sqrt(sum((r - c) ** 2 for r, c in zip(reference_color, captured_color))), 2)

    suspect_nodes = find_suspect_nodes(blueprint, diff_bbox or captured_box or reference_box)

    issues: list[dict[str, Any]] = []
    if abs(center_delta["x"]) >= 0.04 or abs(center_delta["y"]) >= 0.04 or bbox_iou < 0.72:
        issues.append(build_issue(
            issue_type="composition_shift",
            severity="high" if bbox_iou < 0.55 else "medium",
            title="Top-level composition is shifted from the reference",
            details=(
                f"Foreground center delta is ({center_delta['x']}, {center_delta['y']}) "
                f"with bbox IoU {bbox_iou}."
            ),
            likely_fixes=[
                "Inspect parent container ownership before touching child offsets.",
                "Check anchors and pivot for the suspect region.",
                "Verify centered popup roots are still centered under the intended parent.",
            ],
            suspect_nodes=suspect_nodes,
        ))

    if abs(size_delta["w"]) >= 0.06 or abs(size_delta["h"]) >= 0.06:
        issues.append(build_issue(
            issue_type="scale_mismatch",
            severity="high" if abs(size_delta["w"]) >= 0.12 or abs(size_delta["h"]) >= 0.12 else "medium",
            title="The built UI is scaled differently from the reference",
            details=(
                f"Foreground size delta is ({size_delta['w']}, {size_delta['h']}) "
                "relative to the reference."
            ),
            likely_fixes=[
                "Check CanvasScaler and top-level sizing rules first.",
                "Review parent-driven width and height ownership before local sizeDelta edits.",
                "If this is a frame/background, prefer the correct existing asset before compensating with scale.",
            ],
            suspect_nodes=suspect_nodes,
        ))

    if color_delta >= 35.0 and bbox_iou >= 0.65:
        issues.append(build_issue(
            issue_type="style_asset_mismatch",
            severity="medium",
            title="The overall asset/style looks different even where geometry is similar",
            details=f"Foreground color delta is {color_delta}. Geometry is close enough that asset choice is suspect.",
            likely_fixes=[
                "Review sprite/prefab candidate selection before changing layout.",
                "Collapse decorative regions back into a single baked image if they were over-modeled.",
                "Avoid tinting placeholders when a real project asset likely exists.",
            ],
            suspect_nodes=suspect_nodes,
        ))

    if diff_coverage >= 0.18 and not issues:
        issues.append(build_issue(
            issue_type="broad_visual_mismatch",
            severity="medium",
            title="A broad mismatch remains between the reference and the captured UI",
            details=f"Diff coverage is {diff_coverage} with normalized mean error {normalized_error}.",
            likely_fixes=[
                "Limit the next repair to the dominant incorrect region.",
                "Inspect the parent chain again before broad redesign.",
                "Verify with a screenshot after the smallest structural fix.",
            ],
            suspect_nodes=suspect_nodes,
        ))

    issues.sort(key=lambda item: severity_rank(item["severity"]), reverse=True)

    return {
        "kind": "ui_verification_report",
        "referenceImage": str(reference_path),
        "capturedImage": str(captured_path),
        "referenceSize": {"width": reference_size[0], "height": reference_size[1]},
        "capturedOriginalSize": {"width": captured_original_size[0], "height": captured_original_size[1]},
        "metrics": {
            "normalizedMeanAbsoluteError": normalized_error,
            "diffCoverage": diff_coverage,
            "foregroundBboxIoU": bbox_iou,
            "foregroundCenterDelta": center_delta,
            "foregroundSizeDelta": size_delta,
            "foregroundColorDelta": color_delta,
            "diffThreshold": round(diff_threshold, 2),
        },
        "regions": {
            "referenceForeground": reference_box,
            "capturedForeground": captured_box,
            "dominantDiff": diff_bbox,
        },
        "diagnostics": {
            "referenceForeground": reference_diag,
            "capturedForeground": captured_diag,
        },
        "suspectNodes": suspect_nodes,
        "issues": issues,
        "hasMeaningfulMismatch": bool(issues),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze the mismatch between a reference image and a captured Unity UI screenshot."
    )
    parser.add_argument("reference_image", type=Path, help="Path to the target reference image")
    parser.add_argument("captured_image", type=Path, help="Path to the captured Unity screenshot")
    parser.add_argument("--resolved-blueprint", type=Path, help="Optional resolved blueprint for suspect-node mapping")
    parser.add_argument("--output", type=Path, help="Path to write the verification report JSON")
    args = parser.parse_args()

    blueprint = None
    if args.resolved_blueprint:
        blueprint = load_json(args.resolved_blueprint.expanduser().resolve())

    reference_path = args.reference_image.expanduser().resolve()
    captured_path = args.captured_image.expanduser().resolve()
    report = analyze(
        reference_path=reference_path,
        captured_path=captured_path,
        blueprint=blueprint,
    )

    output_path = args.output or captured_path.with_name(f"{captured_path.stem}.verification-report.json")
    save_json(output_path, report)
    print(json.dumps({
        "output": str(output_path),
        "hasMeaningfulMismatch": report["hasMeaningfulMismatch"],
        "issueCount": len(report["issues"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
