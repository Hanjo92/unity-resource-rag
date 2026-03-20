#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pipeline.verification.repair_patch_models import (
    RepairPatchCandidate,
    RepairPatchCandidateSet,
    RepairPatchNodeRef,
    RepairPatchStep,
)


SUPPORTED_ISSUE_TYPES = {
    "composition_shift",
    "scale_mismatch",
    "style_asset_mismatch",
}

REPAIR_TYPE_BY_ISSUE = {
    "composition_shift": "realign_composition",
    "scale_mismatch": "restore_scale_ownership",
    "style_asset_mismatch": "replace_style_asset",
}

BOUNDED_SCOPE_BY_ISSUE = {
    "composition_shift": [
        "parent containers",
        "anchors",
        "pivot",
        "top-level composition",
    ],
    "scale_mismatch": [
        "CanvasScaler",
        "sizeDelta ownership",
        "layout constraints",
    ],
    "style_asset_mismatch": [
        "sprite or prefab selection",
        "decorative asset replacement",
        "baked frame preservation",
    ],
}

STEP_LIBRARY = {
    "composition_shift": [
        ("inspect_parent_chain", "top suspect node", "Inspect the parent chain before changing child offsets.", {"focus": ["parent", "container ownership"]}),
        ("adjust_anchor_and_pivot", "top suspect node", "Recenter anchors and pivot only after the parent chain is understood.", {"focus": ["anchor", "pivot"]}),
        ("verify_composition_alignment", "root", "Re-verify the root alignment after the smallest structural fix.", {"focus": ["alignment", "hierarchy"]}),
    ],
    "scale_mismatch": [
        ("inspect_canvas_scaler", "root", "Check CanvasScaler and top-level sizing before local overrides.", {"focus": ["CanvasScaler", "resolution"]}),
        ("review_size_ownership", "top suspect node", "Prefer parent-driven size ownership over ad hoc local size changes.", {"focus": ["sizeDelta", "ownership"]}),
        ("verify_layout_constraints", "root", "Confirm that layout groups and stretch rules still match the intended scale.", {"focus": ["layout group", "stretch"]}),
    ],
    "style_asset_mismatch": [
        ("compare_asset_candidates", "top suspect node", "Review the current asset against nearby project candidates before redesigning.", {"focus": ["asset selection", "similarity"]}),
        ("prefer_project_asset", "top suspect node", "Prefer an existing project sprite or prefab over a placeholder or tint workaround.", {"focus": ["sprite", "prefab"]}),
        ("collapse_overmodeled_regions", "root", "Merge decorative subregions back into a single baked image when they read as one asset.", {"focus": ["decorative region", "baked image"]}),
    ],
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _severity_weight(severity: str) -> float:
    return {"high": 0.82, "medium": 0.69, "low": 0.57}.get(severity, 0.55)


def _build_target_nodes(issue: dict[str, Any]) -> list[RepairPatchNodeRef]:
    raw_nodes = issue.get("suspectNodes") or []
    nodes: list[RepairPatchNodeRef] = []
    for raw in raw_nodes[:3]:
        if not isinstance(raw, dict):
            continue
        nodes.append(RepairPatchNodeRef.model_validate(raw))
    return nodes


def _build_patch_steps(issue_type: str, target_nodes: list[RepairPatchNodeRef]) -> list[RepairPatchStep]:
    step_specs = STEP_LIBRARY.get(issue_type, [])
    top_target = target_nodes[0].hierarchyPath if target_nodes else None
    steps: list[RepairPatchStep] = []
    for action, default_target, rationale, parameters in step_specs:
        steps.append(
            RepairPatchStep(
                action=action,
                target=top_target or default_target,
                rationale=rationale,
                parameters=parameters,
            )
        )
    return steps


def _build_candidate(issue: dict[str, Any], index: int) -> RepairPatchCandidate | None:
    issue_type = str(issue.get("type") or "")
    if issue_type not in SUPPORTED_ISSUE_TYPES:
        return None

    severity = str(issue.get("severity") or "low")
    target_nodes = _build_target_nodes(issue)
    summary = str(issue.get("details") or issue.get("title") or "Repair candidate")

    return RepairPatchCandidate(
        id=f"patch_{index:02d}_{issue_type}",
        issueType=issue_type,
        severity=severity,
        repairType=REPAIR_TYPE_BY_ISSUE[issue_type],
        title=str(issue.get("title") or issue_type.replace("_", " ").title()),
        summary=summary,
        confidence=_severity_weight(severity),
        targetNodes=target_nodes,
        patchSteps=_build_patch_steps(issue_type, target_nodes),
        boundedScope=BOUNDED_SCOPE_BY_ISSUE[issue_type],
        sourceIssue={
            "type": issue_type,
            "severity": severity,
            "title": issue.get("title"),
            "details": issue.get("details"),
            "likelyFixes": issue.get("likelyFixes") or [],
        },
    )


def build_repair_patch_candidates(verification_report: dict[str, Any], source_path: str | None = None) -> RepairPatchCandidateSet:
    issues = verification_report.get("issues") or []
    candidates: list[RepairPatchCandidate] = []
    ignored_issues: list[dict[str, Any]] = []

    for index, issue in enumerate(issues, start=1):
        if not isinstance(issue, dict):
            ignored_issues.append({"reason": "non_object_issue", "issue": issue})
            continue
        candidate = _build_candidate(issue, len(candidates) + 1)
        if candidate is None:
            ignored_issues.append(
                {
                    "reason": "unsupported_issue_type",
                    "issueType": issue.get("type"),
                    "title": issue.get("title"),
                }
            )
            continue
        candidates.append(candidate)

    notes = [
        "Only composition_shift, scale_mismatch, and style_asset_mismatch are converted into repair candidates.",
        "Other verification issues are preserved in ignoredIssues for downstream inspection.",
    ]

    return RepairPatchCandidateSet(
        sourceVerificationReport=source_path,
        screenName=verification_report.get("screenName"),
        hasMeaningfulMismatch=bool(verification_report.get("hasMeaningfulMismatch")),
        candidateCount=len(candidates),
        candidates=candidates,
        ignoredIssues=ignored_issues,
        notes=notes,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert a verification report into structured repair patch candidates."
    )
    parser.add_argument("verification_report", type=Path, help="Path to a verification report JSON")
    parser.add_argument("--output", type=Path, help="Path to write the repair patch candidate JSON")
    args = parser.parse_args(argv)

    verification_path = args.verification_report.expanduser().resolve()
    verification_report = load_json(verification_path)
    candidate_set = build_repair_patch_candidates(verification_report, source_path=str(verification_path))

    output_path = args.output or verification_path.with_name(f"{verification_path.stem}.repair-patch-candidates.json")
    save_json(output_path, candidate_set.model_dump(mode="json", exclude_none=True))
    print(
        json.dumps(
            {
                "output": str(output_path),
                "candidateCount": candidate_set.candidateCount,
                "screenName": candidate_set.screenName,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
