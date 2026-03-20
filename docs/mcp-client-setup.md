# MCP Client Setup

이 저장소는 `unity-mcp` 옆에 붙는 sidecar MCP server를 제공한다.

- `unity-mcp`: Unity Editor 실제 조작
- `unity-resource-rag`: reference extraction, asset binding workflow, repair planning

둘은 함께 쓰는 게 기준이다.

## 인증 모델 정리

### 1) API key 방식

- 용도: `openai` 또는 `openai_compatible` provider로 레퍼런스 레이아웃을 추출할 때 사용
- 실제 구현: Python 파이프라인이 `--provider-api-key-env`로 지정한 **환경 변수(env)** 값을 읽는다.
- 기본 env 이름: `OPENAI_API_KEY`

### 2) OAuth / bearer 방식

- 용도: Codex 같은 MCP client가 **원격 HTTP MCP server** 에 붙을 때 사용
- 이 저장소의 기본 실행 방식은 로컬 stdio(`python3 -m pipeline.mcp`)이므로, sidecar Python 코드가 OAuth token 자체를 읽지는 않는다.
- Codex 기준 실제 관련 필드명은 `bearer_token_env_var`, `oauth_resource`, `scopes`, `env_http_headers`, 그리고 top-level `mcp_oauth_credentials_store`다.

### 실제 구현된 토큰 읽기 방식

요청하신 `env`, `file`, `command`를 기준으로 구분하면 다음과 같다.

#### 이 저장소 `pipeline/` 코드

- 구현됨: `env`
  - `OPENAI_API_KEY`
  - 또는 `--provider-api-key-env SOME_OTHER_ENV_NAME`
- 구현 안 됨: `file`
- 구현 안 됨: `command`

#### Codex MCP client

- 구현됨: `env`
  - `mcp_servers.<id>.bearer_token_env_var`
  - `mcp_servers.<id>.env_http_headers`
- 구현됨: credential store
  - `mcp_oauth_credentials_store = auto | file | keyring`
- 구현 안 됨: `command`

즉, 이 저장소 자체는 provider API key를 env에서만 읽고, OAuth credential 저장/로그인은 MCP client가 담당한다.

## Local stdio `mcpServers` Example

아래 예시는 `mcpServers` 형식을 쓰는 MCP client에서 로컬 stdio server를 붙일 때 그대로 응용할 수 있다.

```json
{
  "mcpServers": {
    "unity-resource-rag": {
      "command": "python3",
      "args": [
        "-m",
        "pipeline.mcp"
      ],
      "cwd": "/absolute/path/to/unity-resource-rag",
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}"
      }
    }
  }
}
```

설명:

- 이 예시는 **로컬 stdio 실행용**이다.
- 여기서 실제로 sidecar가 읽는 secret은 `OPENAI_API_KEY` 같은 provider API key env뿐이다.
- OAuth env placeholder를 이 local stdio 예시에 넣어도 sidecar가 직접 읽지는 않으므로, 기본 예제에서는 제외했다.

샘플 파일은 [examples/mcp/mcp-client-config.example.json](../examples/mcp/mcp-client-config.example.json) 에 있다.

## Codex HTTP / OAuth Example

Codex 공식 MCP 문서와 Config Reference 기준으로, 원격 HTTP MCP server에 OAuth/bearer를 붙일 때는 아래 필드들을 사용한다.

- `url`
- `bearer_token_env_var`
- `oauth_resource`
- `scopes`
- `mcp_oauth_credentials_store`

예시:

```toml
mcp_oauth_credentials_store = "file"

[mcp_servers.unity-resource-rag]
url = "https://mcp.example.com/unity-resource-rag/mcp"
bearer_token_env_var = "UNITY_RESOURCE_RAG_BEARER_TOKEN"
oauth_resource = "https://mcp.example.com"
scopes = ["openid", "profile", "offline_access"]
```

이 예시는 **원격 HTTP MCP endpoint** 를 전제로 한다.

- `bearer_token_env_var`: bearer token을 읽어 올 env 이름
- `oauth_resource`: OAuth login 시 전달할 resource parameter
- `scopes`: 요청할 OAuth scope 목록
- `mcp_oauth_credentials_store`: Codex가 OAuth credential을 어디에 저장할지 결정

현재 Codex 문서 기준 credential store 값은 `auto`, `file`, `keyring`이고, `command` 기반 token source는 보이지 않는다.

## JSON starter for OAuth-capable clients

일부 MCP client가 JSON에서 Codex와 유사한 필드명을 받아들인다면 아래 형태로 시작할 수 있다.

```json
{
  "mcpServers": {
    "unity-resource-rag-http": {
      "url": "https://mcp.example.com/unity-resource-rag/mcp",
      "bearer_token_env_var": "UNITY_RESOURCE_RAG_BEARER_TOKEN",
      "oauth_resource": "https://mcp.example.com",
      "scopes": [
        "openid",
        "profile",
        "offline_access"
      ]
    }
  }
}
```

단, 이 JSON HTTP/OAuth 예시는 **client별 지원 여부가 다를 수 있으므로** 사용 중인 MCP client의 스키마를 함께 확인해야 한다.

## Absolute Script Path Variant

client가 `cwd`를 지원하지 않거나 모듈 실행보다 절대 경로가 편하면 아래처럼 써도 된다.

```json
{
  "mcpServers": {
    "unity-resource-rag": {
      "command": "python3",
      "args": [
        "/absolute/path/to/unity-resource-rag/pipeline/mcp/server.py"
      ],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}"
      }
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

## `--provider auto` 동작 순서

`--provider auto`일 때 provider/auth 결정은 다음 순서다.

1. `--provider-api-key-env` 값으로 지정된 env 이름을 확인
2. 해당 env가 존재하면 `openai`
3. 존재하지 않으면 `local_heuristic`
4. `openai_compatible`는 자동 선택하지 않음
5. OAuth token, bearer token, Codex login 상태는 검사하지 않음

즉, `auto`는 provider API key 존재 여부만 보고 판단한다.

## Environment Variables

문서 검색용 키워드를 그대로 유지한다.

- `OPENAI_API_KEY`
- `provider-api-key-env`
- `Environment Variables`
- `mcpServers`

추천 env 이름 예시:

- `OPENAI_API_KEY`
- `UNITY_RESOURCE_RAG_BEARER_TOKEN`

설명:

- `OPENAI_API_KEY`: 이 저장소 Python 코드가 실제로 읽는 provider credential
- `UNITY_RESOURCE_RAG_BEARER_TOKEN`: Codex 같은 MCP client가 `bearer_token_env_var`로 읽을 수 있는 bearer token 예시 이름

## 보안 주의사항

- 토큰 원문은 report/log/json artifact에 넣지 않는다.
- 특히 extraction report, `workflow-report.json`, MCP handoff JSON, shell debug 출력에 access token을 남기지 않는다.
- 설정 파일에는 가능하면 토큰 값 대신 env 이름 또는 placeholder만 넣는다.
- `mcp_oauth_credentials_store = "file"`를 쓸 때는 저장 위치와 파일 권한까지 검토한다.

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
