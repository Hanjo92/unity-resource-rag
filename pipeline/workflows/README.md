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
  --gateway-url http://127.0.0.1:8090 \
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

- `--provider auto`: `--gateway-url` 또는 `UNITY_RESOURCE_RAG_GATEWAY_URL`이 있으면 `gateway`, 없으면 OpenAI 키/Codex OAuth가 있으면 `openai`, 없으면 Google API key -> `gemini`, 없으면 Google OAuth / gcloud access token -> `antigravity`, 없으면 `ANTHROPIC_API_KEY` -> `claude`, 없으면 `ANTHROPIC_AUTH_TOKEN` 또는 `~/.claude/.credentials.json` -> `claude_code`, 셋 다 없으면 `local_heuristic`
- OAuth 입력(`--oauth-token-env`, `--oauth-token-file`, `--oauth-token-command`, `--codex-auth-file`)을 주면 `--provider-api-key-env`보다 OAuth 설정이 우선된다
- 명시적인 OAuth 입력이 없어도 `$CODEX_HOME/auth.json` 또는 `~/.codex/auth.json`에 Codex 로그인 토큰이 있으면 `--provider auto`가 OpenAI provider를 계속 사용할 수 있다
- `--provider gateway --gateway-url ...`: OAuth-protected gateway 또는 team gateway 사용
- `--provider local_heuristic`: 완전 로컬 fallback
- `--provider gemini`: Google OpenAI-compatible endpoint preset (`GEMINI_API_KEY` 또는 `GOOGLE_API_KEY`)
- `--provider antigravity`: Google OpenAI-compatible endpoint + OAuth preset (`GOOGLE_OAUTH_ACCESS_TOKEN` 또는 `gcloud auth application-default print-access-token`)
- `--provider claude`: Anthropic OpenAI-compatible endpoint preset (`ANTHROPIC_API_KEY`)
- `--provider claude_code`: Anthropic OpenAI-compatible endpoint + Claude Code bearer preset (`ANTHROPIC_AUTH_TOKEN` 또는 `~/.claude/.credentials.json`)
- `--provider openai_compatible --provider-base-url ... --provider-api-key-env ...`: 다른 OpenAI-compatible 서비스로 확장. Codex OAuth 자동 재사용 대신 서비스 전용 API key 또는 명시적 OAuth 입력을 사용
- workflow runner도 extractor와 동일하게 `--auth-mode`, `--oauth-token-env`, `--oauth-token-file`, `--oauth-token-command`, `--codex-auth-file`를 그대로 전달한다
- `--gateway-auth-token-env ...`: gateway bearer token env var 이름
- `--gateway-timeout-ms ...`: gateway request timeout

Benchmark helpers:

- `python3 -m pipeline.evaluation.run_retrieval_benchmark <suite-manifest> <retrieval-result>`
- `python3 -m pipeline.evaluation.run_screen_benchmark <suite-manifest> <benchmark-report>`

두 runner는 모두 suite manifest와 입력 payload의 `schemaVersion`, `benchmarkName`, `projectName`이 일치해야 통과한다.
retrieval runner는 `top1HitRate`, `top3HitRate`, `selectedCandidateScore`와 `bindingDecision`을 기준으로 채점하고, screen runner는 fixture threshold와 `repairIterations`/mismatch issue types를 기준으로 채점한다.
`low_confidence_review`, threshold breach, missing screen result가 자주 나는 실패 원인이다.

MCP tool preset 메모:

- 처음 설정할 때는 CLI 저수준 플래그를 MCP에서 그대로 노출하기보다 `connection_preset`을 먼저 고르는 것을 권장한다
- 권장 시작값은 `connection_preset=recommended_auto`
- Codex OAuth는 `codex_oauth`, OpenAI 키는 `openai_api_key`, Gemini 키는 `gemini_api_key`, Google OAuth는 `google_oauth`, Claude API key는 `claude_api_key`, Claude Code는 `claude_code`, 완전 로컬은 `offline_local`
- `custom_openai_compatible`만 `provider_base_url` 같은 고급 설정을 추가로 채우면 된다
- `connection_preset`과 저수준 필드를 함께 넘기면 preset이 우선하지만, 고급 커스텀 입력은 계속 지원한다

적용 후 screenshot이 생기면 [pipeline/verification/README.md](../verification/README.md)의 repair loop를 이어서 돌릴 수 있다.

MCP handoff bundle 예제는 [sample-mcp-handoff-bundle.json](../../examples/mcp/sample-mcp-handoff-bundle.json)과 [end-to-end-usage.md](../../examples/mcp/end-to-end-usage.md)를 참고하면 된다.
