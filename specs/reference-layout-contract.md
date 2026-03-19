# Reference Layout Contract

## Goal

레퍼런스 이미지나 목업을 바로 Unity object로 만들지 않고, 먼저 영역 단위 계획으로 정리한다.

이 계약은 vision model, 수동 annotator, 또는 다른 planner가 공통으로 만들어낼 수 있는 중간 산출물이다.

## Root Shape

```json
{
  "screenName": "RewardPopup",
  "referenceResolution": { "x": 1920, "y": 1080 },
  "safeAreaRoot": {
    "name": "SafeAreaRoot",
    "components": [
      {
        "typeName": "MyGame.UI.SafeAreaFitter",
        "properties": { "applyOnAwake": true }
      }
    ]
  },
  "regions": []
}
```

## Region Shape

```json
{
  "id": "popup_frame",
  "name": "PopupFrame",
  "kind": "image",
  "parentId": "safe_area_root",
  "regionType": "popup_frame",
  "queryText": "blue rounded popup frame with gold trim reward modal window",
  "preferredKind": "sprite",
  "normalizedBounds": { "x": 0.25, "y": 0.24, "w": 0.5, "h": 0.52 },
  "image": {
    "type": "Sliced",
    "raycastTarget": false
  }
}
```

## Coordinate System

`normalizedBounds` is relative to the parent region.

- origin: top-left
- `x`, `y`: parent-relative start position
- `w`, `h`: parent-relative size
- value range: `0.0` to `1.0`

If a region should fill its parent instead of using explicit bounds:

```json
{
  "id": "content_column",
  "kind": "container",
  "parentId": "popup_frame",
  "stretchToParent": true
}
```

## Supported Kinds

- `container`
- `image`
- `prefab_instance`
- `tmp_text`

## Query Fields

For `image` and `prefab_instance`:

- `queryText`
- `regionType`
- `preferredKind`
- `bindingPolicy`
- `minScore`
- `topK`

These become `assetQuery` in the generated blueprint template.

For `tmp_text`:

```json
{
  "id": "title_text",
  "kind": "tmp_text",
  "text": {
    "value": "Reward Unlocked",
    "fontQueryText": "fantasy ui title font serif gold heading",
    "fontPreferredKind": "tmp_font",
    "fontMinScore": 0.45
  }
}
```

These become `text.fontAssetQuery` in the generated blueprint template.

## Optional Machine-Generated Fields

자동 추출기는 아래 선택 필드도 넣을 수 있다.

- `repeatCount`
- `interactionLevel`
- `confidence`

이 필드들은 retrieval/binding 품질을 높이기 위한 힌트이며, 현재 템플릿 생성기는 없어도 동작한다.

## Output

`reference_layout_to_blueprint.py` converts this plan into a blueprint template that conforms to the pre-apply stage described in [ui-binding-contract.md](./ui-binding-contract.md).
