# Resource Catalog Schema

## Purpose

Unity 프로젝트 안의 UI 관련 리소스를 벡터 검색 가능한 공통 포맷으로 정규화한다.

이 스키마의 목표는 두 가지다.

1. retrieval이 asset type을 정확히 필터링할 수 있게 한다.
2. binder가 선택된 asset을 Unity에 다시 정확히 바인딩할 수 있게 한다.

## Record Shape

```json
{
  "id": "guid-or-stable-hash",
  "guid": "string",
  "path": "Assets/UI/...",
  "assetType": "Sprite|Texture2D|Prefab|TMP_FontAsset|Material|ScriptableObject",
  "name": "InventorySlotBlue",
  "labels": ["ui", "inventory", "slot"],
  "folderTokens": ["ui", "inventory", "slots"],
  "semanticText": "blue inventory slot frame rounded border reusable",
  "preview": {
    "path": "Library/ResourceRagPreviews/....png",
    "width": 256,
    "height": 256
  },
  "geometry": {
    "width": 128,
    "height": 128,
    "aspectRatio": 1.0,
    "border": { "left": 12, "right": 12, "top": 12, "bottom": 12 },
    "pivot": { "x": 0.5, "y": 0.5 }
  },
  "uiHints": {
    "isNineSliceCandidate": true,
    "isSingleImageRegion": true,
    "isRepeatableBlock": false,
    "preferredUse": ["panel_frame", "slot_frame"]
  },
  "prefabSummary": {
    "rootName": null,
    "componentTypes": [],
    "childPaths": []
  },
  "embeddingRefs": {
    "imageEmbeddingId": "optional",
    "textEmbeddingId": "optional"
  },
  "binding": {
    "kind": "sprite",
    "unityLoadPath": "Assets/UI/Inventory/InventorySlotBlue.png"
  },
  "updatedAtUtc": "2026-03-19T00:00:00Z"
}
```

## Required Fields

- `guid`
- `path`
- `assetType`
- `name`
- `semanticText`
- `binding.kind`
- `binding.unityLoadPath`

## Asset-Type Specific Rules

### Sprite / Texture2D

필수 추가 필드:

- `geometry.width`
- `geometry.height`
- `geometry.aspectRatio`

가능하면 추가:

- sprite border
- alpha 여부
- atlas membership

### Prefab

필수 추가 필드:

- `prefabSummary.rootName`
- `prefabSummary.componentTypes`
- `prefabSummary.childPaths`

가능하면 추가:

- preview render
- repeated UI block 여부
- button/list/item slot/card/popup/frame 같은 semantic tags

### TMP Font Asset

필수 추가 필드:

- font asset name
- atlas size
- fallback font summary

### Material

필수 추가 필드:

- shader name
- render pipeline compatibility hint

## Semantic Text Construction

`semanticText`는 아래를 합쳐서 만든다.

1. asset name tokenization
2. folder path tokenization
3. Unity labels
4. inferred UI role tags
5. prefab/component hints

예시:

`Assets/UI/Popup/BlueRewardPopup.prefab`

-> `blue reward popup modal dialog panel frame reusable prefab`

## Binding Kinds

`binding.kind`는 아래 중 하나를 사용한다.

- `sprite`
- `texture`
- `prefab`
- `tmp_font`
- `material`
- `scriptable_object`

이 값은 retrieval 이후 binder가 어떤 MCP 호출을 써야 하는지 결정하는 기준이 된다.

## Export Format

MVP는 JSONL을 권장한다.

이유:

- diff/debug가 쉽다
- Python/Node/C# 어디서든 다루기 쉽다
- batch embedding이 쉽다

파일 예시:

`artifacts/resource-catalog/resource_catalog.jsonl`

## Preview Export Rules

- preview는 검색용이므로 너무 큰 원본 이미지를 그대로 쓰지 않는다.
- 기본 preview는 정사각형 256 또는 384 해상도를 권장한다.
- transparent background를 유지한다.
- prefab preview는 가능하면 isolation render 또는 editor preview를 쓴다.

## Hard Constraints

1. binder가 다시 Unity object를 찾을 수 있어야 하므로 `guid` 또는 `path`는 반드시 살아 있어야 한다.
2. text-only metadata만으로는 부족하므로 image preview가 가능한 자산은 preview를 함께 저장한다.
3. retrieval이 잘못된 type을 뽑지 않게 `assetType`과 `binding.kind`를 분리해 둔다.
