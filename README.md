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
- 선택 사항: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`
- 또는 Codex/로컬 OAuth 로그인 상태(`$CODEX_HOME/auth.json` 또는 `~/.codex/auth.json`)

> API 키가 없어도 동작은 가능하다. Codex OAuth 로그인 파일이 있으면 OpenAI provider를 그대로 쓸 수 있고, Google 쪽은 `gemini`(API key)와 `antigravity`(OAuth / gcloud access token), Anthropic 쪽은 `claude`(API key)와 `claude_code`(Claude Code bearer token / credential file)로 나눠서 사용할 수 있다. 전부 없으면 이미지 레이아웃 추출은 `local_heuristic` fallback을 사용한다.

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

긴 설명 대신, 아래 요약표에서 본인 상황과 가장 가까운 항목을 고른 뒤 [docs/mcp-client-setup.md](./docs/mcp-client-setup.md)의 선택 가이드로 바로 들어가는 것을 권장한다.

| 상황 | 바로 선택할 설정 | 이동 |
| --- | --- | --- |
| Codex에 이미 로그인되어 있다 | `codex_oauth` | [빠른 선택 가이드](./docs/mcp-client-setup.md#빠른-선택-가이드) |
| OpenAI API 키를 이미 쓰고 있다 | `openai_api_key` | [추천 설정 5가지](./docs/mcp-client-setup.md#추천-설정-5가지) |
| Gemini API 키를 이미 쓰고 있다 | `gemini_api_key` | [추천 설정 5가지](./docs/mcp-client-setup.md#추천-설정-5가지) |
| Claude Code credential을 재사용하고 싶다 | `claude_code` | [추천 설정 5가지](./docs/mcp-client-setup.md#추천-설정-5가지) |
| 인터넷 없이 동작만 테스트하고 싶다 | `offline_local` | [추천 설정 5가지](./docs/mcp-client-setup.md#추천-설정-5가지) |

사용 시나리오별 JSON 예시는 아래 문서에서 바로 복사할 수 있다.

- [docs/mcp-client-setup.md](./docs/mcp-client-setup.md)
- [examples/mcp/README.md](./examples/mcp/README.md)

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

Gemini preset을 바로 쓰려면:

```bash
python3 pipeline/workflows/run_reference_to_resolved_blueprint.py \
  --image /absolute/path/to/reference.png \
  --catalog /absolute/path/to/resource_catalog.jsonl \
  --provider gemini
```

Antigravity preset을 바로 쓰려면:

```bash
python3 pipeline/workflows/run_reference_to_resolved_blueprint.py \
  --image /absolute/path/to/reference.png \
  --catalog /absolute/path/to/resource_catalog.jsonl \
  --provider antigravity
```

Claude preset을 바로 쓰려면:

```bash
python3 pipeline/workflows/run_reference_to_resolved_blueprint.py \
  --image /absolute/path/to/reference.png \
  --catalog /absolute/path/to/resource_catalog.jsonl \
  --provider claude
```

Claude Code preset을 바로 쓰려면:

```bash
python3 pipeline/workflows/run_reference_to_resolved_blueprint.py \
  --image /absolute/path/to/reference.png \
  --catalog /absolute/path/to/resource_catalog.jsonl \
  --provider claude_code
```

Codex OAuth 로그인(`~/.codex/auth.json`)을 그대로 재사용하고 싶다면 별도 `OPENAI_API_KEY` 없이도 같은 명령으로 동작한다. 다른 위치의 auth 파일을 쓰려면:

```bash
python3 pipeline/workflows/run_reference_to_resolved_blueprint.py \
  --image /absolute/path/to/reference.png \
  --catalog /absolute/path/to/resource_catalog.jsonl \
  --provider openai \
  --auth-mode oauth_token \
  --codex-auth-file /custom/path/to/auth.json
```

### MCP preset 예시

MCP tool에서는 처음 설정할 때 저수준 인증 필드를 직접 채우기보다 `connection_preset`을 먼저 고르는 것을 권장한다.

- `recommended_auto`: 권장값. 가능한 인증을 자동 선택
- `codex_oauth`: Codex OAuth로 OpenAI 연결
- `openai_api_key`: `OPENAI_API_KEY`
- `gemini_api_key`: `GEMINI_API_KEY` 또는 `GOOGLE_API_KEY`
- `google_oauth`: `GOOGLE_OAUTH_ACCESS_TOKEN` 또는 `gcloud` access token
- `claude_api_key`: `ANTHROPIC_API_KEY`
- `claude_code`: `ANTHROPIC_AUTH_TOKEN` 또는 `~/.claude/.credentials.json`
- `custom_openai_compatible`: 별도 OpenAI-compatible endpoint
- `offline_local`: `local_heuristic` 전용

예를 들어 MCP client에서 workflow tool을 호출할 때는 다음처럼 시작하면 된다.

```json
{
  "tool": "unity_rag.run_reference_to_resolved_blueprint",
  "arguments": {
    "image": "/absolute/path/to/reference.png",
    "catalog": "/absolute/path/to/resource_catalog.jsonl",
    "connection_preset": "recommended_auto"
  }
}
```

커스텀 endpoint가 필요할 때만 `provider_base_url` 같은 고급 설정을 함께 넣는다. 대부분의 사용자는 CLI든 MCP든 기본값 또는 `auto`/`recommended_auto`만으로 시작하면 된다.

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
