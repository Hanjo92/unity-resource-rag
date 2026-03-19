# Unity Resource RAG

`unity-resource-rag`는 레퍼런스 이미지나 목업을 보고, Unity 프로젝트 안의 실제 `Sprite`, `Prefab`, `TMP Font Asset`, `Material`을 우선 사용해 UI를 조립하기 위한 저장소다.

이 저장소는 두 레이어로 나뉜다.

- Unity 안쪽 실행 레이어: UPM 패키지 `com.hanjo92.unity-resource-rag`
- Unity 바깥 planning/retrieval/verification 레이어: Python sidecar pipeline + MCP server

## What It Includes

- Unity custom tool: `index_project_resources`
- Unity resource: `ui_asset_catalog`
- Unity custom tool: `apply_ui_blueprint`
- Sidecar workflow: `reference image -> resolved blueprint -> MCP handoff`
- Verification workflow: `screenshot compare -> repair handoff`
- MCP server wrapper: `python3 -m pipeline.mcp`

## Repository Layout

- `Packages/com.hanjo92.unity-resource-rag/`
- `pipeline/`
- `specs/`
- `docs/`
- `examples/`

## Links

- Repository: [Hanjo92/unity-resource-rag](https://github.com/Hanjo92/unity-resource-rag)
- Issues: [github.com/Hanjo92/unity-resource-rag/issues](https://github.com/Hanjo92/unity-resource-rag/issues)

## Requirements

- Python 3.11+
- Unity project with `unity-mcp`
- Optional: `OPENAI_API_KEY`

키가 없어도 동작은 가능하다. 이 경우 이미지 레이아웃 추출은 `local_heuristic` fallback을 사용한다.

## Python Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Unity Setup

1. Unity 프로젝트에 `unity-mcp`를 설치한다.
2. 이 저장소의 [Packages/com.hanjo92.unity-resource-rag](./Packages/com.hanjo92.unity-resource-rag) 를 `Packages/` 아래에 두거나 Git URL로 설치한다.
3. Unity에서 custom tool discovery가 되면 `index_project_resources`, `ui_asset_catalog`, `apply_ui_blueprint`를 사용할 수 있다.

패키지 문서는 [Packages/com.hanjo92.unity-resource-rag/README.md](./Packages/com.hanjo92.unity-resource-rag/README.md)를 보면 된다.

## MCP Client Setup

이 저장소는 `unity-mcp`를 대체하지 않는다. `unity-mcp`는 Unity Editor를 실제로 조작하고, 이 저장소의 MCP server는 planning/retrieval/repair sidecar를 담당한다.

클라이언트 설정 예시는 [docs/mcp-client-setup.md](./docs/mcp-client-setup.md) 와 [examples/mcp/mcp-client-config.example.json](./examples/mcp/mcp-client-config.example.json) 에 정리했다.

직접 실행할 때는:

```bash
python3 -m pipeline.mcp
```

또는:

```bash
python3 /absolute/path/to/unity-resource-rag/pipeline/mcp/server.py
```

## Quick Start

1. Unity에서 `index_project_resources`로 `resource_catalog.jsonl`을 만든다.
2. MCP client에 이 저장소의 sidecar server를 등록한다.
3. 레퍼런스 이미지에서 시작할 때는 `unity_rag.run_reference_to_resolved_blueprint`를 호출한다.
4. 생성된 handoff bundle을 Unity 쪽 `apply_ui_blueprint`와 `manage_camera`에 넘긴다.
5. 결과가 다르면 `unity_rag.run_verification_repair_loop`를 호출해 repair bundle을 만든다.

CLI로 먼저 시험할 때는:

```bash
python3 pipeline/workflows/run_reference_to_resolved_blueprint.py \
  --image /absolute/path/to/reference.png \
  --catalog /absolute/path/to/resource_catalog.jsonl \
  --provider auto
```

## Key Docs

- [docs/asset-aware-ui-rag-architecture.md](./docs/asset-aware-ui-rag-architecture.md)
- [specs/mcp-sidecar-contract.md](./specs/mcp-sidecar-contract.md)
- [specs/ui-assembly-contract.md](./specs/ui-assembly-contract.md)
- [specs/ui-binding-contract.md](./specs/ui-binding-contract.md)
- [examples/mcp/end-to-end-usage.md](./examples/mcp/end-to-end-usage.md)

## Upload Notes

- 생성물과 캐시는 `.gitignore`로 제외한다.
- 실제 사용 전 Unity 프로젝트 안에서 C# 컴파일 확인은 한 번 더 필요하다.
- 라이선스는 MIT이며, 루트 [LICENSE](./LICENSE)에 포함되어 있다.
