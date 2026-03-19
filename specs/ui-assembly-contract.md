# UI Assembly Contract

## Goal

`apply_ui_blueprint` is the execution-side contract that turns retrieved real assets into a deterministic Unity UI hierarchy.
It supports core UGUI composition primitives plus TextMeshPro text, layout groups, layout elements, and project-specific custom components.

## Root Shape

```json
{
  "screenName": "RewardPopup",
  "stack": "ugui",
  "root": {
    "id": "root_canvas",
    "name": "RewardPopupCanvas",
    "kind": "canvas",
    "canvasScaler": {
      "uiScaleMode": "ScaleWithScreenSize",
      "referenceResolution": { "x": 1920, "y": 1080 },
      "screenMatchMode": "MatchWidthOrHeight",
      "matchWidthOrHeight": 0.5
    },
    "children": []
  }
}
```

## Supported Node Kinds

### `canvas`

- creates a new Canvas root
- configures `CanvasScaler` when possible
- should normally be the root node

### `container`

- creates an empty `RectTransform` GameObject
- used for safe-area roots, regions, layout containers

### `prefab_instance`

- resolves a real prefab by `path` or `guid`
- instantiates it with `PrefabUtility.InstantiatePrefab`
- preferred for repeated structures and reusable blocks

### `image`

- creates a `RectTransform` + `Image`
- resolves a real sprite asset by `path`, `guid`, `localFileId`, or `subAssetName`
- preferred for single-image regions and frame/background art

### `tmp_text`

- creates a `RectTransform` + `TextMeshProUGUI`
- optionally resolves a real `TMP_FontAsset`
- supports text value, font size, alignment, color, auto-sizing, and raycast target

## Asset Reference

```json
{
  "kind": "sprite",
  "path": "Assets/UI/Popup/RewardPopupFrame.png",
  "guid": null,
  "localFileId": null,
  "subAssetName": null
}
```

Allowed `kind` values:

- `sprite`
- `prefab`
- `texture`
- `material`
- `tmp_font`

Current MVP directly binds:

- `sprite`
- `prefab`
- `tmp_font`

## RectTransform Spec

```json
{
  "anchorMin": { "x": 0.5, "y": 0.5 },
  "anchorMax": { "x": 0.5, "y": 0.5 },
  "pivot": { "x": 0.5, "y": 0.5 },
  "anchoredPosition": { "x": 0, "y": 0 },
  "sizeDelta": { "x": 960, "y": 560 }
}
```

Supported fields:

- `anchorMin`
- `anchorMax`
- `pivot`
- `anchoredPosition`
- `sizeDelta`
- `offsetMin`
- `offsetMax`

## Image Spec

```json
{
  "type": "Sliced",
  "preserveAspect": false,
  "raycastTarget": false,
  "color": "#FFFFFFFF"
}
```

## TMP Text Spec

```json
{
  "value": "Reward Unlocked",
  "fontAsset": {
    "kind": "tmp_font",
    "path": "Assets/UI/Fonts/TitleFont.asset"
  },
  "fontSize": 42,
  "alignment": "Center",
  "enableAutoSizing": false,
  "raycastTarget": false,
  "color": "#FFF4D2FF"
}
```

## Layout Group Spec

```json
{
  "kind": "Vertical",
  "padding": { "left": 48, "right": 48, "top": 48, "bottom": 48 },
  "childAlignment": "UpperCenter",
  "spacing": 24,
  "childControlWidth": true,
  "childControlHeight": false,
  "childForceExpandWidth": true,
  "childForceExpandHeight": false
}
```

Supported kinds:

- `Horizontal`
- `Vertical`
- `Grid`

## Layout Element Spec

```json
{
  "preferredWidth": 720,
  "preferredHeight": 60,
  "flexibleWidth": 1,
  "ignoreLayout": false
}
```

## Custom Components

Project-specific behavior such as safe area ownership can be attached through custom components.

```json
{
  "typeName": "MyGame.UI.SafeAreaFitter",
  "properties": {
    "applyOnAwake": true
  }
}
```

