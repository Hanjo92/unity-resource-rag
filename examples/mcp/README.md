# MCP Client Config Examples

상황별로 맞는 예시 파일 하나만 복사해서 MCP client 설정의 출발점으로 쓰면 된다.

- `mcp-client-config.codex-oauth.example.json`: Codex에 이미 로그인되어 있고 OpenAI provider 인증을 그대로 재사용하고 싶을 때 복사한다.
- `mcp-client-config.openai-api-key.example.json`: `OPENAI_API_KEY` 기반으로 가장 익숙한 OpenAI 설정을 바로 붙이고 싶을 때 복사한다.
- `mcp-client-config.gemini-api-key.example.json`: `GEMINI_API_KEY` 또는 `GOOGLE_API_KEY`를 이미 쓰고 있을 때 복사한다.
- `mcp-client-config.claude-code.example.json`: Claude Code credential 또는 bearer token을 재사용하고 싶을 때 복사한다.
- `mcp-client-config.local-only.example.json`: 인터넷 없이 `local_heuristic` 경로만 테스트하고 싶을 때 복사한다.

모든 파일은 `/absolute/path/to/unity-resource-rag`만 실제 경로로 바꿔 사용하면 된다.
