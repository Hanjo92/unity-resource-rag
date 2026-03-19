# Asset-Aware Unity UI RAG Architecture

## Goal

Reference image, mockup, or screenshot를 보고 Unity UI를 만들 때:

- 단순히 비슷한 색의 사각형을 조합하지 않는다.
- 프로젝트 안에 이미 있는 `Sprite`, `Prefab`, `TMP Font Asset`, `Material`, `Panel frame` 같은 실제 리소스를 우선 사용한다.
- `unity-mcp`로 Unity Editor를 조작하고, `unity-mcp-ui-layout`의 레이아웃 규칙으로 구조를 안정화한다.
- 부족한 것은 "프로젝트 리소스 인덱싱 + 벡터 검색 + 실제 에셋 바인딩" 계층으로 보완한다.

## Current Findings

### 1. `unity-mcp`

`unity-mcp`는 이미 Unity 조작용 기반 엔진으로 충분히 강하다.

- `manage_asset(search)`로 프로젝트 에셋을 검색할 수 있고, `guid`, `path`, `assetType`, `lastWriteTimeUtc`, `previewBase64`까지 얻을 수 있다.
- `manage_gameobject(create, prefab_path=...)`로 기존 프리팹을 실제로 인스턴스화할 수 있다.
- `manage_prefabs`로 프리팹 정보를 읽고 headless 수정도 가능하다.
- `manage_camera`로 스크린샷 검증 루프를 만들 수 있다.
- `execute_custom_tool`과 project-scoped custom tools 구조가 이미 있어서, 프로젝트 전용 "에셋 인덱서" 도구를 C#으로 얹기 좋다.
- Codex용 스킬 동기화 구조도 이미 있다.

정리하면, `unity-mcp`는 "Unity를 만지는 손"은 이미 제공한다. 부족한 것은 "어떤 에셋을 집을지 고르는 눈"이다.

### 2. `unity-mcp-ui-layout`

이 저장소는 UI 생성 품질을 올리는 워크플로 스킬이다.

- anchor, parent container, `CanvasScaler`, safe area, screenshot verification을 강하게 유도한다.
- mockup을 바로 픽셀 배치로 번역하지 않고, 상위 영역부터 구조화하게 만든다.
- 반복 구조를 prefab/reusable block으로 만들고, 단일 이미지처럼 보이는 영역은 괜히 쪼개지 않게 한다.

하지만 이 스킬은 어디까지나 "레이아웃 규칙"이다.

- 프로젝트 리소스를 인덱싱하지 않는다.
- 유사한 실제 스프라이트/프리팹을 검색하지 않는다.
- 어떤 장식 프레임이나 버튼이 프로젝트에 이미 존재하는지 알지 못한다.

즉, `unity-mcp-ui-layout`은 배치 철학은 좋지만, asset retrieval layer는 없다.

## Gap To Fill

현재 빠진 것은 아래 하나다.

`reference -> layout intent -> project asset retrieval -> actual asset binding -> screenshot verification`

이 흐름에서 `project asset retrieval`과 `actual asset binding`이 없다.

실행 계약과 예제는 [mcp-sidecar-contract.md](../specs/mcp-sidecar-contract.md)와 [examples/mcp/end-to-end-usage.md](../examples/mcp/end-to-end-usage.md)에 모아둔다.

그래서 목표 달성을 위해서는 `unity-mcp` 위에 다음 계층을 추가해야 한다.

1. Unity project resource cataloger
2. embedding/vector index
3. retrieval planner
4. actual asset binder
5. screenshot-based repair loop

## Recommended Architecture

### A. Unity Resource Catalog Layer

Unity Editor 안에서 프로젝트 리소스를 수집하는 계층이다.

우선 대상 리소스:

- `Sprite`
- `Texture2D`
- `Prefab`
- `TMP_FontAsset`
- `Material`
- `ScriptableObject` 기반 UI theme/token asset

각 리소스에 대해 최소한 아래 메타데이터를 만든다.

- `guid`
- `path`
- `asset_type`
- `name`
- `labels`
- `folder_tokens`
- `size`
- `aspect_ratio`
- `is_nine_slice_candidate`
- `is_reusable_widget`
- `preview_path` or preview bytes
- `semantic_text`
- `usage_context`

권장 방식:

