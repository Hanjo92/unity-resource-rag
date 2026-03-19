# UI Binding Contract

## Goal

`bind_blueprint_assets.py` is the bridge between retrieval and `apply_ui_blueprint`.

It takes a blueprint template that still contains semantic asset queries and turns it into a resolved blueprint with concrete Unity asset references.

## Template Contract

Pre-apply templates may use `assetQuery` on visual nodes and `fontAssetQuery` inside `tmp_text.text`.

### `assetQuery`

```json
{
  "queryText": "blue rounded popup frame with gold trim",
  "regionType": "popup_frame",
  "preferredKind": "sprite",
  "aspectRatio": 1.71,
  "topK": 5,
  "minScore": 0.55,
  "bindingPolicy": "require_confident"
}
```

Fields:

- `queryText`: required semantic lookup text
- `regionType`: optional retrieval hint such as `popup_frame`, `inventory_slot`, `badge_icon`
- `preferredKind`: optional binding preference such as `sprite`, `prefab`, `tmp_font`
- `aspectRatio`: optional target ratio; if omitted, binder may infer it from `rect.sizeDelta`
- `topK`: optional shortlist size before choosing
- `minScore`: minimum confidence when `bindingPolicy` is `require_confident`
- `bindingPolicy`: `require_confident` or `best_match`

### `fontAssetQuery`

```json
{
  "queryText": "fantasy ui title font serif gold heading",
  "preferredKind": "tmp_font",
  "minScore": 0.45
}
```

This is attached at:

```json
{
  "kind": "tmp_text",
  "text": {
    "value": "Reward Unlocked",
    "fontAssetQuery": {
      "queryText": "fantasy ui title font serif gold heading",
      "preferredKind": "tmp_font"
    }
  }
}
```

## Output

The binder writes two files:

1. resolved blueprint JSON
2. binding report JSON

The resolved blueprint must conform to [ui-assembly-contract.md](./ui-assembly-contract.md).

## Resolution Rules

1. Search the project catalog with hybrid ranking.
2. Choose top-1 if it satisfies `bindingPolicy`.
3. Materialize a concrete asset reference:
   - `kind`
   - `path`
   - optional `guid`
   - optional `localFileId`
   - optional `subAssetName`
4. Remove the query object from the resolved output when binding succeeds.
5. Emit an issue in the binding report when confidence is too low or no candidate exists.

## Failure Policy

Default mode is strict:

- unresolved queries make the script exit non-zero
- resolved blueprint is still written for inspection
- unresolved query blocks stay in the written output so the original intent is preserved
- binding report records all unresolved nodes

Optional partial mode:

- `--allow-partial`
- unresolved query blocks stay in the blueprint output
- useful for review loops before Unity apply
