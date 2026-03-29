#!/usr/bin/env python3
import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    retrieval_dir = Path(__file__).resolve().parent
    if str(retrieval_dir) not in sys.path:
        sys.path.insert(0, str(retrieval_dir))
    from search_catalog import Query, resolve_vector_index_path, search
    from vector_index import load_jsonl, load_vector_index, score_query_against_index
else:
    from .search_catalog import Query, resolve_vector_index_path, search
    from .vector_index import load_jsonl, load_vector_index, score_query_against_index


BINDING_STATE_AUTO_BIND = "auto_bind"
BINDING_STATE_HOLD = "hold"
BINDING_STATE_REVIEW_NEEDED = "review_needed"
HOLD_BINDING_POLICIES = {"hold_if_uncertain", "preserve_candidates"}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def infer_aspect_ratio(node: dict[str, Any], fallback: float | None) -> float | None:
    if fallback is not None:
        return fallback

    rect = node.get("rect") or {}
    size_delta = rect.get("sizeDelta") or {}
    width = size_delta.get("x")
    height = size_delta.get("y")
    if isinstance(width, (int, float)) and isinstance(height, (int, float)) and height not in (0, 0.0):
        return float(width) / float(height)
    return None


def preferred_kind_for_node(node: dict[str, Any], target: str) -> str | None:
    if target == "fontAsset":
        return "tmp_font"

    kind = (node.get("kind") or "").lower()
    if kind == "image":
        return "sprite"
    if kind == "prefab_instance":
        return "prefab"
    return None


def build_query(query_spec: dict[str, Any], node: dict[str, Any], target: str) -> Query:
    query_text = query_spec.get("queryText")
    if not query_text:
        raise ValueError("assetQuery requires queryText.")

    preferred_kind = query_spec.get("preferredKind") or preferred_kind_for_node(node, target)
    aspect_ratio = None if target == "fontAsset" else infer_aspect_ratio(node, query_spec.get("aspectRatio"))
    top_k = int(query_spec.get("topK") or 5)

    return Query(
        query_text=query_text,
        region_type=query_spec.get("regionType"),
        preferred_kind=preferred_kind,
        aspect_ratio=aspect_ratio,
        top_k=max(1, top_k),
    )


def build_asset_reference(candidate: dict[str, Any], forced_kind: str | None = None) -> dict[str, Any]:
    binding = candidate.get("binding") or {}
    reference = {
        "kind": forced_kind or binding.get("kind"),
        "path": candidate.get("path"),
        "guid": candidate.get("guid"),
        "localFileId": candidate.get("localFileId"),
        "subAssetName": candidate.get("subAssetName"),
    }
    return {
        key: value
        for key, value in reference.items()
        if value not in (None, "", 0)
    }


def select_candidate(query_spec: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    binding_policy = (query_spec.get("bindingPolicy") or "require_confident").lower()
    min_score = float(query_spec.get("minScore") or 0.55)

    if not results:
        return {
            "bindingState": BINDING_STATE_REVIEW_NEEDED,
            "bindingDecision": "no_candidates",
            "selectedCandidate": None,
            "appliedCandidate": None,
            "topScore": None,
            "minScore": min_score,
            "shouldBind": False,
        }

    top = results[0]
    top_score = float(top.get("score", 0.0))

    if binding_policy == "best_match":
        return {
            "bindingState": BINDING_STATE_AUTO_BIND,
            "bindingDecision": "best_match",
            "selectedCandidate": top,
            "appliedCandidate": top,
            "topScore": top_score,
            "minScore": min_score,
            "shouldBind": True,
        }

    if top_score >= min_score:
        return {
            "bindingState": BINDING_STATE_AUTO_BIND,
            "bindingDecision": "confident_match",
            "selectedCandidate": top,
            "appliedCandidate": top,
            "topScore": top_score,
            "minScore": min_score,
            "shouldBind": True,
        }

    if binding_policy in HOLD_BINDING_POLICIES:
        return {
            "bindingState": BINDING_STATE_HOLD,
            "bindingDecision": f"low_confidence_hold:{top_score:.4f}<{min_score:.4f}",
            "selectedCandidate": top,
            "appliedCandidate": None,
            "topScore": top_score,
            "minScore": min_score,
            "shouldBind": False,
        }

    return {
        "bindingState": BINDING_STATE_REVIEW_NEEDED,
        "bindingDecision": f"low_confidence_review:{top_score:.4f}<{min_score:.4f}",
        "selectedCandidate": top,
        "appliedCandidate": None,
        "topScore": top_score,
        "minScore": min_score,
        "shouldBind": False,
    }


def resolve_query(
    query_spec: dict[str, Any],
    node: dict[str, Any],
    target: str,
    records: list[dict[str, Any]],
    vector_index: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], Query]:
    query = build_query(query_spec, node, target)
    vector_scores = None
    if vector_index is not None:
        vector_scores = score_query_against_index(query.query_text, vector_index)
    results = search(query, records, vector_scores)
    selection = select_candidate(query_spec, results)
    return selection, results, query