- 1차 구현은 `unity-mcp`의 existing search를 활용한다.
- 2차 구현은 Unity 프로젝트 내부 custom tool로 `index_project_resources`를 만든다.

이 custom tool이 해야 할 일:

- `AssetDatabase.FindAssets`로 리소스 수집
- preview 캡처 또는 preview export
- prefab이면 hierarchy/component summary 생성
- sprite면 texture size, border, atlas, alpha 여부 수집
- folder/name/labels를 합쳐 `semantic_text` 생성
- 결과를 JSONL 또는 SQLite-friendly format으로 export

### B. Vectorization Layer

여기서 "리소스를 벡터화한다"는 것은 레퍼런스 이미지를 벡터로 바꾸는 게 아니라, 프로젝트 리소스 자체를 검색 가능한 임베딩으로 만든다는 뜻이다.

권장 임베딩 단위:

- sprite preview image embedding
- prefab preview image embedding
- `semantic_text` text embedding

권장 저장 방식:

- 로컬 SQLite + vector extension or lightweight local vector store
- 한 리소스당 하나의 primary record
- 필요하면 image/text embedding을 분리 저장

추천 스코어 구조:

`final_score = visual_similarity + text_similarity + type_fit + layout_fit + reuse_fit`

예시:

- `visual_similarity`: preview와 reference crop의 시각적 유사도
- `text_similarity`: `name/path/labels/semantic_text`와 query intent의 유사도
- `type_fit`: panel 영역에는 frame/panel/popup prefab 가중치, icon 영역에는 sprite 가중치
- `layout_fit`: aspect ratio, stretch suitability, nine-slice suitability
- `reuse_fit`: repeated region이면 prefab/reusable block 우대

### C. Reference Understanding Layer

레퍼런스 이미지를 보고 전체를 바로 생성하지 말고, 먼저 영역 단위 intent를 만든다.

영역 단위 예시:

- top header
- bottom nav bar
- left inventory panel
- item slot repeated block
- central popup frame
- decorative badge

각 영역에 대해 아래를 만든다.

- `region_type`
- `normalized_bounds`
- `repeat_count`
- `interaction_level`
- `preferred_asset_kind`
- `query_text`

예시:

- popup frame: `preferred_asset_kind = sprite_or_prefab_frame`
- repeated inventory slot: `preferred_asset_kind = prefab_or_sprite_slot`
- title text: `preferred_asset_kind = TMP`
- decorative ribbon: `preferred_asset_kind = sprite`

이 단계의 핵심은 `unity-mcp-ui-layout`의 규칙을 그대로 가져오는 것이다.

- 상위 영역 먼저
- 반복 구조 먼저 reusable block으로
- 단일 이미지로 보이는 영역은 함부로 쪼개지 않기

### D. Retrieval Layer

각 UI region마다 project assets에서 top-k 후보를 가져온다.

추천 retrieval 순서:

1. asset kind hard filter
2. aspect ratio / slice capability filter
3. text similarity
4. image similarity
5. context rerank

예시 hard filter:

- stretchable panel이면 nine-slice 가능 sprite 또는 panel prefab 우선
- repeated slot이면 prefab or slot sprite 우선
- icon이면 large background prefab 제외

중요 규칙:

- score가 낮으면 억지로 만들지 말고 "후보 부족" 상태를 반환한다.
- decorative region은 없는 리소스를 꾸며서 흉내내기보다 기존 단일 스프라이트를 우선 쓴다.
- repeated block은 leaf widget 여러 개보다 prefab 후보를 먼저 찾는다.

### E. Binding / Assembly Layer

후보 에셋이 정해지면 실제 Unity UI를 만든다.

UGUI 기준 권장 조립 순서:

1. `Canvas -> SafeAreaRoot -> ScreenRoot`
2. top-level regions 생성
3. region별로 asset bind
4. 반복 영역은 prefab instantiate
5. text/button/interactable 연결
6. 스크린샷 검증

실제 바인딩 방식:

- sprite 영역: `Image.sprite`에 asset path/guid 기반 참조 바인딩
- prefab 영역: `manage_gameobject(create, prefab_path=...)`
- prefab 내부 미세 조정: `manage_prefabs(modify_contents)`
- component field 바인딩: guid/path 기반 object reference 사용

핵심 원칙:

- "비슷하게 그리기"보다 "실제 리소스 붙이기"가 우선이다.
- frame/panel/background는 가능한 한 기존 sprite/prefab 그대로 사용한다.
- 필요한 경우에만 분해하고, 기본값은 기존 리소스를 살린다.

