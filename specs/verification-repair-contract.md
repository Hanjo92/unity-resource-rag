# Verification Repair Contract

## Goal

Unity에서 생성한 UI screenshot을 reference image와 비교해, 다음 bounded repair 단계에 바로 쓸 수 있는 진단 결과를 만든다.

## Verification Report

`analyze_screenshot_mismatch.py` output:

- global mismatch metrics
- dominant mismatch region
- suspect blueprint nodes
- prioritized issues

대표 필드:

```json
{
  "kind": "ui_verification_report",
  "metrics": {
    "normalizedMeanAbsoluteError": 0.0831,
    "diffCoverage": 0.124,
    "foregroundBboxIoU": 0.71,
    "foregroundCenterDelta": { "x": -0.032, "y": 0.018 },
    "foregroundSizeDelta": { "w": 0.041, "h": -0.055 }
  },
  "regions": {
    "referenceForeground": { "x": 0.25, "y": 0.24, "w": 0.5, "h": 0.52 },
    "capturedForeground": { "x": 0.22, "y": 0.26, "w": 0.56, "h": 0.49 },
    "dominantDiff": { "x": 0.2, "y": 0.22, "w": 0.6, "h": 0.56 }
  },
  "issues": []
}
```

## Repair Handoff

`build_repair_handoff_bundle.py` output:

- bounded repair summary
- focus nodes
- recommended repair order
- agent-facing repair prompt
- screenshot reverify request

## Repair Priority

Always bias toward:

1. parent/container ownership
2. anchors and pivot
3. canvas scaler and size rules
4. layout ownership
5. asset choice
6. local spacing or offsets

This keeps the repair proportional and avoids accidental redesign.
