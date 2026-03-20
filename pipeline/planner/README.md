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

## 인증 메모

### API key 방식

- `openai` / `openai_compatible` provider에서 사용
- 실제 구현은 `--provider-api-key-env`로 지정한 env에서 읽는다.
- 기본 env 이름은 `OPENAI_API_KEY`

예시:

```bash
python3 pipeline/planner/extract_reference_layout.py \
  /absolute/path/to/reference.png \
  --provider openai \
  --provider-api-key-env OPENAI_API_KEY
```

### OAuth 방식

- planner 자체는 OAuth access token을 직접 읽지 않는다.
- `env`, `file`, `command` 중 planner 코드에 구현된 방식은 provider API key용 `env`뿐이다.
- Codex/MCP client 쪽 OAuth 설정은 [docs/mcp-client-setup.md](../../docs/mcp-client-setup.md)에서 별도로 다룬다.

## provider 메모

- `auto`: `--provider-api-key-env`에 지정한 env가 있으면 `openai`, 없으면 `local_heuristic`
- `local_heuristic`: 키 없이 동작하는 로컬 fallback
- `openai`: `OPENAI_API_KEY` 같은 env 기반 인증을 사용하는 기본 API provider
- `openai_compatible`: OpenAI-compatible Responses API를 제공하는 다른 서비스에 연결할 때 사용

중요:

- `auto`는 OAuth token을 보지 않는다.
- `auto`는 `openai_compatible`를 자동으로 선택하지 않는다.
- OpenAI-compatible 서비스는 `--provider openai_compatible --provider-base-url ... --provider-api-key-env ...`를 명시해야 한다.

예시:

```bash
python3 pipeline/planner/extract_reference_layout.py \
  /absolute/path/to/reference.png \
  --provider openai_compatible \
  --provider-base-url https://example.com/v1 \
  --provider-api-key-env EXAMPLE_API_KEY
```

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

## 보안 주의사항

- API key나 OAuth token 값을 report/log/json artifact에 넣지 않는다.
- `extract-report.json`에는 env 이름이나 provider 종류만 남기고, 실제 secret 값은 남기지 않는 운영을 권장한다.
- shell history에 토큰 원문이 남지 않도록 직접 CLI 인자로 토큰을 넘기지 말고 env를 사용한다.

## Environment Variables / MCP 검색 키워드

- `OPENAI_API_KEY`
- `provider-api-key-env`
- `Environment Variables`
- `mcpServers`
