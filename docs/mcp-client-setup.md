# MCP Client Setup

이 문서는 긴 설명서보다 먼저 고를 수 있는 선택 가이드로 시작한다. 먼저 아래 질문 3개로 본인에게 맞는 연결 방식을 고른 뒤, 바로 아래 preset 예시를 복사하면 된다.

## 빠른 선택 가이드

### 질문 1. Codex로 로그인되어 있나요?

- 예 → `connection_preset: "codex_oauth"`를 권장한다. Codex OAuth를 그대로 재사용해 OpenAI provider로 연결한다.
- 아니오 → 질문 2로 넘어가 권장 provider 또는 preset을 고른다.

### 질문 2. OpenAI/Gemini/Claude 중 이미 쓰는 계정이 있나요?

- OpenAI 계정/API 키가 있다 → `connection_preset: "openai_api_key"` 또는 CLI의 `--provider openai`를 권장한다.
- Gemini 계정/API 키가 있다 → `connection_preset: "gemini_api_key"` 또는 CLI의 `--provider gemini`를 권장한다.
- Claude 계정/API 키 또는 Claude Code credential이 있다 → `connection_preset: "claude_api_key"` 또는 `"claude_code"`를 권장한다.
- 셋 다 아직 없다 → `connection_preset: "recommended_auto"`로 시작해 자동 감지를 먼저 시도한다.

### 질문 3. 인터넷 없이 테스트만 하고 싶나요?

- 예 → `connection_preset: "offline_local"` 또는 CLI의 `--provider local_heuristic`를 권장한다.
- 아니오 → 위에서 고른 preset/provider를 그대로 사용한다.

## 추천 설정 5가지

자주 쓰는 조합만 짧게 복사할 수 있도록 정리했다. 실제 파일 예시는 [examples/mcp/README.md](../examples/mcp/README.md)와 각 예시 JSON 파일을 참고하면 된다.

### 1) Codex OAuth 재사용

Codex에 이미 로그인되어 있고 같은 사용자 홈에서 sidecar를 실행할 때 가장 간단하다.

```json
{
  "tool": "unity_rag.run_reference_to_resolved_blueprint",
  "arguments": {
    "image": "/absolute/path/to/reference.png",
    "catalog": "/absolute/path/to/resource_catalog.jsonl",
    "connection_preset": "codex_oauth"
  }
}
```

### 2) OpenAI API key

`OPENAI_API_KEY`를 이미 관리하고 있으면 가장 익숙한 설정이다.

```json
{
  "tool": "unity_rag.run_reference_to_resolved_blueprint",
  "arguments": {
    "image": "/absolute/path/to/reference.png",
    "catalog": "/absolute/path/to/resource_catalog.jsonl",
    "connection_preset": "openai_api_key"
  }
}
```

### 3) Gemini API key

Google AI Studio 또는 Gemini API 키를 이미 쓰고 있다면 이 조합이 가장 빠르다.

```json
{
  "tool": "unity_rag.run_reference_to_resolved_blueprint",
  "arguments": {
    "image": "/absolute/path/to/reference.png",
    "catalog": "/absolute/path/to/resource_catalog.jsonl",
    "connection_preset": "gemini_api_key"
  }
}
```

### 4) Claude Code credential

Claude Code credential 또는 bearer token 재사용이 필요하면 이 preset을 쓴다.

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

### 5) 로컬 heuristic 테스트

네트워크나 API 키 없이 레이아웃 추출 흐름만 확인하고 싶을 때 사용한다.

```json
{
  "tool": "unity_rag.run_reference_to_resolved_blueprint",
  "arguments": {
    "image": "/absolute/path/to/reference.png",
    "catalog": "/absolute/path/to/resource_catalog.jsonl",
    "connection_preset": "offline_local"
  }
}
```

## Generic `mcpServers` Example

아래 예시는 `mcpServers` 형식을 쓰는 MCP client에서 그대로 응용할 수 있는 최소 예시다.

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

같은 내용의 파일은 [examples/mcp/mcp-client-config.example.json](../examples/mcp/mcp-client-config.example.json)으로도 제공된다. 사용 시나리오별 샘플 파일은 [examples/mcp/README.md](../examples/mcp/README.md)에 정리되어 있다.

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

실사용에서는 MCP client에 `unity-mcp`와 `unity-resource-rag`를 함께 등록하는 구성을 권장한다. `unity-mcp`는 Unity Editor를 실제로 조작하고, `unity-resource-rag`는 레퍼런스 분석과 handoff bundle 생성을 맡는다.

아래는 두 서버를 함께 등록한 전체 JSON 예시다.

```json
{
  "mcpServers": {
    "unity-mcp": {
      "command": "npx",
      "args": [
        "-y",
        "unity-mcp"
      ],
      "cwd": "/absolute/path/to/unity-project"
    },
    "unity-resource-rag": {
      "command": "python3",
      "args": [
        "-m",
        "pipeline.mcp"
      ],
      "cwd": "/absolute/path/to/unity-resource-rag",
      "env": {
        "OPENAI_API_KEY": "your-openai-api-key"
      }
    }
  }
}
```

JSON에는 주석을 넣을 수 없으므로, key별 설명은 [examples/mcp/mcp-client-config.with-unity-mcp.example.md](../examples/mcp/mcp-client-config.with-unity-mcp.example.md)를 함께 참고하면 된다. 같은 JSON 파일은 [examples/mcp/mcp-client-config.with-unity-mcp.example.json](../examples/mcp/mcp-client-config.with-unity-mcp.example.json)에도 들어 있다.

