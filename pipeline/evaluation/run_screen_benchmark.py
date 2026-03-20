#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from .fixtures import load_benchmark_report, load_benchmark_suite, save_json
from .models import BenchmarkFixtureError, SCHEMA_VERSION
from .report_models import BenchmarkRunReport, BenchmarkRunSummary, BenchmarkScreenResult


DEFAULT_OUTPUT_SUFFIX = ".screen-scorecard.json"
RUN_KIND = "screen_benchmark_scorecard"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise BenchmarkFixtureError(f"Expected JSON object in {path}.")
    return payload


def _result_lookup(results: tuple[BenchmarkScreenResult, ...]) -> dict[str, BenchmarkScreenResult]:
    lookup: dict[str, BenchmarkScreenResult] = {}
    for result in results:
        if result.screen_name in lookup:
            raise BenchmarkFixtureError(f"Duplicate screen result for '{result.screen_name}'.")
        lookup[result.screen_name] = result
    return lookup


def _screen_bundle_lookup(suite: Any) -> dict[str, Any]:
    lookup: dict[str, Any] = {}
    for bundle in suite.screens:
        lookup[bundle.entry.screen_name] = bundle
    return lookup


def _screen_payload_lookup(report_payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    payload_lookup: dict[str, Mapping[str, Any]] = {}
    results = report_payload.get("results", [])
    if not isinstance(results, list):
        raise BenchmarkFixtureError("Expected list at 'results'.")
    for item in results:
        if isinstance(item, Mapping):
            screen_name = item.get("screenName")
            if isinstance(screen_name, str) and screen_name:
                payload_lookup[screen_name] = item
    return payload_lookup


def _issue_types(payload: Mapping[str, Any]) -> tuple[str, ...]:
    issues = payload.get("issues", [])
    if not isinstance(issues, list):
        raise BenchmarkFixtureError("Expected list at 'issues'.")
    types = []
    for item in issues:
        if isinstance(item, Mapping):
            issue_type = item.get("type")
            if isinstance(issue_type, str) and issue_type:
                types.append(issue_type)
    return tuple(types)


def _screen_check(
    *,
    result: BenchmarkScreenResult,
    report_payload: Mapping[str, Any],
    thresholds: Any,
    expected_mismatch_classes: tuple[str, ...],
) -> dict[str, Any]:
    checks = {
        "screenName": result.screen_name,
        "status": result.status,
        "thresholds": {
            "retrievalTop1Min": thresholds.retrieval_top1_min,
            "retrievalTop3Min": thresholds.retrieval_top3_min,
            "normalizedMeanAbsoluteErrorMax": thresholds.normalized_mean_absolute_error_max,
            "foregroundBboxIoUMin": thresholds.foreground_bbox_iou_min,
            "maxRepairIterations": thresholds.max_repair_iterations,
        },
        "metrics": {
            "retrievalTop1HitRate": result.retrieval_top1_hit_rate,
            "retrievalTop3HitRate": result.retrieval_top3_hit_rate,
            "normalizedMeanAbsoluteError": result.normalized_mean_absolute_error,
            "foregroundBboxIoU": result.foreground_bbox_iou,
            "repairIterations": result.repair_iterations,
            "hasMeaningfulMismatch": result.has_meaningful_mismatch,
        },
        "expectedMismatchClasses": list(expected_mismatch_classes),
        "observedIssueTypes": list(_issue_types(report_payload)),
        "notes": list(result.notes),
    }

    status = "pass"
    if result.retrieval_top1_hit_rate < thresholds.retrieval_top1_min:
        status = "fail"
    if result.retrieval_top3_hit_rate < thresholds.retrieval_top3_min:
        status = "fail"
    if result.normalized_mean_absolute_error > thresholds.normalized_mean_absolute_error_max:
        status = "fail"
    if result.foreground_bbox_iou < thresholds.foreground_bbox_iou_min:
        status = "fail"
    if result.repair_iterations > thresholds.max_repair_iterations:
        status = "fail"
    if result.status != "pass":
        status = "fail"

    if checks["observedIssueTypes"] and expected_mismatch_classes:
        unexpected = [item for item in checks["observedIssueTypes"] if item not in expected_mismatch_classes]
        if unexpected:
            checks["notes"].append(f"unexpected issue types: {unexpected}")
            status = "fail"

    checks["status"] = status
    return checks


def evaluate_screen_benchmark(manifest_path: Path, report_path: Path) -> dict[str, Any]:
    suite = load_benchmark_suite(manifest_path)
    raw_report = _load_json(report_path)
    report = load_benchmark_report(report_path)

    if report.schema_version != SCHEMA_VERSION:
        raise BenchmarkFixtureError(f"Expected schemaVersion '{SCHEMA_VERSION}'.")
    if report.benchmark_name != suite.manifest.benchmark_name:
        raise BenchmarkFixtureError("Benchmark name does not match suite manifest.")
    if report.project_name != suite.manifest.project_name:
        raise BenchmarkFixtureError("Project name does not match suite manifest.")

    result_lookup = _result_lookup(report.results)
    bundle_lookup = _screen_bundle_lookup(suite)
    report_payload_lookup = _screen_payload_lookup(raw_report)
    results: list[BenchmarkScreenResult] = []
    screen_checks: list[dict[str, Any]] = []
    all_passed = True

    for screen in suite.manifest.screens:
        result = result_lookup.get(screen.screen_name)
        if result is None:
            raise BenchmarkFixtureError(f"Missing screen result for '{screen.screen_name}'.")
        results.append(result)
        bundle = bundle_lookup[screen.screen_name]
        report_payload = report_payload_lookup.get(screen.screen_name, {})
        screen_check = _screen_check(
            result=result,
            report_payload=report_payload,
            thresholds=bundle.thresholds,
            expected_mismatch_classes=bundle.screen_fixture.expected_mismatch_classes,
        )
        screen_checks.append(screen_check)
        all_passed = all_passed and screen_check["status"] == "pass"

    summary = BenchmarkRunSummary.from_results(tuple(results))
    report_dict = BenchmarkRunReport(
        schema_version=report.schema_version,
        benchmark_name=report.benchmark_name,
        project_name=report.project_name,
        generated_at_utc=report.generated_at_utc,
        results=tuple(results),
        summary=summary,
        notes=report.notes,
    ).to_dict()

    return {
        "kind": RUN_KIND,
        "suiteManifest": str(manifest_path.expanduser().resolve()),
        "reportPayload": str(report_path.expanduser().resolve()),
        **report_dict,
        "screenChecks": screen_checks,
        "hasErrors": not all_passed,
    }


def default_output_path(report_path: Path) -> Path:
    return report_path.with_name(f"{report_path.stem}{DEFAULT_OUTPUT_SUFFIX}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score screen verification reports against benchmark fixtures and thresholds."
    )
    parser.add_argument("suite_manifest", type=Path, help="Path to the benchmark suite manifest JSON")
    parser.add_argument("report_payload", type=Path, help="Path to the benchmark run report JSON")
    parser.add_argument("--output", type=Path, help="Path to write the screen benchmark scorecard JSON")
    args = parser.parse_args(argv)

    output = evaluate_screen_benchmark(args.suite_manifest, args.report_payload)
    output_path = args.output or default_output_path(args.report_payload)
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
