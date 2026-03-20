#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any, Mapping

from .fixtures import load_benchmark_suite, save_json
from .models import BenchmarkFixtureError, SCHEMA_VERSION
from .report_models import BenchmarkRunReport, BenchmarkRunSummary, BenchmarkScreenResult


DEFAULT_OUTPUT_SUFFIX = ".retrieval-scorecard.json"
RUN_KIND = "retrieval_benchmark_scorecard"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise BenchmarkFixtureError(f"Expected JSON object in {path}.")
    return payload


def _require_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise BenchmarkFixtureError(f"Expected mapping at '{key}'.")
    return value


def _require_list(payload: Mapping[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise BenchmarkFixtureError(f"Expected list at '{key}'.")
    return value


def _require_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise BenchmarkFixtureError(f"Expected non-empty string at '{key}'.")
    return value


def _require_float(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)):
        raise BenchmarkFixtureError(f"Expected number at '{key}'.")
    return float(value)


def _optional_float(payload: Mapping[str, Any], key: str, default: float) -> float:
    value = payload.get(key)
    if value is None:
        return default
    if not isinstance(value, (int, float)):
        raise BenchmarkFixtureError(f"Expected number at '{key}'.")
    return float(value)


def _optional_int(payload: Mapping[str, Any], key: str, default: int) -> int:
    value = payload.get(key)
    if value is None:
        return default
    if not isinstance(value, int):
        raise BenchmarkFixtureError(f"Expected integer at '{key}'.")
    return value


def _optional_bool(payload: Mapping[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise BenchmarkFixtureError(f"Expected boolean at '{key}'.")
    return value


def _find_screen_payload(payload: Mapping[str, Any], screen_name: str) -> Mapping[str, Any]:
    for item in _require_list(payload, "screens"):
        if isinstance(item, Mapping) and item.get("screenName") == screen_name:
            return item
    raise BenchmarkFixtureError(f"Missing screen result for '{screen_name}'.")


def _screen_results_by_region(screen_payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    region_results = _require_list(screen_payload, "regions")
    if not region_results:
        raise BenchmarkFixtureError(f"Screen '{_require_str(screen_payload, 'screenName')}' must contain at least one region result.")
    results: dict[str, Mapping[str, Any]] = {}
    for item in region_results:
        if not isinstance(item, Mapping):
            raise BenchmarkFixtureError("Region results must be objects.")
        region_id = _require_str(item, "regionId")
        if region_id in results:
            raise BenchmarkFixtureError(f"Duplicate region result for '{region_id}'.")
        results[region_id] = item
    return results


def _region_score(item: Mapping[str, Any], fixture_min_score: float | None) -> tuple[float, float, bool, list[str]]:
    top1 = _require_float(item, "top1HitRate")
    top3 = _require_float(item, "top3HitRate")
    candidate_score = _optional_float(item, "selectedCandidateScore", _optional_float(item, "candidateScore", _optional_float(item, "score", 0.0)))
    decision = str(item.get("bindingDecision") or item.get("decision") or "").strip()
    notes = [str(note) for note in item.get("notes", []) if isinstance(note, str) and note]

    min_score = fixture_min_score if fixture_min_score is not None else 0.55
    passed = candidate_score >= min_score
    if decision == "fallback_to_layout_only" and min_score > 0.0:
        passed = False

    if candidate_score < min_score:
        notes.append(f"candidateScore {candidate_score:.4f} below minScore {min_score:.4f}")
    if decision:
        notes.append(f"decision={decision}")
    return top1, top3, passed, notes


def _screen_result(
    *,
    screen_name: str,
    screen_payload: Mapping[str, Any],
    retrieval_fixture: Any,
    thresholds: Any,
) -> tuple[BenchmarkScreenResult, dict[str, Any], bool]:
    region_results = _screen_results_by_region(screen_payload)
    expected_region_ids = [region.region_id for region in retrieval_fixture.regions]
    unexpected_region_ids = [region_id for region_id in region_results if region_id not in expected_region_ids]
    missing_region_ids = [region_id for region_id in expected_region_ids if region_id not in region_results]
    if unexpected_region_ids:
        raise BenchmarkFixtureError(f"Screen '{screen_name}' included unexpected region ids: {unexpected_region_ids}.")
    if missing_region_ids:
        raise BenchmarkFixtureError(f"Screen '{screen_name}' is missing region ids: {missing_region_ids}.")

    top1_values: list[float] = []
    top3_values: list[float] = []
    region_checks: list[dict[str, Any]] = []
    region_passed = True

    for region in retrieval_fixture.regions:
        item = region_results[region.region_id]
        top1, top3, passed, notes = _region_score(item, region.min_score)
        top1_values.append(top1)
        top3_values.append(top3)
        region_passed = region_passed and passed
        region_checks.append(
            {
                "regionId": region.region_id,
                "regionType": region.region_type,
                "status": "pass" if passed else "fail",
                "top1HitRate": top1,
                "top3HitRate": top3,
                "candidateScore": _optional_float(
                    item,
                    "selectedCandidateScore",
                    _optional_float(item, "candidateScore", _optional_float(item, "score", 0.0)),
                ),
                "minScore": region.min_score if region.min_score is not None else 0.55,
                "bindingPolicy": region.binding_policy,
                "notes": notes,
            }
        )

    retrieval_top1 = mean(top1_values)
    retrieval_top3 = mean(top3_values)
    status = "pass" if (
        region_passed
        and retrieval_top1 >= thresholds.retrieval_top1_min
        and retrieval_top3 >= thresholds.retrieval_top3_min
    ) else "fail"

    result = BenchmarkScreenResult(
        screen_name=screen_name,
        retrieval_top1_hit_rate=round(retrieval_top1, 4),
        retrieval_top3_hit_rate=round(retrieval_top3, 4),
        normalized_mean_absolute_error=0.0,
        foreground_bbox_iou=1.0,
        repair_iterations=0,
        has_meaningful_mismatch=status != "pass",
        status=status,
        notes=tuple(
            note
            for note in (
                *[note for item in screen_payload.get("notes", []) if isinstance(item, str) and item for note in [item]],
                *(f"missing regions: {missing_region_ids}" if missing_region_ids else []),
            )
            if note
        ),
    )
    screen_check = {
        "screenName": screen_name,
        "status": status,
        "thresholds": {
            "retrievalTop1Min": thresholds.retrieval_top1_min,
            "retrievalTop3Min": thresholds.retrieval_top3_min,
        },
        "aggregate": {
            "retrievalTop1HitRate": result.retrieval_top1_hit_rate,
            "retrievalTop3HitRate": result.retrieval_top3_hit_rate,
        },
        "regionChecks": region_checks,
    }
    return result, screen_check, status == "pass"


def evaluate_retrieval_benchmark(manifest_path: Path, result_path: Path) -> dict[str, Any]:
    suite = load_benchmark_suite(manifest_path)
    payload = _load_json(result_path)

    if _require_str(payload, "schemaVersion") != SCHEMA_VERSION:
        raise BenchmarkFixtureError(f"Expected schemaVersion '{SCHEMA_VERSION}'.")
    if _require_str(payload, "benchmarkName") != suite.manifest.benchmark_name:
        raise BenchmarkFixtureError("Benchmark name does not match suite manifest.")
    if _require_str(payload, "projectName") != suite.manifest.project_name:
        raise BenchmarkFixtureError("Project name does not match suite manifest.")

    screen_lookup = {bundle.entry.screen_name: bundle for bundle in suite.screens}
    results: list[BenchmarkScreenResult] = []
    screen_checks: list[dict[str, Any]] = []
    all_passed = True

    for screen in suite.manifest.screens:
        screen_payload = _find_screen_payload(payload, screen.screen_name)
        bundle = screen_lookup[screen.screen_name]
        result, screen_check, passed = _screen_result(
            screen_name=screen.screen_name,
            screen_payload=screen_payload,
            retrieval_fixture=bundle.retrieval_fixture,
            thresholds=bundle.thresholds,
        )
        results.append(result)
        screen_checks.append(screen_check)
        all_passed = all_passed and passed

    report = BenchmarkRunReport(
        schema_version=SCHEMA_VERSION,
        benchmark_name=suite.manifest.benchmark_name,
        project_name=suite.manifest.project_name,
        generated_at_utc=_require_str(payload, "generatedAtUtc"),
        results=tuple(results),
        summary=BenchmarkRunSummary.from_results(tuple(results)),
        notes=tuple(
            item for item in payload.get("notes", []) if isinstance(item, str) and item
        ),
    ).to_dict()

    return {
        "kind": RUN_KIND,
        "suiteManifest": str(manifest_path.expanduser().resolve()),
        "resultPayload": str(result_path.expanduser().resolve()),
        **report,
        "screenChecks": screen_checks,
        "hasErrors": not all_passed,
    }


def default_output_path(result_path: Path) -> Path:
    return result_path.with_name(f"{result_path.stem}{DEFAULT_OUTPUT_SUFFIX}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score retrieval benchmark result payloads against benchmark fixtures and thresholds."
    )
    parser.add_argument("suite_manifest", type=Path, help="Path to the benchmark suite manifest JSON")
    parser.add_argument("result_payload", type=Path, help="Path to the retrieval result payload JSON")
    parser.add_argument("--output", type=Path, help="Path to write the retrieval benchmark scorecard JSON")
    args = parser.parse_args(argv)

    output = evaluate_retrieval_benchmark(args.suite_manifest, args.result_payload)
    output_path = args.output or default_output_path(args.result_payload)
    save_json(output_path, output)
    print(
        json.dumps(
            {
                "output": str(output_path),
                "hasErrors": bool(output["hasErrors"]),
                "screenCount": output["summary"]["screenCount"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if output["hasErrors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