서버별 역할은 다음처럼 나뉜다.

- `unity-mcp` entry: Unity Editor 연결, scene 조작, `execute_custom_tool`, `manage_camera` 같은 Unity 쪽 실행을 담당한다.
- `unity-resource-rag` entry: `unity_rag.inspect_provider_setup`, `unity_rag.extract_reference_layout`, `unity_rag.run_reference_to_resolved_blueprint`, `unity_rag.run_verification_repair_loop`, `unity_rag.build_mcp_handoff_bundle` 같은 sidecar workflow를 담당한다.

권장 흐름은 `unity-resource-rag`로 blueprint / repair handoff를 만든 뒤, 생성된 handoff bundle을 `unity-mcp` 쪽 `apply_ui_blueprint`와 `manage_camera`로 넘기는 방식이다.

처음 연결할 때는 실제 workflow보다 먼저 `unity_rag.doctor`를 한 번 돌리는 것을 권장한다. provider/auth만이 아니라 Unity 프로젝트 경로, catalog, gateway, Unity MCP HTTP Local custom tool/resource 노출 상태까지 함께 점검해준다.

```json
{
  "tool": "unity_rag.doctor",
  "arguments": {
    "unity_project_path": "/absolute/path/to/unity-project",
    "connection_preset": "recommended_auto"
  }
}
```

## Unity HTTP Local Checklist

Codex나 다른 HTTP MCP client로 `unity-mcp`를 직접 붙일 때는 아래 순서로 맞추는 편이 안전하다.

1. Unity에서 `Window > MCP for Unity`를 연다.
2. HTTP Local transport를 쓴다면 `Project Scoped Tools`를 끈다.
3. `Stop Local HTTP Server` 후 `Start Local HTTP Server`로 다시 올린다.
4. custom tool은 `index_project_resources`, `query_ui_asset_catalog`, `apply_ui_blueprint`처럼 tool 목록에서 확인하고, `ui_asset_catalog`는 raw resource가 필요할 때만 resource 목록에서 확인한다.

`Project Scoped Tools`가 켜져 있으면 일부 client에서는 개별 custom tool 대신 `execute_custom_tool`만 보일 수 있다.

catalog를 읽을 때는 대부분 `query_ui_asset_catalog`를 먼저 쓰는 편이 낫다. resource를 잘 다루는 클라이언트에서만 `ui_asset_catalog`를 직접 읽으면 된다.

## Gateway Port Note

`unity-mcp`의 HTTP Local은 흔히 `127.0.0.1:8080/mcp`를 사용한다. `pipeline.gateway`는 기본값으로 `http://127.0.0.1:8090`을 쓰도록 잡혀 있으니, 두 서버를 같이 띄울 때는 이 기본값을 그대로 두는 편이 충돌이 적다.

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
- `custom_openai_compatible`: 별도 OpenAI-compatible endpoint 연결. 이 경우 `provider_base_url`과 해당 서비스의 API key env를 함께 채운다. Codex OAuth 자동 재사용은 적용되지 않는다
- `offline_local`: 네트워크 없이 `local_heuristic`만 사용

기존 `provider`, `auth_mode`, `provider_api_key_env`, `oauth_token_env`, `oauth_token_file`, `oauth_token_command`, `codex_auth_file`, `provider_base_url`도 계속 지원하지만, MCP tool 인자에서 `connection_preset`을 같이 넘기면 preset이 우선 적용된다.

## 연결 확인하기

실제 workflow를 돌리기 전에 `unity_rag.inspect_provider_setup`을 먼저 호출해 현재 설정이 어떻게 해석되는지 확인하는 것을 권장한다. 이 tool은 레퍼런스 이미지를 요구하지 않고, 아래 항목을 바로 읽을 수 있는 형태로 돌려준다.

- 현재 권장 선택
- 실제로 해석된 provider
- 토큰 소스
- 누락된 설정
- 다음 액션

가장 안전한 시작점은 자동 감지다.

```json
{
  "tool": "unity_rag.inspect_provider_setup",
  "arguments": {
    "connection_preset": "recommended_auto"
  }
}
```

Codex OAuth를 강제로 확인하고 싶으면:

```json
{
  "tool": "unity_rag.inspect_provider_setup",
  "arguments": {
    "connection_preset": "codex_oauth",
    "codex_auth_file": "/custom/path/to/auth.json"
  }
}
```

커스텀 OpenAI-compatible endpoint를 점검할 때는:

```json
{
  "tool": "unity_rag.inspect_provider_setup",
  "arguments": {
    "connection_preset": "custom_openai_compatible",
    "provider_base_url": "https://example.com/v1",
    "provider_api_key_env": "EXAMPLE_API_KEY"
  }
}
```

진단 결과에서 누락된 설정이 없다고 나오면 그 다음에 `unity_rag.extract_reference_layout` 또는 `unity_rag.run_reference_to_resolved_blueprint`를 호출한다.

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

MCP client에서 연결 후 `tools/list`를 보면 아래 5개가 보여야 한다.

- `unity_rag.inspect_provider_setup`
- `unity_rag.extract_reference_layout`
- `unity_rag.run_reference_to_resolved_blueprint`
- `unity_rag.run_verification_repair_loop`
- `unity_rag.build_mcp_handoff_bundle`

실사용 예시는 [examples/mcp/end-to-end-usage.md](../examples/mcp/end-to-end-usage.md) 를 참고하면 된다.
