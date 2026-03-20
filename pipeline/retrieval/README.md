# Retrieval MVP

현재 retrieval MVP는 `catalog -> vector index -> hybrid search` 흐름까지 바로 돌릴 수 있다.

파일:

- `build_vector_index.py`
- `bind_blueprint_assets.py`
- `embedding_bridge.py`
- `search_catalog.py`
- `vector_index.py`

입력:

- `resource_catalog.jsonl`
- optional `resource_vector_index.json`
- blueprint template json with `assetQuery` / `text.fontAssetQuery`
- query text
- optional `region-type`
- optional `preferred-kind`
- optional `aspect-ratio`

예시:

```bash
python3 pipeline/retrieval/build_vector_index.py \
  Library/ResourceRag/resource_catalog.jsonl

python3 pipeline/retrieval/search_catalog.py \
  Library/ResourceRag/resource_catalog.jsonl \
  --query "blue rounded popup frame with gold trim" \
  --region-type popup_frame \
  --preferred-kind sprite \
  --aspect-ratio 1.71 \
  --top-k 5

python3 pipeline/retrieval/bind_blueprint_assets.py \
  Packages/com.hanjo92.unity-resource-rag/Samples~/Blueprints/sample-popup-blueprint-template.json \
  Library/ResourceRag/resource_catalog.jsonl
```

`search_catalog.py`는 같은 폴더에 `resource_vector_index.json`이 있으면 자동으로 읽고, 없으면 기존 lexical 모드로 fallback 한다.
`bind_blueprint_assets.py`는 blueprint template 안의 query를 실제 `asset` / `text.fontAsset` 참조로 치환하고, 별도 binding report를 남긴다.
confidence가 충분하면 `auto_bind`, 애매하지만 보류하고 싶으면 `hold_if_uncertain` 또는 `preserve_candidates`, 기준 미달이면 `review_needed`로 떨어진다.
`hold`와 `review_needed`는 resolved blueprint에 원래 query block을 다시 남기고, binding report의 `summary.bindingStates`와 각 binding entry의 `bindingState`로 구분된다.
`auto_bind`만 query를 제거하고 실제 Unity asset reference를 쓴다.

이 binding report와 resolved blueprint는 [mcp-sidecar-contract.md](../../specs/mcp-sidecar-contract.md)에서 정의한 MCP handoff bundle의 입력이다.

하이브리드 검색 점수:

- vector match
- text match
- type fit
- region fit
- aspect fit

의도:

1. Unity export 결과를 바로 검색해볼 수 있게 한다.
2. 프로젝트 리소스를 실제 검색 가능한 벡터 인덱스로 바꾼다.
3. `apply_ui_blueprint` 이전에 candidate shortlist와 최종 asset binding 단계를 명확히 한다.

현재 벡터 스킴은 `tfidf-sparse-v1`이다.

- 장점: 외부 API 없이 바로 생성 가능하다.
- `embedding_bridge.py`는 gateway sparse embedding 응답을 현재 sparse index 점수로 연결하는 seam 역할을 한다.
- `image_embedding`은 preview-only local capability로 들어왔고, `visual-token-sparse-v1` 출력은 같은 bridge/scorer 경로로 rerank spike를 해볼 수 있다.
- production image embedding provider 연동과 asset-side preview index 설계는 아직 `0.3.x` 범위다.
- 다음 단계: preview/image encoder를 추가해서 visual similarity를 score에 합친다.
