#!/usr/bin/env python3
import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    retrieval_dir = Path(__file__).resolve().parent
    if str(retrieval_dir) not in sys.path:
        sys.path.insert(0, str(retrieval_dir))
    from vector_index import load_jsonl, load_vector_index, score_query_against_index
else:
    from .vector_index import load_jsonl, load_vector_index, score_query_against_index

TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


@dataclass
class Query:
    query_text: str
    region_type: str | None
    preferred_kind: str | None
    aspect_ratio: float | None
    top_k: int


def tokenize(text: str | None) -> set[str]:
    if not text:
        return set()
    return {match.group(0).lower() for match in TOKEN_RE.finditer(text)}


def jaccard_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def score_type_fit(query: Query, record: dict[str, Any]) -> float:
    binding_kind = ((record.get("binding") or {}).get("kind") or "").lower()
    asset_type = (record.get("assetType") or "").lower()

    if not query.preferred_kind:
        return 0.5

    preferred = query.preferred_kind.lower()
    if binding_kind == preferred:
        return 1.0

    if preferred == "sprite" and asset_type in {"sprite", "texture2d"}:
        return 0.8

    if preferred == "prefab" and asset_type == "prefab":
        return 1.0

    if preferred == "tmp_font" and (binding_kind == "tmp_font" or asset_type == "tmp_fontasset"):
        return 1.0

    return 0.0


def score_region_fit(query: Query, record: dict[str, Any]) -> float:
    if not query.region_type:
        return 0.5

    region = query.region_type.lower()
    hints = record.get("uiHints") or {}
    preferred_use = [value.lower() for value in (hints.get("preferredUse") or [])]
    semantic = (record.get("semanticText") or "").lower()

    score = 0.0
    if region in preferred_use:
        score += 0.7

    if region.replace("_", " ") in semantic or region.replace("_", "") in semantic:
        score += 0.2

    if "popup" in region and hints.get("isNineSliceCandidate"):
        score += 0.1

    if "inventory" in region and hints.get("isRepeatableBlock"):
        score += 0.1

    return min(score, 1.0)


def score_aspect_ratio(query: Query, record: dict[str, Any]) -> float:
    if query.aspect_ratio is None:
        return 0.5

    geometry = record.get("geometry") or {}
    value = geometry.get("aspectRatio")
    if not value:
        return 0.25

    delta = abs(float(value) - query.aspect_ratio)
    return max(0.0, 1.0 - min(delta, 1.0))


def score_record(
    query: Query,
    record: dict[str, Any],
    vector_score: float,
    use_vector_score: bool,
) -> dict[str, Any]:
    query_tokens = tokenize(query.query_text)
    semantic_tokens = tokenize(record.get("semanticText"))
    path_tokens = tokenize(record.get("path"))
    name_tokens = tokenize(record.get("name"))

    text_score = max(
        jaccard_score(query_tokens, semantic_tokens),
        jaccard_score(query_tokens, path_tokens | name_tokens),
    )
    type_fit = score_type_fit(query, record)
    region_fit = score_region_fit(query, record)
    aspect_fit = score_aspect_ratio(query, record)

    if use_vector_score:
        final_score = (
            0.35 * vector_score
            + 0.25 * text_score
            + 0.20 * type_fit
            + 0.15 * region_fit
            + 0.05 * aspect_fit
        )
    else:
        final_score = (
            0.45 * text_score
            + 0.25 * type_fit
            + 0.20 * region_fit
            + 0.10 * aspect_fit
        )

    reasons: list[str] = []
    if vector_score >= 0.45:
        reasons.append("vector-match")
    if text_score > 0.0:
        reasons.append("text-match")
    if type_fit >= 0.8:
        reasons.append("type-fit")
    if region_fit >= 0.7:
        reasons.append("region-fit")
    if aspect_fit >= 0.8:
        reasons.append("aspect-fit")
    if ((record.get("uiHints") or {}).get("isNineSliceCandidate")):
        reasons.append("nine-slice-candidate")
    if ((record.get("uiHints") or {}).get("isRepeatableBlock")):
        reasons.append("repeatable-block")

    return {
        "id": record.get("id"),
        "guid": record.get("guid"),
        "localFileId": record.get("localFileId"),
        "subAssetName": record.get("subAssetName"),
        "score": round(final_score, 4),
        "path": record.get("path"),
        "name": record.get("name"),
        "assetType": record.get("assetType"),
        "binding": record.get("binding", {}),
        "semanticText": record.get("semanticText"),
        "scoreBreakdown": {
            "vector": round(vector_score, 4),
            "text": round(text_score, 4),
            "typeFit": round(type_fit, 4),
            "regionFit": round(region_fit, 4),
            "aspectFit": round(aspect_fit, 4),
        },
        "reasons": reasons,
    }


def search(
    query: Query,
    records: list[dict[str, Any]],
    vector_scores: dict[str, float] | None,
) -> list[dict[str, Any]]:
    use_vector_score = vector_scores is not None
    scored = [
        score_record(
            query,
            record,
            (vector_scores or {}).get(record.get("id"), 0.0),
            use_vector_score,
        )
        for record in records
    ]
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[: query.top_k]


def resolve_vector_index_path(catalog_path: Path, requested_path: Path | None) -> Path | None:
    if requested_path:
        return requested_path

    default_path = catalog_path.with_name("resource_vector_index.json")
    if default_path.exists():
        return default_path

    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Search a Unity resource catalog using lexical + heuristic scoring.")
    parser.add_argument("catalog", type=Path, help="Path to resource_catalog.jsonl")
    parser.add_argument("--query", required=True, help="Natural language query")
    parser.add_argument("--region-type", help="Optional region type such as popup_frame or inventory")
    parser.add_argument("--preferred-kind", help="Optional binding kind such as sprite or prefab")
    parser.add_argument("--aspect-ratio", type=float, help="Optional desired aspect ratio")
    parser.add_argument("--vector-index", type=Path, help="Optional path to resource_vector_index.json")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to return")
    args = parser.parse_args()

    records = load_jsonl(args.catalog)
    vector_index_path = resolve_vector_index_path(args.catalog, args.vector_index)
    vector_scores: dict[str, float] | None = None
    if vector_index_path is not None and vector_index_path.exists():
        vector_scores = score_query_against_index(
            args.query,
            load_vector_index(vector_index_path),
        )

    query = Query(
        query_text=args.query,
        region_type=args.region_type,
        preferred_kind=args.preferred_kind,
        aspect_ratio=args.aspect_ratio,
        top_k=max(1, args.top_k),
    )

    results = search(query, records, vector_scores)
    print(json.dumps({
        "query": args.query,
        "regionType": args.region_type,
        "preferredKind": args.preferred_kind,
        "aspectRatio": args.aspect_ratio,
        "vectorIndex": str(vector_index_path) if vector_index_path else None,
        "results": results,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