def _count_binding_state(summary: dict[str, int], state: str) -> None:
    summary[state] = summary.get(state, 0) + 1


def bind_blueprint(
    blueprint: dict[str, Any],
    records: list[dict[str, Any]],
    vector_index: dict[str, Any] | None,
    allow_partial: bool,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    resolved = deepcopy(blueprint)
    report = {
        "resolvedAtUtc": datetime.now(timezone.utc).isoformat(),
        "screenName": resolved.get("screenName"),
        "bindings": [],
        "issues": [],
        "summary": {
            "bindingStates": {
                BINDING_STATE_AUTO_BIND: 0,
                BINDING_STATE_HOLD: 0,
                BINDING_STATE_REVIEW_NEEDED: 0,
            },
            "bindingCount": 0,
        },
    }
    has_errors = False

    def walk(node: dict[str, Any], hierarchy_path: str) -> None:
        nonlocal has_errors

        node_name = node.get("name") or node.get("id") or "UnnamedNode"
        current_path = f"{hierarchy_path}/{node_name}" if hierarchy_path else node_name

        asset_query = node.pop("assetQuery", None)
        if isinstance(asset_query, dict):
            selection, results, query = resolve_query(asset_query, node, "asset", records, vector_index)
            entry = {
                "nodeId": node.get("id"),
                "nodeName": node.get("name"),
                "hierarchyPath": current_path,
                "target": "asset",
                "query": {
                    "queryText": query.query_text,
                    "regionType": query.region_type,
                    "preferredKind": query.preferred_kind,
                    "aspectRatio": query.aspect_ratio,
                },
                "bindingPolicy": (asset_query.get("bindingPolicy") or "require_confident"),
                "bindingState": selection["bindingState"],
                "bindingDecision": selection["bindingDecision"],
                "topScore": selection["topScore"],
                "minScore": selection["minScore"],
                "chosenCandidate": selection["selectedCandidate"],
                "appliedCandidate": selection["appliedCandidate"],
                "alternatives": results[:3],
            }
            if selection["shouldBind"]:
                node["asset"] = build_asset_reference(selection["appliedCandidate"])
            else:
                node["assetQuery"] = asset_query
                if selection["bindingState"] == BINDING_STATE_REVIEW_NEEDED:
                    has_errors = True
                    report["issues"].append({
                        "severity": "error",
                        "nodeId": node.get("id"),
                        "nodeName": node.get("name"),
                        "target": "asset",
                        "message": f"Could not resolve asset query for {current_path}: {selection['bindingDecision']}",
                    })
            report["bindings"].append(entry)
            _count_binding_state(report["summary"]["bindingStates"], selection["bindingState"])

        text = node.get("text")
        if isinstance(text, dict):
            font_query = text.pop("fontAssetQuery", None)
            if isinstance(font_query, dict):
                selection, results, query = resolve_query(font_query, node, "fontAsset", records, vector_index)
                entry = {
                    "nodeId": node.get("id"),
                    "nodeName": node.get("name"),
                    "hierarchyPath": current_path,
                    "target": "fontAsset",
                    "query": {
                        "queryText": query.query_text,
                        "regionType": query.region_type,
                        "preferredKind": query.preferred_kind,
                        "aspectRatio": query.aspect_ratio,
                    },
                    "bindingPolicy": (font_query.get("bindingPolicy") or "require_confident"),
                    "bindingState": selection["bindingState"],
                    "bindingDecision": selection["bindingDecision"],
                    "topScore": selection["topScore"],
                    "minScore": selection["minScore"],
                    "chosenCandidate": selection["selectedCandidate"],
                    "appliedCandidate": selection["appliedCandidate"],
                    "alternatives": results[:3],
                }
                if selection["shouldBind"]:
                    text["fontAsset"] = build_asset_reference(selection["appliedCandidate"], forced_kind="tmp_font")
                else:
                    text["fontAssetQuery"] = font_query
                    if selection["bindingState"] == BINDING_STATE_REVIEW_NEEDED:
                        has_errors = True
                        report["issues"].append({
                            "severity": "error",
                            "nodeId": node.get("id"),
                            "nodeName": node.get("name"),
                            "target": "fontAsset",
                            "message": f"Could not resolve font query for {current_path}: {selection['bindingDecision']}",
                        })
                report["bindings"].append(entry)
                _count_binding_state(report["summary"]["bindingStates"], selection["bindingState"])

        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child, current_path)

    root = resolved.get("root")
    if isinstance(root, dict):
        walk(root, "")
    else:
        has_errors = True
        report["issues"].append({
            "severity": "error",
            "message": "Blueprint root is missing or invalid.",
        })

    report["summary"]["bindingCount"] = len(report["bindings"])
    return resolved, report, has_errors