This lets the blueprint reuse whatever safe-area or adaptive component the project already ships.

## MVP Guarantees

The first implementation guarantees:

1. blueprint validation before mutation
2. real sprite/prefab resolution by asset identity
3. basic UGUI hierarchy creation
4. deterministic rect transform assignment
5. TextMeshPro text node creation
6. layout group / layout element application
7. project-specific custom component attachment

The first implementation does not yet guarantee:

1. existing-root reuse or replacement strategy
2. automatic safe-area behavior without a project component
3. post-apply screenshot capture inside the same tool
4. full repair loop after screenshot comparison

## Example

```json
{
  "screenName": "RewardPopup",
  "stack": "ugui",
  "root": {
    "id": "root_canvas",
    "name": "RewardPopupCanvas",
    "kind": "canvas",
    "canvasScaler": {
      "uiScaleMode": "ScaleWithScreenSize",
      "referenceResolution": { "x": 1920, "y": 1080 },
      "screenMatchMode": "MatchWidthOrHeight",
      "matchWidthOrHeight": 0.5
    },
    "children": [
      {
        "id": "safe_area_root",
        "name": "SafeAreaRoot",
        "kind": "container",
        "components": [
          {
            "typeName": "MyGame.UI.SafeAreaFitter",
            "properties": {
              "applyOnAwake": true
            }
          }
        ],
        "rect": {
          "anchorMin": { "x": 0, "y": 0 },
          "anchorMax": { "x": 1, "y": 1 },
          "offsetMin": { "x": 0, "y": 0 },
          "offsetMax": { "x": 0, "y": 0 }
        },
        "children": [
          {
            "id": "popup_frame",
            "name": "PopupFrame",
            "kind": "image",
            "asset": {
              "kind": "sprite",
              "path": "Assets/UI/Popup/RewardPopupFrame.png"
            },
            "image": {
              "type": "Sliced",
              "raycastTarget": false
            },
            "rect": {
              "anchorMin": { "x": 0.5, "y": 0.5 },
              "anchorMax": { "x": 0.5, "y": 0.5 },
              "pivot": { "x": 0.5, "y": 0.5 },
              "anchoredPosition": { "x": 0, "y": 0 },
              "sizeDelta": { "x": 960, "y": 560 }
            },
            "children": [
              {
                "id": "content_column",
                "name": "ContentColumn",
                "kind": "container",
                "layoutGroup": {
                  "kind": "Vertical",
                  "padding": { "left": 48, "right": 48, "top": 48, "bottom": 48 },
                  "childAlignment": "UpperCenter",
                  "spacing": 24,
                  "childControlWidth": true,
                  "childControlHeight": false,
                  "childForceExpandWidth": true,
                  "childForceExpandHeight": false
                },
                "rect": {
                  "anchorMin": { "x": 0, "y": 0 },
                  "anchorMax": { "x": 1, "y": 1 },
                  "offsetMin": { "x": 0, "y": 0 },
                  "offsetMax": { "x": 0, "y": 0 }
                },
                "children": [
                  {
                    "id": "title_text",
                    "name": "TitleText",
                    "kind": "tmp_text",
                    "text": {
                      "value": "Reward Unlocked",
                      "fontAsset": {
                        "kind": "tmp_font",
                        "path": "Assets/UI/Fonts/TitleFont.asset"
                      },
                      "fontSize": 42,
                      "alignment": "Center",
                      "enableAutoSizing": false,
                      "raycastTarget": false,
                      "color": "#FFF4D2FF"
                    },
                    "layoutElement": {
                      "preferredHeight": 60,
                      "flexibleWidth": 1
                    },
                    "rect": {
                      "anchorMin": { "x": 0.5, "y": 1.0 },
                      "anchorMax": { "x": 0.5, "y": 1.0 },
                      "pivot": { "x": 0.5, "y": 1.0 },
                      "sizeDelta": { "x": 720, "y": 60 }
                    }
                  }
                ]
              }
            ]
          }
        ]
      }
    ]
  }
}
```
