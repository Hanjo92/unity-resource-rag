# MCP Client Setup

이 저장소는 `unity-mcp` 옆에 붙는 sidecar MCP server를 제공한다.

- `unity-mcp`: Unity Editor 실제 조작
- `unity-resource-rag`: reference extraction, asset binding workflow, repair planning

둘은 함께 쓰는 게 기준이다.

## Generic `mcpServers` Example

아래 예시는 `mcpServers` 형식을 쓰는 MCP client에서 그대로 응용할 수 있다.

```json
{
  "mcpServers": {
    "unity-resource-rag": {
      "command": "python3",
      "args": [
        "-m",
        "pipeline.mcp"
      ],
      "cwd": "/absolute/path/to/unity-resource-rag"
    }
  }
}
```

샘플 파일은 [examples/mcp/mcp-client-config.example.json](../examples/mcp/mcp-client-config.example.json) 에 있다.

## Absolute Script Path Variant

client가 `cwd`를 지원하지 않거나 모듈 실행보다 절대 경로가 편하면 아래처럼 써도 된다.

```json
{
  "mcpServers": {
    "unity-resource-rag": {
      "command": "python3",
      "args": [
        "/absolute/path/to/unity-resource-rag/pipeline/mcp/server.py"
      ]
    }
  }
}
```

## With `unity-mcp`

기존 `unity-mcp` server entry는 그대로 유지하고, 여기에 `unity-resource-rag` entry를 하나 더 추가하면 된다.

실행 역할은 이렇게 나뉜다.

- `unity_rag.extract_reference_layout`
- `unity_rag.run_reference_to_resolved_blueprint`
- `unity_rag.run_verification_repair_loop`
- `unity_rag.build_mcp_handoff_bundle`

그리고 생성된 handoff bundle은 Unity 쪽 `apply_ui_blueprint`와 `manage_camera`로 넘긴다.

## Environment Variables

- `OPENAI_API_KEY`: OpenAI provider
- `GEMINI_API_KEY` / `GOOGLE_API_KEY`: Google Gemini API-key preset provider
- `GOOGLE_OAUTH_ACCESS_TOKEN`: Google Antigravity-style OAuth bearer token preset
- `ANTHROPIC_API_KEY`: Claude preset provider
- `ANTHROPIC_AUTH_TOKEN`: Claude Code-style bearer token preset

Codex에 이미 OAuth 로그인되어 있고 같은 사용자 홈에서 sidecar를 실행한다면 `$CODEX_HOME/auth.json` 또는 `~/.codex/auth.json`을 자동으로 읽어 OpenAI provider 인증에 재사용한다.

`--provider auto`는 OpenAI 키 또는 Codex OAuth가 있으면 `openai`, 그게 없고 Google API key가 있으면 `gemini`, 그다음 Google OAuth token / `gcloud auth application-default print-access-token`이 가능하면 `antigravity`, 그다음 `ANTHROPIC_API_KEY`면 `claude`, 마지막으로 `ANTHROPIC_AUTH_TOKEN` 또는 `~/.claude/.credentials.json`이 있으면 `claude_code`, 전부 없으면 `local_heuristic` fallback을 선택한다.

## MCP Tool Connection Presets

MCP tool을 처음 붙일 때는 저수준 `provider`, `auth_mode`, 각종 env/file 필드보다 `connection_preset`을 먼저 고르는 것을 권장한다.

- `recommended_auto`: 권장값. 감지 가능한 인증을 자동 선택
- `codex_oauth`: Codex OAuth를 OpenAI provider에 연결
- `openai_api_key`: `OPENAI_API_KEY` 기반 OpenAI 연결
- `gemini_api_key`: `GEMINI_API_KEY` 또는 `GOOGLE_API_KEY` 기반 Gemini 연결
- `google_oauth`: `GOOGLE_OAUTH_ACCESS_TOKEN` 또는 `gcloud` access token 기반 Google OAuth 연결
- `claude_api_key`: `ANTHROPIC_API_KEY` 기반 Claude 연결
- `claude_code`: `ANTHROPIC_AUTH_TOKEN` 또는 `~/.claude/.credentials.json` 기반 Claude Code 연결
- `custom_openai_compatible`: 별도 OpenAI-compatible endpoint 연결. 이 경우 `provider_base_url` 같은 고급 설정을 함께 채운다
- `offline_local`: 네트워크 없이 `local_heuristic`만 사용

기존 `provider`, `auth_mode`, `provider_api_key_env`, `oauth_token_env`, `oauth_token_file`, `oauth_token_command`, `codex_auth_file`, `provider_base_url`도 계속 지원하지만, MCP tool 인자에서 `connection_preset`을 같이 넘기면 preset이 우선 적용된다.

## Codex OAuth 연결

Codex에서 이 MCP server를 붙일 때는 별도의 `OPENAI_API_KEY` 복사 대신 Codex 로그인 상태를 그대로 쓰는 구성이 가능하다.

기본값:

- `$CODEX_HOME/auth.json`이 있으면 우선 사용
- 없으면 `~/.codex/auth.json`을 확인

다른 위치를 써야 하면 extractor / workflow 호출 시 `codex_auth_file` 인자를 넘기면 된다.

```json
{
  "tool": "unity_rag.run_reference_to_resolved_blueprint",
  "arguments": {
    "image": "/absolute/path/to/reference.png",
    "catalog": "/absolute/path/to/resource_catalog.jsonl",
    "connection_preset": "codex_oauth",
    "codex_auth_file": "/custom/path/to/auth.json"
  }
}
```

Gemini / Google OAuth / Claude / Claude Code 연결도 preset 이름만 바꾸면 된다.

```json
{
  "tool": "unity_rag.run_reference_to_resolved_blueprint",
  "arguments": {
    "image": "/absolute/path/to/reference.png",
    "catalog": "/absolute/path/to/resource_catalog.jsonl",
    "connection_preset": "claude_code"
  }
}
```

OpenAI-compatible 커스텀 endpoint를 붙일 때만 preset과 고급 설정을 같이 쓴다.

```json
{
  "tool": "unity_rag.extract_reference_layout",
  "arguments": {
    "image": "/absolute/path/to/reference.png",
    "connection_preset": "custom_openai_compatible",
    "provider_base_url": "https://example.com/v1",
    "provider_api_key_env": "EXAMPLE_API_KEY"
  }
}
```

## Smoke Test

서버가 뜨는지 먼저 확인할 때는:

```bash
python3 -m pipeline.mcp
```

MCP client에서 연결 후 `tools/list`를 보면 아래 4개가 보여야 한다.

- `unity_rag.extract_reference_layout`
- `unity_rag.run_reference_to_resolved_blueprint`
- `unity_rag.run_verification_repair_loop`
- `unity_rag.build_mcp_handoff_bundle`

실사용 예시는 [examples/mcp/end-to-end-usage.md](../examples/mcp/end-to-end-usage.md) 를 참고하면 된다.
