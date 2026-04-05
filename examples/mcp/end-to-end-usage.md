# MCP Sidecar Usage

## 1. Run Doctor First

실제 워크플로우 전에 전체 연결 상태를 한 번에 점검한다.

```json
{
  "tool": "unity_rag.doctor",
  "arguments": {
    "unity_project_path": "/absolute/path/to/unity-project",
    "connection_preset": "recommended_auto"
  }
}
```

응답에서 `overallStatus`가 `ok` 또는 작업 가능한 `warn`이고 `nextActions`가 정리되면 다음 단계로 넘어간다.

## 2. Single Entry Point

가장 짧은 시작은 이 tool 하나다. 내부에서 `doctor`를 먼저 실행하고, reference가 있으면 reference-first path를, 없으면 catalog-first draft path를 자동 선택한다.

```json
{
  "tool": "unity_rag.start_ui_build",
  "arguments": {
    "image": "/absolute/path/to/reference.png",
    "unity_project_path": "/absolute/path/to/unity-project",
    "connection_preset": "recommended_auto"
  }
}
```

reference가 아직 없을 때도 같은 entrypoint를 그대로 쓴다.

```json
{
  "tool": "unity_rag.start_ui_build",
  "arguments": {
    "goal": "shop popup",
    "screen_name": "ShopPopupDraft",
    "title": "Night Shift Shop",
    "body": "Catalog-first popup draft",
    "primary_action_label": "BUY",
    "secondary_action_label": "CLOSE",
    "unity_project_path": "/absolute/path/to/unity-project"
  }
}
```

## 3. One-Click First Pass

가장 짧은 happy path는 이 tool 하나다.

```json
{
  "tool": "unity_rag.run_first_pass_ui_build",
  "arguments": {
    "image": "/absolute/path/to/reference.png",
    "unity_project_path": "/absolute/path/to/unity-project",
    "connection_preset": "recommended_auto"
  }
}
```

이 호출은 필요하면 `index_project_resources`를 먼저 실행하고, resolved blueprint 생성과 Unity `apply_ui_blueprint` validate/apply까지 이어서 수행한다.

## 4. Inspect Provider Setup

실제 워크플로우를 실행하기 전에 연결 설정이 어떻게 해석되는지 먼저 확인한다.

```json
{
  "tool": "unity_rag.inspect_provider_setup",
  "arguments": {
    "connection_preset": "recommended_auto"
  }
}
```

응답에서 `missingSettings`가 비어 있고 `nextActions`가 실행 가능 상태를 안내하면 다음 단계로 넘어간다.

## 5. No-Reference Catalog Draft

reference 이미지가 아직 없으면 catalog만으로 popup draft부터 띄울 수 있다.

```json
{
  "tool": "unity_rag.run_catalog_draft_ui_build",
  "arguments": {
    "goal": "shop popup",
    "screen_name": "ShopPopupDraft",
    "title": "Night Shift Shop",
    "body": "Catalog-first popup draft",
    "primary_action_label": "BUY",
    "secondary_action_label": "CLOSE",
    "unity_project_path": "/absolute/path/to/unity-project"
  }
}
```

이 호출은 catalog에서 popup shell, panel sprite, icon, TMP font 후보를 찾아 draft blueprint를 만들고, 원하면 Unity `apply_ui_blueprint` validate/apply까지 이어서 수행한다.

## 6. Build The Catalog

Run the Unity-side export tool first so the sidecar has real project assets to bind against.

```bash
python3 pipeline/indexer/inspect_catalog.py \
  Library/ResourceRag/resource_catalog.jsonl
```

If the client handles tools better than resources, inspect the catalog through the Unity custom tool:

```json
{
  "tool": "query_ui_asset_catalog",
  "parameters": {
    "pageSize": 10,
    "pageNumber": 1
  }
}
```

## 7. Extract And Bind

From a reference image:

```bash
python3 pipeline/workflows/run_reference_to_resolved_blueprint.py \
  --image /absolute/path/to/reference.png \
  --catalog /absolute/path/to/resource_catalog.jsonl \
  --provider auto \
  --hint "mobile reward popup"
```

Codex에서 실행 중이고 같은 사용자 계정에 `~/.codex/auth.json`이 있다면 위 명령은 별도의 `OPENAI_API_KEY` 없이도 OpenAI provider 인증을 재사용한다.

Outputs:

- `01-reference-layout.json`
- `02-blueprint-template.json`
- `03-resolved-blueprint.json`
- `03-binding-report.json`
- `04-mcp-handoff.json`

## 8. Execute In Unity MCP

Use the resolved blueprint with `apply_ui_blueprint`.

`04-mcp-handoff.json`을 쓰는 클라이언트라면, follow-up 수정 전에 bundle 안의 `requests.inspectCatalog` 또는 `directToolFallback.inspectCatalog`로 catalog를 먼저 확인하는 편이 안전하다. 특히 binding report에 low-confidence / unresolved 항목이 있으면 catalog를 source of truth로 보고 candidate를 다시 고른다.

If the MCP client supports custom tools directly:

```json
{
  "tool": "execute_custom_tool",
  "customToolName": "apply_ui_blueprint",
  "parameters": {
    "action": "apply",
    "blueprintPath": "/absolute/path/to/03-resolved-blueprint.json"
  }
}
```

If the Unity MCP bridge exposes the tool directly:

```json
{
  "tool": "apply_ui_blueprint",
  "parameters": {
    "action": "apply",
    "blueprintPath": "/absolute/path/to/03-resolved-blueprint.json"
  }
}
```

Then capture a screenshot:

```json
{
  "tool": "manage_camera",
  "parameters": {
    "action": "screenshot",
    "capture_source": "scene_view",
    "view_target": "RewardPopupCanvas",
    "include_image": true,
    "max_resolution": 768
  }
}
```

## 9. Repair If Needed

Compare the screenshot against the reference image:

```bash
python3 pipeline/workflows/run_verification_repair_loop.py \
  /absolute/path/to/reference.png \
  /absolute/path/to/captured.png \
  --resolved-blueprint /absolute/path/to/03-resolved-blueprint.json
```

Outputs:

- `01-verification-report.json`
- `02-repair-handoff.json`
- `workflow-report.json`
