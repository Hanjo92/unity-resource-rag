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
- Custom tool: `query_ui_asset_catalog`
- Resource: `ui_asset_catalog`
- Custom tool: `apply_ui_blueprint`

### Sidecar 쪽

- Workflow: `reference image -> resolved blueprint -> MCP handoff`
- Verification workflow: `screenshot compare -> repair handoff`
- MCP server wrapper: `python3 -m pipeline.mcp`
- Provider gateway server: `python3 -m pipeline.gateway`

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
- 선택 사항: `UNITY_RESOURCE_RAG_GATEWAY_URL`, `UNITY_RESOURCE_RAG_GATEWAY_TOKEN`
- 또는 Codex/로컬 OAuth 로그인 상태(`$CODEX_HOME/auth.json` 또는 `~/.codex/auth.json`)

> API 키가 없어도 동작은 가능하다. `UNITY_RESOURCE_RAG_GATEWAY_URL`이 있으면 gateway를 우선 쓸 수 있고, Codex OAuth 로그인 파일이 있으면 OpenAI provider를 그대로 쓸 수 있다. Google 쪽은 `gemini`(API key)와 `antigravity`(OAuth / gcloud access token), Anthropic 쪽은 `claude`(API key)와 `claude_code`(Claude Code bearer token / credential file)로 나눠서 사용할 수 있다. 전부 없으면 이미지 레이아웃 추출은 `local_heuristic` fallback을 사용한다.

## 설치

### 1) Python 설정

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows에서는 `python3` 대신 `py -3 -m venv .venv` 또는 `python -m venv .venv`를 써도 된다. Unity 창의 고급 설정 `Python Command`도 `py`, `py -3`, 절대 경로 Python 실행 파일처럼 명령 형태를 그대로 받을 수 있다.

### 2) Unity 설정

1. Unity 프로젝트에 `unity-mcp`를 설치한다.
2. 이 저장소의 [Packages/com.hanjo92.unity-resource-rag](./Packages/com.hanjo92.unity-resource-rag)를 `Packages/` 아래에 두거나 Git URL로 설치한다.
3. non-dev 사용자는 portable sidecar bundle을, 개발자는 이 저장소 전체 local checkout을 sidecar runtime root로 사용할 수 있다. `Window > Unity Resource RAG`의 one-click build는 패키지 내부 코드뿐 아니라 루트 `pipeline/` sidecar도 필요하다.
4. Unity에서 `Window > Unity Resource RAG`를 열고 `Quick Setup`을 한 번 실행한다. 이 버튼은 Unity MCP를 HTTP Local로 맞추고, `Project Scoped Tools`를 끄고, custom tool/resource 노출과 Codex config 동기화를 함께 시도한다.
5. Readiness Dashboard에서 `sidecar / python / AI access / Unity Editor connection / build input` 상태를 확인한다. Python이 막혀 있으면 같은 창에서 `Bootstrap Python Runtime`으로 sidecar-local `.venv`와 requirements를 준비할 수 있다.
6. Unity에서 discovery와 resource registration이 완료되면 `index_project_resources`, `query_ui_asset_catalog`, `apply_ui_blueprint`는 custom tool로, `ui_asset_catalog`는 MCP resource로 사용할 수 있다.
7. sidecar와 gateway를 같이 띄울 때는 `unity-mcp`의 기본 `127.0.0.1:8080/mcp`와 겹치지 않도록 gateway 기본 URL `http://127.0.0.1:8090`을 사용한다.

패키지 상세 문서는 [Packages/com.hanjo92.unity-resource-rag/README.md](./Packages/com.hanjo92.unity-resource-rag/README.md)에서 확인할 수 있다.

### 3) MCP 클라이언트 설정

이 저장소는 `unity-mcp`를 대체하지 않는다. MCP client에는 두 서버를 함께 등록해야 한다.

- `unity-mcp`: Unity Editor를 실제로 조작
- 이 저장소의 MCP server: planning / retrieval / repair sidecar를 담당

대부분의 사용자는 `query_ui_asset_catalog` tool만 써도 된다. `ui_asset_catalog`는 같은 내용을 raw MCP resource로 노출하는 경로라서, resource를 잘 다루는 클라이언트에서만 직접 읽으면 된다.

실사용용 전체 예시는 [examples/mcp/mcp-client-config.with-unity-mcp.example.json](./examples/mcp/mcp-client-config.with-unity-mcp.example.json)에 있고, key 설명은 [examples/mcp/mcp-client-config.with-unity-mcp.example.md](./examples/mcp/mcp-client-config.with-unity-mcp.example.md)에서 볼 수 있다.

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

### 4) Portable sidecar bundle 만들기

non-dev 배포용 sidecar artifact를 만들려면 아래 스크립트를 사용한다.

```bash
python3 scripts/build_sidecar_bundle.py --output-dir dist
```

이 명령은 `dist/unity-resource-rag-sidecar-<version>/` 아래에 portable sidecar bundle을 만들고, Unity 창의 `Sidecar Runtime Root`에서 바로 가리킬 수 있는 형태로 정리한다.

## 빠른 시작

### 기본 흐름

