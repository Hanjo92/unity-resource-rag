#!/usr/bin/env python3
import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


SAFE_AREA_ROOT_ID = "safe_area_root"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def copy_if_present(target: dict[str, Any], source: dict[str, Any], key: str) -> None:
    if key in source and source[key] is not None:
        target[key] = deepcopy(source[key])


def validate_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    resolution = plan.get("referenceResolution") or {}
    if not isinstance(resolution.get("x"), (int, float)) or not isinstance(resolution.get("y"), (int, float)):
        errors.append("referenceResolution.x and referenceResolution.y are required.")

    seen_ids: set[str] = set()
    regions = plan.get("regions") or []
    for region in regions:
        region_id = region.get("id")
        if not region_id:
            errors.append("Every region requires an id.")
            continue
        if region_id in seen_ids:
            errors.append(f"Duplicate region id: {region_id}")
        seen_ids.add(region_id)

    valid_parent_ids = seen_ids | {SAFE_AREA_ROOT_ID}
    for region in regions:
        parent_id = region.get("parentId") or SAFE_AREA_ROOT_ID
        region_id = region.get("id") or "unknown"
        if parent_id not in valid_parent_ids:
            errors.append(f"Region '{region_id}' references missing parentId '{parent_id}'.")

    return errors


def make_canvas_scaler(plan: dict[str, Any]) -> dict[str, Any]:
    resolution = plan.get("referenceResolution") or {}
    return {
        "uiScaleMode": "ScaleWithScreenSize",
        "referenceResolution": {
            "x": int(resolution.get("x", 1920)),
            "y": int(resolution.get("y", 1080)),
        },
        "screenMatchMode": "MatchWidthOrHeight",
        "matchWidthOrHeight": 0.5,
    }


def make_safe_area_root(plan: dict[str, Any]) -> dict[str, Any]:
    safe_area = plan.get("safeAreaRoot") or {}
    node = {
        "id": SAFE_AREA_ROOT_ID,
        "name": safe_area.get("name") or "SafeAreaRoot",
        "kind": "container",
        "rect": {
            "anchorMin": {"x": 0, "y": 0},
            "anchorMax": {"x": 1, "y": 1},
            "offsetMin": {"x": 0, "y": 0},
            "offsetMax": {"x": 0, "y": 0},
        },
    }
    if safe_area.get("components"):
        node["components"] = deepcopy(safe_area["components"])
    return node


def make_asset_query(region: dict[str, Any], node_kind: str, aspect_ratio: float | None) -> dict[str, Any] | None:
    if region.get("assetQuery"):
        return deepcopy(region["assetQuery"])

    query_text = region.get("queryText")
    if not query_text:
        return None

    preferred_kind = region.get("preferredKind")
    if not preferred_kind:
        if node_kind == "image":
            preferred_kind = "sprite"
        elif node_kind == "prefab_instance":
            preferred_kind = "prefab"

    query = {
        "queryText": query_text,
        "regionType": region.get("regionType"),
        "preferredKind": preferred_kind,
        "bindingPolicy": region.get("bindingPolicy") or "require_confident",
        "minScore": region.get("minScore", 0.55),
        "topK": region.get("topK", 5),
    }
    if aspect_ratio is not None:
        query["aspectRatio"] = round(aspect_ratio, 4)
    return query


def make_text_spec(region: dict[str, Any]) -> dict[str, Any] | None:
    if "text" not in region:
        return None

    text = deepcopy(region.get("text") or {})
    if "fontAssetQuery" not in text and text.get("fontQueryText"):
        text["fontAssetQuery"] = {
            "queryText": text.pop("fontQueryText"),
            "preferredKind": text.pop("fontPreferredKind", "tmp_font"),
            "bindingPolicy": text.pop("fontBindingPolicy", "require_confident"),
            "minScore": text.pop("fontMinScore", 0.45),
        }
    return text


def compute_frame_from_bounds(parent_frame: dict[str, float], bounds: dict[str, Any]) -> dict[str, float]:
    x = float(bounds.get("x", 0.0))
    y = float(bounds.get("y", 0.0))
    w = float(bounds.get("w", 1.0))
    h = float(bounds.get("h", 1.0))
    return {
        "x": parent_frame["x"] + x * parent_frame["w"],
        "y": parent_frame["y"] + y * parent_frame["h"],
        "w": w * parent_frame["w"],
        "h": h * parent_frame["h"],
    }


