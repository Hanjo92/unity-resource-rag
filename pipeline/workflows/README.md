# Workflow Runner

`run_reference_to_resolved_blueprint.py`는 레퍼런스 이미지에서 시작해 최종 resolved blueprint까지 한 번에 만든다.

기본 흐름:

1. `extract_reference_layout.py`
2. `reference_layout_to_blueprint.py`
3. `build_vector_index.py` or existing vector index reuse
4. `bind_blueprint_assets.py`
5. `build_mcp_handoff_bundle.py`

이미지에서 시작:

```bash
python3 pipeline/workflows/run_reference_to_resolved_blueprint.py \
  --image /absolute/path/to/reference.png \
  --catalog /absolute/path/to/resource_catalog.jsonl \
  --provider auto \
  --hint "mobile reward popup" \
  --safe-area-component-type "MyGame.UI.SafeAreaFitter" \
  --safe-area-properties '{"applyOnAwake": true}'
```

기존 plan에서 시작:

```bash
python3 pipeline/workflows/run_reference_to_resolved_blueprint.py \
  --reference-layout /absolute/path/to/reference-layout.json \
  --catalog /absolute/path/to/resource_catalog.jsonl
```

산출물:

- `01-reference-layout.json` or input reference layout
- `02-blueprint-template.json`
- `03-resolved-blueprint.json`
- `03-binding-report.json`
- `04-mcp-handoff.json`
- `workflow-report.json`

provider 메모:

- `--provider auto`: 기본적으로 키가 있으면 API provider, 없으면 `local_heuristic`
- OAuth 입력(`--oauth-token-env`, `--oauth-token-file`, `--oauth-token-command`)을 주면 `--provider-api-key-env`보다 OAuth 설정이 우선된다
- `--provider local_heuristic`: 완전 로컬 fallback
- `--provider openai_compatible --provider-base-url ... --provider-api-key-env ...`: 다른 OpenAI-compatible 서비스로 확장
- workflow runner도 extractor와 동일하게 `--auth-mode`, `--oauth-token-env`, `--oauth-token-file`, `--oauth-token-command`를 그대로 전달한다

적용 후 screenshot이 생기면 [pipeline/verification/README.md](../verification/README.md)의 repair loop를 이어서 돌릴 수 있다.

MCP handoff bundle 예제는 [sample-mcp-handoff-bundle.json](../../examples/mcp/sample-mcp-handoff-bundle.json)과 [end-to-end-usage.md](../../examples/mcp/end-to-end-usage.md)를 참고하면 된다.
