#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
VERIFICATION_DIR = PIPELINE_ROOT / "verification"

ANALYZE_SCRIPT = VERIFICATION_DIR / "analyze_screenshot_mismatch.py"
REPAIR_BUNDLE_SCRIPT = VERIFICATION_DIR / "build_repair_handoff_bundle.py"


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def run_json_command(command: list[str]) -> tuple[int, dict[str, Any], str, str]:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=str(PIPELINE_ROOT.parent),
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    payload: dict[str, Any] = {}
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {"rawStdout": stdout}
    return completed.returncode, payload, stdout, stderr


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze a captured Unity screenshot against the reference image and build a repair handoff bundle."
    )
    parser.add_argument("reference_image", type=Path, help="Path to the reference image")
    parser.add_argument("captured_image", type=Path, help="Path to the captured Unity screenshot")
    parser.add_argument("--resolved-blueprint", type=Path, help="Optional resolved blueprint JSON")
    parser.add_argument("--output-dir", type=Path, help="Directory for verification artifacts")
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser().resolve() if args.output_dir else args.captured_image.expanduser().resolve().with_name(f"{args.captured_image.stem}.repair-loop")
    output_dir.mkdir(parents=True, exist_ok=True)

    verification_report_path = output_dir / "01-verification-report.json"
    repair_handoff_path = output_dir / "02-repair-handoff.json"
    workflow_report_path = output_dir / "workflow-report.json"

    analyze_command = [
        sys.executable,
        str(ANALYZE_SCRIPT),
        str(args.reference_image.expanduser().resolve()),
        str(args.captured_image.expanduser().resolve()),
        "--output",
        str(verification_report_path),
    ]
    if args.resolved_blueprint:
        analyze_command.extend(["--resolved-blueprint", str(args.resolved_blueprint.expanduser().resolve())])

    steps: list[dict[str, Any]] = []
    exit_code, payload, stdout, stderr = run_json_command(analyze_command)
    steps.append({
        "step": "analyze_screenshot_mismatch",
        "exitCode": exit_code,
        "payload": payload,
        "stdout": stdout or None,
        "stderr": stderr or None,
    })

    if exit_code == 0:
        bundle_command = [
            sys.executable,
            str(REPAIR_BUNDLE_SCRIPT),
            str(verification_report_path),
            "--output",
            str(repair_handoff_path),
        ]
        if args.resolved_blueprint:
            bundle_command.extend(["--resolved-blueprint", str(args.resolved_blueprint.expanduser().resolve())])
        exit_code2, payload2, stdout2, stderr2 = run_json_command(bundle_command)
        steps.append({
            "step": "build_repair_handoff_bundle",
            "exitCode": exit_code2,
            "payload": payload2,
            "stdout": stdout2 or None,
            "stderr": stderr2 or None,
        })
        exit_code = exit_code or exit_code2

    report = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "referenceImage": str(args.reference_image.expanduser().resolve()),
        "capturedImage": str(args.captured_image.expanduser().resolve()),
        "resolvedBlueprint": str(args.resolved_blueprint.expanduser().resolve()) if args.resolved_blueprint else None,
        "outputDir": str(output_dir),
        "hasErrors": exit_code != 0,
        "steps": steps,
        "artifacts": {
            "verificationReport": str(verification_report_path),
            "repairHandoff": str(repair_handoff_path),
        },
    }
    save_json(workflow_report_path, report)
    print(json.dumps({
        "workflowReport": str(workflow_report_path),
        "verificationReport": str(verification_report_path),
        "repairHandoff": str(repair_handoff_path),
        "hasErrors": exit_code != 0,
    }, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
