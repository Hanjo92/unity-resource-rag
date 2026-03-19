# Verification And Repair

`analyze_screenshot_mismatch.py`는 레퍼런스 이미지와 Unity 캡처 이미지를 비교해서 mismatch report를 만든다.

`build_repair_handoff_bundle.py`는 그 결과를 바탕으로 bounded repair용 handoff bundle을 만든다.

한 번에 돌리려면:

```bash
python3 pipeline/workflows/run_verification_repair_loop.py \
  /absolute/path/to/reference.png \
  /absolute/path/to/captured.png \
  --resolved-blueprint /absolute/path/to/03-resolved-blueprint.json
```

출력:

- `01-verification-report.json`
- `02-repair-handoff.json`
- `workflow-report.json`

repair bundle 예제는 [sample-repair-handoff-bundle.json](../../examples/mcp/sample-repair-handoff-bundle.json)를 보면 된다.
