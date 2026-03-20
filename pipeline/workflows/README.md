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

- `--provider auto`: 기본적으로 OpenAI 키/Codex OAuth가 있으면 `openai`, 없으면 Google API key -> `gemini`, 없으면 Google OAuth / gcloud access token -> `antigravity`, 없으면 `ANTHROPIC_API_KEY` -> `claude`, 없으면 `ANTHROPIC_AUTH_TOKEN` 또는 `~/.claude/.credentials.json` -> `claude_code`, 셋 다 없으면 `local_heuristic`
- OAuth 입력(`--oauth-token-env`, `--oauth-token-file`, `--oauth-token-command`, `--codex-auth-file`)을 주면 `--provider-api-key-env`보다 OAuth 설정이 우선된다
- 명시적인 OAuth 입력이 없어도 `$CODEX_HOME/auth.json` 또는 `~/.codex/auth.json`에 Codex 로그인 토큰이 있으면 `--provider auto`가 OpenAI provider를 계속 사용할 수 있다
- `--provider local_heuristic`: 완전 로컬 fallback
- `--provider gemini`: Google OpenAI-compatible endpoint preset (`GEMINI_API_KEY` 또는 `GOOGLE_API_KEY`)
- `--provider antigravity`: Google OpenAI-compatible endpoint + OAuth preset (`GOOGLE_OAUTH_ACCESS_TOKEN` 또는 `gcloud auth application-default print-access-token`)
- `--provider claude`: Anthropic OpenAI-compatible endpoint preset (`ANTHROPIC_API_KEY`)
- `--provider claude_code`: Anthropic OpenAI-compatible endpoint + Claude Code bearer preset (`ANTHROPIC_AUTH_TOKEN` 또는 `~/.claude/.credentials.json`)
- `--provider openai_compatible --provider-base-url ... --provider-api-key-env ...`: 다른 OpenAI-compatible 서비스로 확장
- workflow runner도 extractor와 동일하게 `--auth-mode`, `--oauth-token-env`, `--oauth-token-file`, `--oauth-token-command`, `--codex-auth-file`를 그대로 전달한다

적용 후 screenshot이 생기면 [pipeline/verification/README.md](../verification/README.md)의 repair loop를 이어서 돌릴 수 있다.

MCP handoff bundle 예제는 [sample-mcp-handoff-bundle.json](../../examples/mcp/sample-mcp-handoff-bundle.json)과 [end-to-end-usage.md](../../examples/mcp/end-to-end-usage.md)를 참고하면 된다.