1. Unity에서 `Window > Unity Resource RAG`를 열고 `Quick Setup`을 누른다.
2. sign-in method는 기본적으로 `Use my Codex sign-in (Recommended)`로 두고, 필요할 때만 API key environment mode나 offline mode로 바꾼다.
3. 같은 창의 Readiness Dashboard에서 `Refresh Readiness`를 눌러 현재 상태를 확인한다.
4. Python runtime이 막혀 있으면 `Bootstrap Python Runtime`을 먼저 실행한다.
5. reference 이미지를 넣거나, 비워둔 채 `Draft Template`을 `Popup / HUD / List` 중 하나로 고른 뒤 goal/title/body를 채우고 `Start UI Build`를 누른다.
6. 이 버튼은 내부적으로 readiness를 다시 확인한 뒤 `unity_rag.start_ui_build`를 호출하고, reference가 있으면 `run_first_pass_ui_build`, 없으면 `run_catalog_draft_ui_build`를 자동 선택한다.
7. build가 끝나면 같은 창에서 `Capture Result`로 현재 Unity 결과를 캡처한다.
8. reference build였다면 `Run Repair Handoff`로 mismatch report와 repair bundle을 만든다.
9. `Last Run Artifacts`에서 blueprint, search report, handoff, screenshot, repair output을 `Open / Reveal / Copy`로 바로 다시 연다.
10. 검토 케이스를 남기고 싶으면 `Export Case Report`로 md/json 리포트를 `Library/ResourceRag/Cases/` 아래에 저장한다.

> Unity window 기반 one-click build는 sidecar runtime root를 알아야 한다. Git URL로 패키지만 설치된 상태라면 `Sidecar Runtime Root`에 portable sidecar bundle 경로나 전체 저장소 checkout 경로를 따로 지정해야 한다.

> non-dev 배포의 공식 방향은 embedded Python보다 `portable sidecar bundle + sidecar-local .venv bootstrap`이다. 결정 배경은 [packaged-sidecar-distribution-strategy.md](./docs/decisions/packaged-sidecar-distribution-strategy.md)에서 볼 수 있다.

> `Capture Result`와 `Run Repair Handoff`는 Unity 창 안에서 계속 이어갈 수 있다. `Run Repair Handoff`는 reference 이미지가 있을 때만 활성화된다.

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
- `custom_openai_compatible`: 별도 OpenAI-compatible endpoint (`provider_base_url` + 서비스 전용 API key)
- `offline_local`: `local_heuristic` 전용

예를 들어 MCP client에서 workflow tool을 호출할 때는 다음처럼 시작하면 된다.

```json
{
  "tool": "unity_rag.start_ui_build",
  "arguments": {
    "image": "/absolute/path/to/reference.png",
    "unity_project_path": "/absolute/path/to/unity-project",
    "connection_preset": "recommended_auto"
  }
}
```

reference 없이 catalog 기반 draft부터 시작하고 싶을 때도 같은 tool에 goal만 주면 된다.

```json
{
  "tool": "unity_rag.start_ui_build",
  "arguments": {
    "goal": "reward popup",
    "template_mode": "popup",
    "screen_name": "RewardPopupDraft",
    "title": "Reward Unlocked",
    "body": "Catalog-first popup draft",
    "primary_action_label": "CLAIM",
    "secondary_action_label": "CLOSE",
    "unity_project_path": "/absolute/path/to/unity-project"
  }
}
```

catalog-first draft는 `template_mode`로 `popup`, `hud`, `list` 중 하나를 고를 수 있다.

세부 단계를 직접 지정하고 싶을 때는 아래처럼 기존 tool을 개별 호출하면 된다.

```json
{
  "tool": "unity_rag.run_first_pass_ui_build",
  "arguments": {
    "image": "/absolute/path/to/reference.png",
    "unity_project_path": "/absolute/path/to/unity-project",
    "connection_preset": "recommended_auto"
  }
}
```

커스텀 endpoint가 필요할 때만 `provider_base_url` 같은 고급 설정을 함께 넣는다. 대부분의 사용자는 CLI든 MCP든 기본값 또는 `auto`/`recommended_auto`만으로 시작하면 된다. 세부 단계를 직접 제어하고 싶을 때만 `unity_rag.run_reference_to_resolved_blueprint`로 내려가면 된다.

## 문서 바로가기

### 핵심 문서

- [docs/asset-aware-ui-rag-architecture.md](./docs/asset-aware-ui-rag-architecture.md)
- [docs/provider-gateway-architecture.md](./docs/provider-gateway-architecture.md)
- [docs/troubleshooting/v0.3.0-gateway-benchmark-troubleshooting.md](./docs/troubleshooting/v0.3.0-gateway-benchmark-troubleshooting.md)
- [CHANGELOG.md](./CHANGELOG.md)
- [pipeline/gateway/README.md](./pipeline/gateway/README.md)
- [pipeline/workflows/README.md](./pipeline/workflows/README.md)
- [specs/mcp-sidecar-contract.md](./specs/mcp-sidecar-contract.md)
- [specs/provider-auth-matrix.md](./specs/provider-auth-matrix.md)
- [specs/provider-gateway-contract.md](./specs/provider-gateway-contract.md)
- [specs/ui-assembly-contract.md](./specs/ui-assembly-contract.md)
- [specs/ui-binding-contract.md](./specs/ui-binding-contract.md)

### 참고 자료

- [examples/mcp/end-to-end-usage.md](./examples/mcp/end-to-end-usage.md)

## 링크

- Repository: [Hanjo92/unity-resource-rag](https://github.com/Hanjo92/unity-resource-rag)
- Issues: [github.com/Hanjo92/unity-resource-rag/issues](https://github.com/Hanjo92/unity-resource-rag/issues)
- Releases: [github.com/Hanjo92/unity-resource-rag/releases](https://github.com/Hanjo92/unity-resource-rag/releases)
- License: [LICENSE](./LICENSE)

## 참고 사항

- 생성물과 캐시는 `.gitignore`로 제외한다.
- 실제 사용 전에는 Unity 프로젝트 안에서 C# 컴파일 상태를 한 번 더 확인하는 것이 좋다.
- 라이선스는 MIT이며, 자세한 내용은 루트 [LICENSE](./LICENSE)에 포함되어 있다.
