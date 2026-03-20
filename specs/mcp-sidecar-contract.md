# MCP Sidecar Contract

## Goal

This contract describes the sidecar pipeline that sits next to `unity-mcp`.

The sidecar is responsible for planning and verification work that is easier to do outside Unity:

- extract a reference layout from an image
- convert the layout into a blueprint template
- bind the template to real project assets
- produce an MCP handoff bundle for Unity execution
- analyze screenshot mismatches and produce a repair handoff bundle

Unity still owns the actual scene mutation through `apply_ui_blueprint` and screenshot capture through `manage_camera`.

## Tool Family

The sidecar pipeline is organized into four user-facing flows.

### 1. Reference Extraction

Input:

```json
{
  "image": "/absolute/path/to/reference.png",
  "provider": "auto",
  "gatewayUrl": "http://127.0.0.1:8080",
  "screenName": "RewardPopup",
  "hint": [
    "mobile reward popup",
    "safe area required"
  ]
}
```

Output:

```json
{
  "output": "/.../RewardPopup.reference-layout.json",
  "report": "/.../RewardPopup.extract-report.json",
  "screenName": "RewardPopup",
  "regionCount": 3,
  "resolvedProvider": "gateway"
}
```

Script:

- [extract_reference_layout.py](../pipeline/planner/extract_reference_layout.py)

### 2. Layout To Blueprint

Input:

- reference layout JSON

Output:

- blueprint template JSON with `assetQuery` and `text.fontAssetQuery`

Script:

- [reference_layout_to_blueprint.py](../pipeline/planner/reference_layout_to_blueprint.py)

### 3. Blueprint Binding

Input:

- blueprint template JSON
- `resource_catalog.jsonl`
- optional `resource_vector_index.json`

Output:

- resolved blueprint JSON
- binding report JSON

Script:

- [bind_blueprint_assets.py](../pipeline/retrieval/bind_blueprint_assets.py)

### 4. Unity MCP Handoff

Input:

- resolved blueprint JSON
- binding report JSON

Output:

- MCP handoff bundle

The bundle contains:

- preflight notes
- validate request
- apply request
- screenshot verification request

Script:

- [build_mcp_handoff_bundle.py](../pipeline/workflows/build_mcp_handoff_bundle.py)

## Verification Flow

When Unity has produced a screenshot, the sidecar can compare it with the reference image.

Input:

- reference image
- captured image
- optional resolved blueprint

Output:

- verification report
- repair handoff bundle

Scripts:

- [analyze_screenshot_mismatch.py](../pipeline/verification/analyze_screenshot_mismatch.py)
- [build_repair_handoff_bundle.py](../pipeline/verification/build_repair_handoff_bundle.py)

## End To End Flow

The recommended order is:

1. `extract_reference_layout`
2. `reference_layout_to_blueprint`
3. `bind_blueprint_assets`
4. `build_mcp_handoff_bundle`
5. Unity MCP `apply_ui_blueprint`
6. Unity MCP `manage_camera`
7. `analyze_screenshot_mismatch`
8. `build_repair_handoff_bundle`
9. Unity MCP repair pass

## Unity Side Package

The Unity package that actually executes the resolved blueprint is:

- [README.md](../Packages/com.hanjo92.unity-resource-rag/README.md)
- [ui-assembly-contract.md](./ui-assembly-contract.md)
- [ui-binding-contract.md](./ui-binding-contract.md)

The sidecar output is designed so the Unity package can consume it without guessing.

## Example Handoff Bundle

See:

- [sample-mcp-handoff-bundle.json](../examples/mcp/sample-mcp-handoff-bundle.json)

## Example Repair Bundle

See:

- [sample-repair-handoff-bundle.json](../examples/mcp/sample-repair-handoff-bundle.json)
