# Unity Resource RAG

`com.hanjo92.unity-resource-rag`는 Unity 프로젝트 리소스를 카탈로그화하고, 실제 sprite/prefab/font 자산을 사용해 UI 블루프린트를 적용하기 위한 Editor 전용 UPM 패키지다.

포함 기능:

- `index_project_resources`
- `query_ui_asset_catalog`
- `ui_asset_catalog` resource
- `apply_ui_blueprint`

패키지 구조:

- `Editor/ResourceIndexing/`
- `Documentation~/`
- `Samples~/Blueprints/`

이 패키지는 Unity 안쪽 실행 레이어만 담는다.
벡터화/검색용 sidecar 스크립트는 저장소 루트의 `pipeline/` 아래에 유지한다.

빠른 시작:

1. 이 패키지를 Unity 프로젝트의 `Packages/` 아래에 두거나 git path로 설치한다.
2. `unity-mcp`가 설치된 프로젝트에서 `Editor/` 코드를 로드하고, HTTP Local transport를 쓴다면 `Project Scoped Tools`를 끈 뒤 Local HTTP Server를 다시 시작한다.
3. `index_project_resources`, `query_ui_asset_catalog`, `apply_ui_blueprint`는 custom tool로, `ui_asset_catalog`는 MCP resource로 노출되는지 확인한다.
4. `index_project_resources`로 카탈로그를 만든다.
5. 루트 `pipeline/retrieval/search_catalog.py`로 후보를 고른다.
6. `apply_ui_blueprint`로 실제 UI를 조립한다.
7. 필요하면 루트 `pipeline/workflows/run_reference_to_resolved_blueprint.py`로 reference-to-resolved-blueprint부터 MCP handoff bundle까지 한 번에 만든다.

샘플:

- `Samples~/Blueprints/sample-popup-blueprint.json`
- `Samples~/Blueprints/sample-popup-blueprint-template.json`

구현 메모는 `Documentation~/resource-indexing-mvp.md`를 참고하면 된다.

MCP sidecar contract는 [mcp-sidecar-contract.md](../../specs/mcp-sidecar-contract.md)와 [examples/mcp/end-to-end-usage.md](../../examples/mcp/end-to-end-usage.md)를 보면 된다.
