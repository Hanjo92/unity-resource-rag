#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .fixtures import save_json
from .models import SCHEMA_VERSION
from .run_retrieval_benchmark import evaluate_retrieval_benchmark
from .run_screen_benchmark import evaluate_screen_benchmark


RETRIEVAL_SCORECARD_NAME = "retrieval-scorecard.json"
SCREEN_SCORECARD_NAME = "screen-scorecard.json"
GATE_REPORT_NAME = "benchmark-gate-report.json"
GATE_REPORT_MARKDOWN_NAME = "benchmark-gate-report.md"
RUN_KIND = "benchmark_gate_report"


def _find_repo_root(*paths: Path) -> Path:
    for path in paths:
        resolved = path.expanduser().resolve()
        for candidate in (resolved, *resolved.parents):
            if candidate.is_dir() and (candidate / ".git").exists():
                return candidate
    return Path.cwd().expanduser().resolve()


def _relativize_path(path: str | Path | None, repo_root: Path) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        return str(candidate)
    try:
        return str(candidate.relative_to(repo_root))
    except ValueError:
        return str(candidate)


def _normalize_scorecard_paths(payload: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    normalized = deepcopy(payload)
    for key in ("suiteManifest", "resultPayload", "reportPayload"):
        if key in normalized:
            normalized[key] = _relativize_path(normalized.get(key), repo_root)
    return normalized


def _relative_artifact_path(path: Path, output_dir: Path) -> str:
    return str(path.expanduser().resolve().relative_to(output_dir.expanduser().resolve()))


def _failed_retrieval_regions(scorecard: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for screen in scorecard.get("screenChecks", []):
        if not isinstance(screen, dict):
            continue
        screen_name = str(screen.get("screenName") or "unknown_screen")
        for region in screen.get("regionChecks", []):
            if not isinstance(region, dict):
                continue
            if region.get("status") != "fail":
                continue
            region_id = str(region.get("regionId") or "unknown_region")
            failures.append(f"{screen_name}:{region_id}")
    return failures


def _failed_screen_checks(scorecard: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for screen in scorecard.get("screenChecks", []):
        if not isinstance(screen, dict):
            continue
        if screen.get("status") == "fail":
            failures.append(str(screen.get("screenName") or "unknown_screen"))
    return failures


def _follow_ups(
    *,
    retrieval_scorecard: dict[str, Any],
    screen_scorecard: dict[str, Any],
    retrieval_result_path: Path,
    screen_report_path: Path,
) -> list[dict[str, str]]:
    follow_ups: list[dict[str, str]] = []

    failed_regions = _failed_retrieval_regions(retrieval_scorecard)
    if failed_regions:
        follow_ups.append(
            {
                "type": "retrieval_quality",
                "message": "Retrieval gate failed for regions: " + ", ".join(failed_regions) + ".",
            }
        )

    failed_screens = _failed_screen_checks(screen_scorecard)
    if failed_screens:
        follow_ups.append(
            {
                "type": "screen_quality",
                "message": "Screen gate failed for screens: " + ", ".join(failed_screens) + ".",
            }
        )

    sample_inputs = any("sample" in path.name.lower() for path in (retrieval_result_path, screen_report_path))
    if sample_inputs:
        follow_ups.append(
            {
                "type": "baseline_fidelity",
                "message": "Current baseline uses sample benchmark artifacts; rerun with real project captures before release candidate sign-off.",
            }
        )

    follow_ups.append(
        {
            "type": "rerun_policy",
            "message": "Rerun this benchmark gate after any retrieval, repair, or gateway contract change that can affect the two benchmark screens.",
        }
    )
    return follow_ups


def _gate_entries(retrieval_scorecard: dict[str, Any], screen_scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    retrieval_failed = int(retrieval_scorecard.get("summary", {}).get("failedScreens", 0))
    screen_failed = int(screen_scorecard.get("summary", {}).get("failedScreens", 0))
    retrieval_passed = not bool(retrieval_scorecard.get("hasErrors"))
    screen_passed = not bool(screen_scorecard.get("hasErrors"))
    return [
        {
            "name": "retrieval_benchmark",
            "status": "pass" if retrieval_passed else "fail",
            "failedScreens": retrieval_failed,
        },
        {
            "name": "screen_benchmark",
            "status": "pass" if screen_passed else "fail",
            "failedScreens": screen_failed,
        },
        {
            "name": "must_have_release_gate",
            "status": "pass" if retrieval_passed and screen_passed else "fail",
            "failedChecks": int(not retrieval_passed) + int(not screen_passed),
        },
    ]


def _artifact_summary(
    *,
    retrieval_scorecard: dict[str, Any],
    screen_scorecard: dict[str, Any],
) -> dict[str, Any]:
    return {
        "retrieval": {
            "screenCount": retrieval_scorecard["summary"]["screenCount"],
            "passedScreens": retrieval_scorecard["summary"]["passedScreens"],
            "failedScreens": retrieval_scorecard["summary"]["failedScreens"],
            "failedRegions": _failed_retrieval_regions(retrieval_scorecard),
        },
        "screen": {
            "screenCount": screen_scorecard["summary"]["screenCount"],
            "passedScreens": screen_scorecard["summary"]["passedScreens"],
            "failedScreens": screen_scorecard["summary"]["failedScreens"],
            "failedScreensList": _failed_screen_checks(screen_scorecard),
        },
    }


def _markdown_lines(
    *,
    gate_report: dict[str, Any],
    retrieval_scorecard: dict[str, Any],
    screen_scorecard: dict[str, Any],
) -> list[str]:
    lines = [
        "# v0.3.0 Benchmark Gate Report",
        "",
        f"- Status: `{str(gate_report['gateStatus']).upper()}`",
        f"- Generated At: `{gate_report['generatedAtUtc']}`",
        f"- Suite: `{gate_report['suiteManifest']}`",
        f"- Retrieval Input: `{gate_report['inputs']['retrievalResult']}`",
        f"- Screen Report Input: `{gate_report['inputs']['screenReport']}`",
        "",
        "## Gate Checks",
        "",
        "| Gate | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for gate in gate_report["gates"]:
        detail_items = [f"{key}={value}" for key, value in gate.items() if key not in {"name", "status"}]
        detail = ", ".join(detail_items) if detail_items else "-"
        lines.append(f"| `{gate['name']}` | `{str(gate['status']).upper()}` | {detail} |")

    lines.extend(
        [
            "",
            "## Retrieval Scorecard",
            "",
            f"- Passed Screens: `{retrieval_scorecard['summary']['passedScreens']}/{retrieval_scorecard['summary']['screenCount']}`",
            f"- Failed Screens: `{retrieval_scorecard['summary']['failedScreens']}`",
        ]
    )
    failed_regions = _failed_retrieval_regions(retrieval_scorecard)
    if failed_regions:
        lines.append(f"- Failed Regions: `{', '.join(failed_regions)}`")
    else:
        lines.append("- Failed Regions: `none`")

    lines.extend(
        [
            "",
            "## Screen Scorecard",
            "",
            f"- Passed Screens: `{screen_scorecard['summary']['passedScreens']}/{screen_scorecard['summary']['screenCount']}`",
            f"- Failed Screens: `{screen_scorecard['summary']['failedScreens']}`",
        ]
    )
    failed_screens = _failed_screen_checks(screen_scorecard)
    if failed_screens:
        lines.append(f"- Failed Screen List: `{', '.join(failed_screens)}`")
    else:
        lines.append("- Failed Screen List: `none`")

    lines.extend(["", "## Follow-up"])
    for item in gate_report["followUps"]:
        lines.append(f"- {item['message']}")
    return lines


def _write_markdown(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def publish_benchmark_gate_report(
    manifest_path: Path,
    retrieval_result_path: Path,
    screen_report_path: Path,
    output_dir: Path,
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    repo_root = _find_repo_root(manifest_path, retrieval_result_path, screen_report_path, output_dir)
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    retrieval_scorecard = _normalize_scorecard_paths(
        evaluate_retrieval_benchmark(manifest_path, retrieval_result_path),
        repo_root,
    )
    screen_scorecard = _normalize_scorecard_paths(
        evaluate_screen_benchmark(manifest_path, screen_report_path),
        repo_root,
    )

    retrieval_scorecard_path = output_dir / RETRIEVAL_SCORECARD_NAME
    screen_scorecard_path = output_dir / SCREEN_SCORECARD_NAME
    save_json(retrieval_scorecard_path, retrieval_scorecard)
    save_json(screen_scorecard_path, screen_scorecard)

    gates = _gate_entries(retrieval_scorecard, screen_scorecard)
    gate_status = "pass" if all(item["status"] == "pass" for item in gates) else "fail"
    now = generated_at_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    gate_report = {
        "kind": RUN_KIND,
        "schemaVersion": SCHEMA_VERSION,
        "generatedAtUtc": now,
        "benchmarkName": retrieval_scorecard["benchmarkName"],
        "projectName": retrieval_scorecard["projectName"],
        "suiteManifest": _relativize_path(manifest_path.expanduser().resolve(), repo_root),
        "inputs": {
            "retrievalResult": _relativize_path(retrieval_result_path.expanduser().resolve(), repo_root),
            "screenReport": _relativize_path(screen_report_path.expanduser().resolve(), repo_root),
        },
        "artifacts": {
            "retrievalScorecard": _relative_artifact_path(retrieval_scorecard_path, output_dir),
            "screenScorecard": _relative_artifact_path(screen_scorecard_path, output_dir),
            "summaryMarkdown": _relative_artifact_path(output_dir / GATE_REPORT_MARKDOWN_NAME, output_dir),
        },
        "gateStatus": gate_status,
        "gates": gates,
        "summary": _artifact_summary(
            retrieval_scorecard=retrieval_scorecard,
            screen_scorecard=screen_scorecard,
        ),
        "followUps": _follow_ups(
            retrieval_scorecard=retrieval_scorecard,
            screen_scorecard=screen_scorecard,
            retrieval_result_path=retrieval_result_path,
            screen_report_path=screen_report_path,
        ),
    }

    gate_report_path = output_dir / GATE_REPORT_NAME
    save_json(gate_report_path, gate_report)
    _write_markdown(
        output_dir / GATE_REPORT_MARKDOWN_NAME,
        _markdown_lines(
            gate_report=gate_report,
            retrieval_scorecard=retrieval_scorecard,
            screen_scorecard=screen_scorecard,
        ),
    )
    return gate_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish combined retrieval/screen benchmark artifacts and a v0.3.0 gate report."
    )
    parser.add_argument("suite_manifest", type=Path, help="Path to the benchmark suite manifest JSON")
    parser.add_argument("retrieval_result", type=Path, help="Path to the retrieval benchmark result JSON")
    parser.add_argument("screen_report", type=Path, help="Path to the benchmark screen report JSON")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory to write benchmark artifacts into")
    parser.add_argument("--generated-at", help="Optional fixed UTC timestamp for deterministic reports")
    args = parser.parse_args(argv)

    gate_report = publish_benchmark_gate_report(
        args.suite_manifest,
        args.retrieval_result,
        args.screen_report,
        args.output_dir,
        generated_at_utc=args.generated_at,
    )
    print(
        json.dumps(
            {
                "output": gate_report["artifacts"]["summaryMarkdown"],
                "gateStatus": gate_report["gateStatus"],
                "benchmarkName": gate_report["benchmarkName"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if gate_report["gateStatus"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