def compute_rect(parent_frame: dict[str, float], child_frame: dict[str, float], stretch_to_parent: bool) -> dict[str, Any]:
    if stretch_to_parent:
        return {
            "anchorMin": {"x": 0, "y": 0},
            "anchorMax": {"x": 1, "y": 1},
            "offsetMin": {"x": 0, "y": 0},
            "offsetMax": {"x": 0, "y": 0},
        }

    center_x = (child_frame["x"] + child_frame["w"] * 0.5) - (parent_frame["w"] * 0.5)
    center_y = (parent_frame["h"] * 0.5) - (child_frame["y"] + child_frame["h"] * 0.5)
    return {
        "anchorMin": {"x": 0.5, "y": 0.5},
        "anchorMax": {"x": 0.5, "y": 0.5},
        "pivot": {"x": 0.5, "y": 0.5},
        "anchoredPosition": {
            "x": round(center_x, 2),
            "y": round(center_y, 2),
        },
        "sizeDelta": {
            "x": round(child_frame["w"], 2),
            "y": round(child_frame["h"], 2),
        },
    }


def build_node(region: dict[str, Any], parent_frame: dict[str, float]) -> tuple[dict[str, Any], dict[str, float]]:
    node_kind = region.get("kind") or "container"
    stretch_to_parent = bool(region.get("stretchToParent"))

    if stretch_to_parent:
        child_frame = {
            "x": parent_frame["x"],
            "y": parent_frame["y"],
            "w": parent_frame["w"],
            "h": parent_frame["h"],
        }
    else:
        bounds = region.get("normalizedBounds")
        if not isinstance(bounds, dict):
            raise ValueError(f"Region '{region.get('id')}' requires normalizedBounds or stretchToParent.")
        child_frame = compute_frame_from_bounds(parent_frame, bounds)

    node = {
        "id": region.get("id"),
        "name": region.get("name") or region.get("id"),
        "kind": node_kind,
        "rect": compute_rect(parent_frame, child_frame, stretch_to_parent),
    }

    if "active" in region:
        node["active"] = bool(region["active"])

    for key in ("image", "layoutGroup", "layoutElement", "components", "canvasScaler"):
        copy_if_present(node, region, key)

    if node_kind in {"image", "prefab_instance"}:
        copy_if_present(node, region, "asset")
        aspect_ratio = None if child_frame["h"] == 0 else child_frame["w"] / child_frame["h"]
        asset_query = make_asset_query(region, node_kind, aspect_ratio)
        if asset_query:
            node["assetQuery"] = asset_query

    if node_kind == "tmp_text":
        text = make_text_spec(region)
        if text:
            node["text"] = text

    return node, child_frame


def build_blueprint(plan: dict[str, Any]) -> dict[str, Any]:
    resolution = plan.get("referenceResolution") or {}
    root_frame = {
        "x": 0.0,
        "y": 0.0,
        "w": float(resolution.get("x", 1920)),
        "h": float(resolution.get("y", 1080)),
    }

    regions = plan.get("regions") or []
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    for region in regions:
        parent_id = region.get("parentId") or SAFE_AREA_ROOT_ID
        children_by_parent.setdefault(parent_id, []).append(region)

    def build_children(parent_id: str, parent_frame: dict[str, float]) -> list[dict[str, Any]]:
        nodes: list[dict[str, Any]] = []
        for region in children_by_parent.get(parent_id, []):
            node, child_frame = build_node(region, parent_frame)
            child_nodes = build_children(region["id"], child_frame)
            if child_nodes:
                node["children"] = child_nodes
            nodes.append(node)
        return nodes

    safe_area_root = make_safe_area_root(plan)
    safe_area_root["children"] = build_children(SAFE_AREA_ROOT_ID, root_frame)

    blueprint = {
        "screenName": plan.get("screenName") or "GeneratedScreen",
        "stack": "ugui",
        "root": {
            "id": "root_canvas",
            "name": plan.get("rootCanvasName") or f"{plan.get('screenName') or 'GeneratedScreen'}Canvas",
            "kind": "canvas",
            "canvasScaler": make_canvas_scaler(plan),
            "children": [safe_area_root],
        },
    }
    return blueprint


def default_output_path(plan_path: Path) -> Path:
    return plan_path.with_name(f"{plan_path.stem}.template.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a reference layout plan into a blueprint template with asset queries."
    )
    parser.add_argument("reference_layout", type=Path, help="Path to reference layout plan JSON")
    parser.add_argument("--output", type=Path, help="Path to write the blueprint template JSON")
    args = parser.parse_args()

    plan = load_json(args.reference_layout)
    errors = validate_plan(plan)
    if errors:
        print(json.dumps({
            "errors": errors,
        }, ensure_ascii=False, indent=2))
        return 1

    blueprint = build_blueprint(plan)
    output_path = args.output or default_output_path(args.reference_layout)
    save_json(output_path, blueprint)

    print(json.dumps({
        "output": str(output_path),
        "screenName": blueprint.get("screenName"),
        "regionCount": len(plan.get("regions") or []),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
