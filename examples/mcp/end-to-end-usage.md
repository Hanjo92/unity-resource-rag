# MCP Sidecar Usage

## 1. Inspect Provider Setup

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

## 2. Build The Catalog

Run the Unity-side export tool first so the sidecar has real project assets to bind against.

```bash
python3 pipeline/indexer/inspect_catalog.py \
  Library/ResourceRag/resource_catalog.jsonl
```

## 3. Extract And Bind

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

## 4. Execute In Unity MCP

Use the resolved blueprint with `apply_ui_blueprint`.

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

## 5. Repair If Needed

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
