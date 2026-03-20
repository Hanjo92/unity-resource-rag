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
- `01-extract-report.json` (image 입력일 때)
- `02-blueprint-template.json`
- `03-resolved-blueprint.json`
- `03-binding-report.json`
- `04-mcp-handoff.json`
- `workflow-report.json`

## 인증 메모

### API key 방식

workflow runner는 extraction 단계에 필요한 provider credential을 하위 planner 스크립트로 그대로 전달한다.

- 기본 env 이름: `OPENAI_API_KEY`
- 관련 옵션: `--provider-api-key-env`
- 실제 구현된 읽기 위치: `env`

예시:

```bash
python3 pipeline/workflows/run_reference_to_resolved_blueprint.py \
  --image /absolute/path/to/reference.png \
  --catalog /absolute/path/to/resource_catalog.jsonl \
  --provider openai \
  --provider-api-key-env OPENAI_API_KEY
```

### OAuth 방식

- workflow runner 자체는 OAuth token을 직접 읽거나 refresh 하지 않는다.
- `env`, `file`, `command` 중 실제 구현된 것은 provider API key용 `env`뿐이다.
- Codex/MCP client 쪽 OAuth 설정은 [docs/mcp-client-setup.md](../../docs/mcp-client-setup.md)에서 별도로 다룬다.

## provider 메모

- `--provider auto`: `--provider-api-key-env`로 지정한 env가 있으면 `openai`, 없으면 `local_heuristic`
- `--provider local_heuristic`: 완전 로컬 fallback
- `--provider openai`: env 기반 API key로 OpenAI Responses API 사용
- `--provider openai_compatible --provider-base-url ... --provider-api-key-env ...`: 다른 OpenAI-compatible 서비스로 확장

### `--provider auto`의 결정 순서

1. `provider-api-key-env`로 지정한 env 이름 확인
2. env가 존재하면 `openai`
3. env가 없으면 `local_heuristic`
4. OAuth token, bearer token, MCP login 상태는 검사하지 않음
5. `openai_compatible`는 자동 선택하지 않음

즉, `auto`는 “API key 기반 provider를 바로 쓸 수 있느냐”만 본다.

적용 후 screenshot이 생기면 [pipeline/verification/README.md](../verification/README.md)의 repair loop를 이어서 돌릴 수 있다.

MCP handoff bundle 예제는 [sample-mcp-handoff-bundle.json](../../examples/mcp/sample-mcp-handoff-bundle.json)과 [end-to-end-usage.md](../../examples/mcp/end-to-end-usage.md)를 참고하면 된다.

## 보안 주의사항

- `workflow-report.json`, `01-extract-report.json`, `03-binding-report.json`, `04-mcp-handoff.json`에 토큰 원문을 남기지 않는다.
- 운영 문서나 CI 로그에는 env 이름만 기록하고, secret 값은 secret manager 또는 shell env에서 주입한다.
- OAuth를 쓰더라도 동일하다. access token / refresh token을 artifact에 넣지 않는다.

## Environment Variables / MCP 검색 키워드

- `OPENAI_API_KEY`
- `provider-api-key-env`
- `Environment Variables`
- `mcpServers`
