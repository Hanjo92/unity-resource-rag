# Retrieval Ranking Rules

## Goal

reference image의 특정 region에 대해, 프로젝트 안의 실제 Unity 리소스 후보를 우선순위대로 고른다.

## Input

각 query region은 최소한 아래 정보를 가져야 한다.

```json
{
  "regionType": "popup_frame",
  "queryText": "blue rounded popup frame with gold trim",
  "normalizedBounds": { "x": 0.2, "y": 0.18, "w": 0.6, "h": 0.46 },
  "repeatCount": 1,
  "interactionLevel": "static",
  "preferredAssetKind": ["sprite", "prefab"]
}
```

## Ranking Pipeline

### 1. Hard Filter

아래는 점수 계산 전에 무조건 걸러낸다.

- asset kind mismatch
- gross aspect ratio mismatch
- popup frame인데 icon/small badge인 경우
- repeatable block인데 단일 decorative texture만 있는 경우

### 2. Primary Score

현재 MVP 기본 점수:

`score = 0.35 * vector + 0.25 * text + 0.20 * type_fit + 0.15 * ui_fit + 0.05 * aspect_fit`

비고:

- 현재는 preview image embedding이 없으므로 `visual` 대신 `vector + text hybrid`를 쓴다.
- `vector`는 카탈로그의 `semanticText/name/path/labels/prefabSummary`를 벡터화한 검색 점수다.
- 나중에 preview/image embedding이 들어오면 `vector`를 `visual + semantic`로 분리한다.

### 3. Score Definitions

#### vector

- queryText와 resource vector index 사이 유사도
- 현재 MVP는 `tfidf-sparse-v1`
- 향후에는 text embedding + image embedding을 모두 수용

#### text

- queryText와 `semanticText` 유사도
- folder/name/label token도 같이 반영

#### type_fit

- regionType과 asset kind의 궁합

예시:

- `popup_frame` -> sprite nine-slice, frame prefab 우대
- `inventory_slot` -> slot prefab, slot sprite 우대
- `badge_icon` -> sprite 우대

#### ui_fit

- nine-slice 가능 여부
- repeatable block 여부
- single-image region 적합 여부
- interaction level 적합 여부

## Bonus / Penalty

### Bonus

- repeated structure에 prefab이 맞으면 `+0.10`
- stretchable container에 nine-slice sprite가 맞으면 `+0.10`
- exact semantic keyword match면 `+0.05`

### Penalty

- decorative single-image region을 과도하게 쪼개야 하는 asset이면 `-0.10`
- aspect ratio 차이가 크면 `-0.15`
- static frame인데 interactive-heavy prefab이면 `-0.10`

## Decision Rules

### Use Existing Prefab First

아래 조건이면 prefab 후보를 sprite 조합보다 우선한다.

- repeated structure
- child hierarchy가 이미 맞는 경우
- 버튼/아이콘/텍스트 slot이 이미 준비된 경우

### Keep Single-Image Regions Intact

아래 조건이면 single sprite/frame을 우선한다.

- interaction 없음
- resize 요구가 약함
- 장식 프레임/배경 역할

### Reject Low Confidence

top-1 score가 낮으면 억지로 바인딩하지 않는다.

권장:

- `score >= 0.75`: auto-select candidate
- `0.55 <= score < 0.75`: human-review or screenshot loop with 2-3 candidates
- `score < 0.55`: no confident match

## Output Contract

retrieval 결과는 최소 아래를 반환한다.

```json
{
  "regionId": "popup_frame_01",
  "chosenCandidate": {
    "guid": "abc123",
    "path": "Assets/UI/Popup/RewardPopupFrame.png",
    "bindingKind": "sprite",
    "score": 0.84
  },
  "alternatives": [
    {
      "guid": "def456",
      "path": "Assets/UI/Popup/BlueFrame.prefab",
      "bindingKind": "prefab",
      "score": 0.78
    }
  ],
  "decisionReason": [
    "single-image decorative frame",
    "nine-slice capable",
    "aspect ratio matches target region"
  ]
}
```

## Binder Hand-Off Rules

retrieval 결과는 binder에게 아래 의사결정까지 넘겨야 한다.

- `bind_as_sprite`
- `instantiate_prefab`
- `build_repeated_from_prefab`
- `fallback_to_layout_only`

이렇게 해야 layout planner가 retrieval 결과를 실제 Unity MCP 호출로 바꿀 수 있다.
