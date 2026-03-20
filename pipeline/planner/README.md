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
  --gateway-url http://127.0.0.1:8080 \
  --hint "mobile reward popup" \
  --safe-area-component-type "MyGame.UI.SafeAreaFitter" \
  --safe-area-properties '{"applyOnAwake": true}'
```

provider 메모:

- `auto`: `UNITY_RESOURCE_RAG_GATEWAY_URL`이 있으면 `gateway`, 없으면 `OPENAI_API_KEY` 또는 Codex OAuth auth file이 있으면 `openai`, 없으면 Google API key -> `gemini`, 없으면 Google OAuth / gcloud access token -> `antigravity`, 없으면 `ANTHROPIC_API_KEY` -> `claude`, 없으면 `ANTHROPIC_AUTH_TOKEN` 또는 `~/.claude/.credentials.json` -> `claude_code`, 셋 다 없으면 `local_heuristic`
- OAuth 입력(`--oauth-token-env`, `--oauth-token-file`, `--oauth-token-command`, `--codex-auth-file`)이 있으면 `provider_api_key_env`보다 OAuth 설정이 우선된다
- 명시적인 OAuth 입력이 없어도 `$CODEX_HOME/auth.json` 또는 `~/.codex/auth.json`에 Codex 로그인 토큰이 있으면 `auto`가 `openai`를 선택한다
- `gateway`: OAuth-protected gateway 또는 team gateway를 통해 extraction capability 호출
- `local_heuristic`: 키 없이 동작하는 로컬 fallback
- `gemini`: Google OpenAI-compatible endpoint preset (`GEMINI_API_KEY` 또는 `GOOGLE_API_KEY`, 기본 base URL 자동 설정)
- `antigravity`: Google OpenAI-compatible endpoint + OAuth preset (`GOOGLE_OAUTH_ACCESS_TOKEN` 또는 `gcloud auth application-default print-access-token`)
- `claude`: Anthropic OpenAI-compatible endpoint preset (`ANTHROPIC_API_KEY`, 기본 base URL 자동 설정)
- `claude_code`: Anthropic OpenAI-compatible endpoint + Claude Code bearer preset (`ANTHROPIC_AUTH_TOKEN` 또는 `~/.claude/.credentials.json`)
- `openai_compatible`: OpenAI-compatible Responses API를 제공하는 다른 서비스에 연결할 때 사용. 보통 `provider_base_url`과 해당 서비스 API key를 함께 지정한다
- `--gateway-auth-token-env`: gateway bearer token이 들어 있는 env var 이름
- `--gateway-timeout-ms`: gateway request timeout

MCP tool preset 메모:

- planner extractor를 MCP tool `unity_rag.extract_reference_layout`로 호출할 때는 처음 설정용으로 `connection_preset`을 먼저 고르는 것을 권장한다
- 권장 시작값은 `connection_preset=recommended_auto`
- Codex OAuth는 `codex_oauth`, OpenAI 키는 `openai_api_key`, Gemini 키는 `gemini_api_key`, Google OAuth는 `google_oauth`, Claude API key는 `claude_api_key`, Claude Code는 `claude_code`, 완전 로컬은 `offline_local`
- `custom_openai_compatible`만 `provider_base_url` 같은 고급 설정을 추가로 채우면 된다
- `connection_preset`이 있으면 MCP handler 내부에서 `provider`, `auth_mode`, 관련 env/file 기본값으로 변환되고 preset이 우선 적용된다

키 없이 요청 구조만 확인하려면:

```bash
python3 pipeline/planner/extract_reference_layout.py \
  /absolute/path/to/reference.png \
  --dry-run
```

OAuth 예시:

```bash
python3 pipeline/planner/extract_reference_layout.py \
  /absolute/path/to/reference.png \
  --provider openai \
  --oauth-token-env OPENAI_OAUTH_TOKEN
```

Gemini / Antigravity / Claude / Claude Code preset 예시:

```bash
python3 pipeline/planner/extract_reference_layout.py \
  /absolute/path/to/reference.png \
  --provider gemini
```

```bash
python3 pipeline/planner/extract_reference_layout.py \
  /absolute/path/to/reference.png \
  --provider antigravity
```

```bash
python3 pipeline/planner/extract_reference_layout.py \
  /absolute/path/to/reference.png \
  --provider claude
```

```bash
python3 pipeline/planner/extract_reference_layout.py \
  /absolute/path/to/reference.png \
  --provider claude_code
```

Codex auth 파일 예시:

```bash
python3 pipeline/planner/extract_reference_layout.py \
  /absolute/path/to/reference.png \
  --provider openai \
  --auth-mode oauth_token \
  --codex-auth-file ~/.codex/auth.json
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
