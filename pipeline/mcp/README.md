# Pipeline MCP Server

This folder exposes the existing sidecar pipeline as an MCP stdio server.

Tools:

- `unity_rag.start_ui_build`
- `unity_rag.doctor`
- `unity_rag.run_first_pass_ui_build`
- `unity_rag.run_catalog_draft_ui_build`
- `unity_rag.inspect_provider_setup`
- `unity_rag.extract_reference_layout`
- `unity_rag.run_reference_to_resolved_blueprint`
- `unity_rag.run_verification_repair_loop`
- `unity_rag.build_mcp_handoff_bundle`

Run locally:

```bash
python3 -m pipeline.mcp
```

or:

```bash
python3 /absolute/path/to/unity-resource-rag/pipeline/mcp/server.py
```

Unity editor window integration can also call the same entrypoint through a local subprocess bridge:

```bash
python3 -m pipeline.mcp.local_runner start_ui_build --payload-file /tmp/payload.json
```

The same local bridge also exposes window-friendly helper commands:

- `doctor`
- `capture_result`
- `run_verification_repair_loop`
- `start_ui_build`

Behavior:

- `initialize` negotiates MCP protocol version and declares the `tools` capability.
- `tools/list` returns the pipeline wrappers and their input schemas.
- `tools/call` shells out to the existing pipeline scripts and returns JSON text content.

권장 시작점은 `unity_rag.start_ui_build`다. 이 tool은 `doctor`를 먼저 실행하고, reference 이미지가 있으면 `unity_rag.run_first_pass_ui_build`, 아직 없으면 `unity_rag.run_catalog_draft_ui_build`를 자동 선택한다. Unity 창에서는 이 흐름 위에 readiness dashboard, Python bootstrap, capture/repair, case export UX를 얹는다.

The wrappers reuse the current sidecar scripts instead of duplicating the workflow logic. Extraction-related wrappers expose a higher-level `connection_preset` first and still forward the extractor auth options (`provider_api_key_env`, `auth_mode`, `oauth_token_env`, `oauth_token_file`, `oauth_token_command`, `codex_auth_file`) when advanced overrides are needed. If both are provided, `connection_preset` takes precedence for provider/auth defaults:

- `pipeline/planner/extract_reference_layout.py`
- `pipeline/workflows/run_reference_to_resolved_blueprint.py`
- `pipeline/workflows/run_verification_repair_loop.py`
- `pipeline/workflows/build_mcp_handoff_bundle.py`

For Unity-side usage, keep using the generated handoff bundles with `apply_ui_blueprint` and `manage_camera`.

Client setup examples:

- [docs/mcp-client-setup.md](../../docs/mcp-client-setup.md)
- [examples/mcp/mcp-client-config.example.json](../../examples/mcp/mcp-client-config.example.json)
