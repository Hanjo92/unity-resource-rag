# `mcp-client-config.with-unity-mcp.example.json` 설명

`mcp-client-config.with-unity-mcp.example.json`은 MCP client에 두 서버를 함께 등록하는 완성형 예시다.

- `unity-mcp`: Unity Editor 연결과 scene 조작, custom tool 실행, screenshot capture를 담당한다.
- `unity-resource-rag`: 레퍼런스 이미지 해석, resource retrieval, resolved blueprint / repair handoff 생성을 담당한다.

## Key 설명

- `mcpServers`: MCP client가 동시에 띄울 서버 목록이다.
- `command`: 각 서버를 시작할 실행 파일이다.
- `args`: `command`에 전달할 인자 배열이다.
- `cwd`: 서버 프로세스를 시작할 작업 디렉터리다.
- `env`: 해당 서버 프로세스에만 주입할 환경 변수다.

## 값 교체 포인트

- `/absolute/path/to/unity-project`: 실제 Unity 프로젝트 루트로 바꾼다.
- `/absolute/path/to/unity-resource-rag`: 이 저장소를 checkout한 경로로 바꾼다.
- `OPENAI_API_KEY`: OpenAI를 쓰지 않는다면 지우거나, Gemini / Claude용 예시 파일을 참고해 다른 환경 변수로 바꾼다.
