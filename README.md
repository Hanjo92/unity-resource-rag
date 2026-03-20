# Unity Resource RAG

[![Release](https://img.shields.io/github/v/release/Hanjo92/unity-resource-rag?label=release)](https://github.com/Hanjo92/unity-resource-rag/releases)
[![License](https://img.shields.io/github/license/Hanjo92/unity-resource-rag)](./LICENSE)
[![Unity](https://img.shields.io/badge/Unity-2021.3%2B-black?logo=unity)](./Packages/com.hanjo92.unity-resource-rag/package.json)

`unity-resource-rag`는 레퍼런스 이미지나 목업을 바탕으로, Unity 프로젝트 안의 실제 `Sprite`, `Prefab`, `TMP Font Asset`, `Material`을 우선 활용해 UI를 조립하기 위한 저장소다.

## 한눈에 보기

이 저장소는 크게 두 레이어로 구성된다.

- **Unity 내부 실행 레이어**: UPM 패키지 `com.hanjo92.unity-resource-rag`
- **Unity 외부 파이프라인 레이어**: planning / retrieval / verification을 담당하는 Python sidecar + MCP server

## 주요 구성 요소

### Unity 쪽

- Custom tool: `index_project_resources`
- Resource catalog: `ui_asset_catalog`
- Custom tool: `apply_ui_blueprint`

### Sidecar 쪽

- Workflow: `reference image -> resolved blueprint -> MCP handoff`
- Verification workflow: `screenshot compare -> repair handoff`
- MCP server wrapper: `python3 -m pipeline.mcp`

## 저장소 구조

- `Packages/com.hanjo92.unity-resource-rag/`
- `pipeline/`
- `specs/`
- `docs/`
- `examples/`

## 요구 사항

- Python 3.11+
- `unity-mcp`가 설치된 Unity 프로젝트
- 선택 사항: `OPENAI_API_KEY`

> `OPENAI_API_KEY`가 없어도 동작은 가능하다. 이 경우 이미지 레이아웃 추출은 `local_heuristic` fallback을 사용한다.

## 인증 개요: API key 방식 vs OAuth 방식

이 저장소에서 문서상 구분해야 하는 인증은 두 가지다.

1. **provider API key 인증**
   - `extract_reference_layout.py`와 `run_reference_to_resolved_blueprint.py`가 이미지 추출 provider에 접근할 때 사용한다.
   - 현재 구현은 `--provider-api-key-env`로 지정한 **환경 변수(env)** 만 읽는다.
   - 기본 env 이름은 `OPENAI_API_KEY`다.

2. **MCP client OAuth / bearer 인증**
   - Codex 같은 MCP client가 **원격 HTTP MCP server** 에 연결할 때 쓰는 인증이다.
   - 이 저장소의 기본 실행 방식은 로컬 stdio(`python3 -m pipeline.mcp`)이므로 sidecar Python 코드가 OAuth token을 직접 파싱하지는 않는다.
   - Codex 기준으로는 `bearer_token_env_var`, `oauth_resource`, `scopes`, `mcp_oauth_credentials_store` 같은 설정이 이 층에 해당한다.

핵심 차이:

- **API key 방식**: `OPENAI_API_KEY` 같은 정적 secret을 env로 주입해서 provider API를 호출한다.
- **OAuth 방식**: MCP client가 bearer token 또는 로그인 세션을 관리해 원격 MCP HTTP endpoint에 붙는다.
- **이 저장소의 실제 구현 범위**: `pipeline/` Python 코드는 provider credential을 env에서 읽는 것만 구현되어 있다. OAuth token을 `file`이나 `command`로 읽는 로직은 없다.

## 설치

### 1) Python 설정

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Unity 설정

1. Unity 프로젝트에 `unity-mcp`를 설치한다.
2. 이 저장소의 [Packages/com.hanjo92.unity-resource-rag](./Packages/com.hanjo92.unity-resource-rag)를 `Packages/` 아래에 두거나 Git URL로 설치한다.
3. Unity에서 custom tool discovery가 완료되면 `index_project_resources`, `ui_asset_catalog`, `apply_ui_blueprint`를 사용할 수 있다.

패키지 상세 문서는 [Packages/com.hanjo92.unity-resource-rag/README.md](./Packages/com.hanjo92.unity-resource-rag/README.md)에서 확인할 수 있다.

### 3) MCP 클라이언트 설정

이 저장소는 `unity-mcp`를 대체하지 않는다.

- `unity-mcp`: Unity Editor를 실제로 조작
- 이 저장소의 MCP server: planning / retrieval / repair sidecar를 담당

클라이언트 설정 예시는 다음 문서에 정리되어 있다.

- [docs/mcp-client-setup.md](./docs/mcp-client-setup.md)
- [examples/mcp/mcp-client-config.example.json](./examples/mcp/mcp-client-config.example.json)

직접 실행할 때는 아래 둘 중 하나를 사용하면 된다.

```bash
python3 -m pipeline.mcp
```

```bash
python3 /absolute/path/to/unity-resource-rag/pipeline/mcp/server.py
```

## 빠른 시작

### 기본 흐름

1. Unity에서 `index_project_resources`를 실행해 `resource_catalog.jsonl`을 생성한다.
2. MCP client에 이 저장소의 sidecar server를 등록한다.
3. 레퍼런스 이미지에서 시작할 때는 `unity_rag.run_reference_to_resolved_blueprint`를 호출한다.
4. 생성된 handoff bundle을 Unity 쪽 `apply_ui_blueprint`와 `manage_camera`에 전달한다.
5. 결과가 기대와 다르면 `unity_rag.run_verification_repair_loop`를 호출해 repair bundle을 만든다.

### CLI 예시

```bash
python3 pipeline/workflows/run_reference_to_resolved_blueprint.py \
  --image /absolute/path/to/reference.png \
  --catalog /absolute/path/to/resource_catalog.jsonl \
  --provider auto
```

### `--provider auto` 결정 순서

`--provider auto`는 현재 다음 순서로 provider/auth를 결정한다.

1. `--provider-api-key-env`에 지정한 환경 변수 이름을 확인한다.
2. 그 env 값이 존재하면 `openai` provider로 resolve한다.
3. env 값이 없으면 `local_heuristic`로 fallback 한다.
4. `auto`는 `openai_compatible`를 자동 선택하지 않는다.
5. OAuth token, bearer token, MCP login 상태는 `auto` 판단에 사용하지 않는다.

실무적으로는 아래처럼 생각하면 된다.

- `OPENAI_API_KEY` 있음 → `openai`
- `OPENAI_API_KEY` 없음 → `local_heuristic`
- 다른 OpenAI-compatible 서비스 사용 → `--provider openai_compatible --provider-base-url ... --provider-api-key-env ...`
- OAuth 기반 MCP 연결 필요 → MCP client 설정에서 별도로 관리

## Environment Variables

문서 검색과 설정 파일 검색을 쉽게 하기 위해 주요 문자열을 그대로 적어 둔다.

- `OPENAI_API_KEY`
- `provider-api-key-env`
- `Environment Variables`
- `mcpServers`

현재 이 저장소 코드가 직접 읽는 인증 관련 값:

- `OPENAI_API_KEY`
- `--provider-api-key-env`로 지정한 다른 env 이름

현재 이 저장소 코드가 직접 구현하지 않는 방식:

- OAuth access token을 `file`에서 읽기
- OAuth access token을 `command` 결과에서 읽기

즉, `pipeline/` Python 코드 기준 실제 구현은 **env만 사용**한다. OAuth credential 저장 위치는 MCP client 구현에 따라 달라질 수 있다.

## 보안 주의사항

- access token, refresh token, API key는 Git에 커밋하지 않는다.
- `workflow-report.json`, extraction report, binding report, handoff JSON 같은 report/log/json artifact에 토큰 원문을 남기지 않는다.
- 문서와 예제에는 secret 값 대신 env 이름이나 placeholder만 기록한다.
- Codex OAuth를 사용할 때도 credential store가 `file`일 수 있으므로, 저장 위치와 접근 권한을 별도로 검토하는 것이 좋다.

## 문서 바로가기

### 핵심 문서

- [docs/asset-aware-ui-rag-architecture.md](./docs/asset-aware-ui-rag-architecture.md)
- [specs/mcp-sidecar-contract.md](./specs/mcp-sidecar-contract.md)
- [specs/ui-assembly-contract.md](./specs/ui-assembly-contract.md)
- [specs/ui-binding-contract.md](./specs/ui-binding-contract.md)

### 참고 자료

- [examples/mcp/end-to-end-usage.md](./examples/mcp/end-to-end-usage.md)
- [CHANGELOG.md](./CHANGELOG.md)

## 링크

- Repository: [Hanjo92/unity-resource-rag](https://github.com/Hanjo92/unity-resource-rag)
- Issues: [github.com/Hanjo92/unity-resource-rag/issues](https://github.com/Hanjo92/unity-resource-rag/issues)
- Releases: [github.com/Hanjo92/unity-resource-rag/releases](https://github.com/Hanjo92/unity-resource-rag/releases)
- License: [LICENSE](./LICENSE)

## 참고 사항

- 생성물과 캐시는 `.gitignore`로 제외한다.
- 실제 사용 전에는 Unity 프로젝트 안에서 C# 컴파일 상태를 한 번 더 확인하는 것이 좋다.
- 라이선스는 MIT이며, 자세한 내용은 루트 [LICENSE](./LICENSE)에 포함되어 있다.