### F. Verification / Repair Loop

마지막은 `unity-mcp-ui-layout`의 장점을 그대로 쓴다.

루프:

1. shell 생성
2. 한 region만 조립
3. `manage_camera`로 screenshot
4. mismatch 분석
5. 구조 수정 후 다시 screenshot

수정 우선순위:

1. parent container
2. anchors / pivot
3. layout group
4. asset choice
5. offsets / spacing

즉, retrieval이 맞아도 구조가 틀리면 UI는 틀어지므로, layout skill과 retrieval system은 반드시 함께 움직여야 한다.

## What To Build First

### Phase 1. Project Asset Index

가장 먼저 만들 것:

- Unity custom tool: `index_project_resources`
- asset preview exporter
- local index schema
- basic vector store

완료 기준:

- 프로젝트 내 sprite/prefab/font/material을 수집할 수 있다.
- 각 항목을 `guid/path/type/preview/semantic_text`로 저장할 수 있다.
- 검색어 하나로 상위 후보를 뽑을 수 있다.

### Phase 2. Region-Level Retrieval

그 다음:

- reference image를 region들로 나누는 planner
- 각 region에 대한 query 생성
- type-aware reranker

완료 기준:

- 예를 들어 "top-right badge", "inventory slot", "popup frame" 같은 질의에 대해 실제 프로젝트 후보를 낼 수 있다.
- repeated block과 single-image region을 구분할 수 있다.

### Phase 3. Unity Assembly Loop

그 다음:

- chosen candidate를 실제 UGUI/UI Toolkit 구조에 바인딩
- prefab instantiate
- sprite bind
- screenshot verify

완료 기준:

- reference와 유사한 구조를 실제 프로젝트 리소스로 조립한다.
- 사각형 색칠이 아니라 실제 existing asset을 화면에 올린다.

## Suggested Module Boundaries

현재 워크스페이스가 비어 있으니, 아래처럼 시작하는 것이 좋다.

```text
Packages/
  com.hanjo92.unity-resource-rag/
    package.json
    README.md
    Editor/
      ResourceIndexing/
        IndexProjectResourcesTool.cs
        ResourceCatalogModels.cs
        ApplyUiBlueprintTool.cs
    Documentation~/
      resource-indexing-mvp.md
    Samples~/
      Blueprints/
        sample-popup-blueprint.json

docs/
  asset-aware-ui-rag-architecture.md

specs/
  resource-schema.md
  retrieval-ranking.md
  ui-assembly-contract.md

pipeline/
  indexer/
    inspect_catalog.py
  retrieval/
    search_catalog.py
```

설명:

- `Packages/com.hanjo92.unity-resource-rag/Editor/ResourceIndexing`은 Unity 안에서 도는 UPM custom tool 계층
- `pipeline/indexer`는 export된 catalog를 embedding/vector store에 적재
- `pipeline/retrieval`은 region별 후보 검색
- `pipeline/planner`는 reference를 region intent로 바꿈
- `pipeline/binder`는 retrieval 결과를 Unity MCP 호출 계획으로 바꿈

## Non-Negotiable Rules

이 프로젝트가 목표를 잃지 않으려면 아래 규칙은 강하게 고정하는 편이 좋다.

1. 실제 프로젝트 리소스가 있으면 생성형 대체물을 만들지 않는다.
2. 단일 이미지처럼 보이는 장식은 필요할 때만 분해한다.
3. 반복 구조는 prefab/reusable block 우선이다.
4. retrieval confidence가 낮으면 억지로 조립하지 않는다.
5. 모든 큰 변경은 screenshot verification을 통과해야 한다.
6. 레이아웃 문제를 색/offset으로 덮지 않는다.

## Immediate Next Step

바로 구현을 시작한다면 첫 스프린트는 아래가 맞다.

1. Unity custom tool `index_project_resources` 설계
2. asset catalog JSON schema 정의
3. preview export 포맷 결정
4. vector index MVP 구축
5. 텍스트 질의 기반 asset retrieval MVP 확인

이 5개가 되면, 그 다음부터는 `unity-mcp-ui-layout` 스킬을 그대로 활용해서 "검색된 실제 리소스를 어디에 붙일지" 조립 단계로 넘어갈 수 있다.
