# Reference Planner MVP

`extract_reference_layout.py`는 레퍼런스 이미지 자체를 보고 `reference layout plan` JSON을 자동 생성한다.

`reference_layout_to_blueprint.py`는 그 plan을 `bind_blueprint_assets.py`가 소비할 수 있는 blueprint template로 바꾼다.

전체를 한 번에 돌리려면 [pipeline/workflows/README.md](../workflows/README.md)의 workflow runner를 쓰면 된다.

MCP handoff와 repair bundle이 Unity MCP와 어떻게 연결되는지는 [mcp-sidecar-contract.md](../../specs/mcp-sidecar-contract.md)와 [examples/mcp/end-to-end-usage.md](../../examples/mcp/end-to-end-usage.md)에 정리했다.

흐름:

1. `reference image`
2. `reference layout plan`
3. `blueprint template`
4. `resolved blueprint`
5. `apply_ui_blueprint`

자동 추출 예시:

```bash
python3 pipeline/planner/extract_reference_layout.py \
  /absolute/path/to/reference.png \
  --provider auto \
  --hint "mobile reward popup" \
  --safe-area-component-type "MyGame.UI.SafeAreaFitter" \
  --safe-area-properties '{"applyOnAwake": true}'
```

provider 메모:

- `auto`: `OPENAI_API_KEY`가 있으면 `openai`, 없으면 `local_heuristic`
- `local_heuristic`: 키 없이 동작하는 로컬 fallback
- `openai_compatible`: OpenAI-compatible Responses API를 제공하는 다른 서비스에 연결할 때 사용

키 없이 요청 구조만 확인하려면:

```bash
python3 pipeline/planner/extract_reference_layout.py \
  /absolute/path/to/reference.png \
  --dry-run
```

예시:

```bash
python3 pipeline/planner/reference_layout_to_blueprint.py \
  examples/blueprints/sample-popup-reference-layout.json
```

출력 템플릿은 다음 단계에서 바로 사용할 수 있다.

```bash
python3 pipeline/retrieval/bind_blueprint_assets.py \
  examples/blueprints/sample-popup-reference-layout.template.json \
  Library/ResourceRag/resource_catalog.jsonl
```
