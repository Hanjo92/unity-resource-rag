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

- `OPENAI_API_KEY`: OpenAI provider를 쓸 때만 필요

Codex에 이미 OAuth 로그인되어 있고 같은 사용자 홈에서 sidecar를 실행한다면 `$CODEX_HOME/auth.json` 또는 `~/.codex/auth.json`을 자동으로 읽어 OpenAI provider 인증에 재사용한다.

키와 Codex OAuth 둘 다 없으면 `--provider auto` 기준으로 `local_heuristic` fallback이 선택된다.

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
    "provider": "openai",
    "auth_mode": "oauth_token",
    "codex_auth_file": "/custom/path/to/auth.json"
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