def default_output_path(template_path: Path) -> Path:
    return template_path.with_name(f"{template_path.stem}.resolved.json")


def default_report_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}.binding-report.json")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve blueprint assetQuery/fontAssetQuery entries into concrete Unity asset references."
    )
    parser.add_argument("blueprint_template", type=Path, help="Path to blueprint template JSON")
    parser.add_argument("catalog", type=Path, help="Path to resource_catalog.jsonl")
    parser.add_argument("--output", type=Path, help="Path to write the resolved blueprint JSON")
    parser.add_argument("--report", type=Path, help="Path to write the binding report JSON")
    parser.add_argument("--vector-index", type=Path, help="Optional path to resource_vector_index.json")
    parser.add_argument("--allow-partial", action="store_true", help="Keep unresolved queries in the output blueprint instead of failing hard")
    args = parser.parse_args()

    template = load_json(args.blueprint_template)
    records = load_jsonl(args.catalog)
    vector_index_path = resolve_vector_index_path(args.catalog, args.vector_index)
    vector_index = None
    if vector_index_path is not None and vector_index_path.exists():
        vector_index = load_vector_index(vector_index_path)

    resolved, report, has_errors = bind_blueprint(
        template,
        records,
        vector_index,
        allow_partial=args.allow_partial,
    )

    output_path = args.output or default_output_path(args.blueprint_template)
    report_path = args.report or default_report_path(output_path)

    report["blueprintTemplate"] = str(args.blueprint_template)
    report["catalog"] = str(args.catalog)
    report["vectorIndex"] = str(vector_index_path) if vector_index_path else None
    report["resolvedBlueprint"] = str(output_path)
    report["hasErrors"] = has_errors

    save_json(output_path, resolved)
    save_json(report_path, report)

    print(json.dumps({
        "output": str(output_path),
        "report": str(report_path),
        "bindingCount": len(report["bindings"]),
        "issueCount": len(report["issues"]),
        "hasErrors": has_errors,
    }, ensure_ascii=False, indent=2))

    if has_errors and not args.allow_partial:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
