# Pipeline MCP Server

This folder exposes the existing sidecar pipeline as an MCP stdio server.

Tools:

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

Behavior:

- `initialize` negotiates MCP protocol version and declares the `tools` capability.
- `tools/list` returns the five pipeline wrappers and their input schemas.
- `tools/call` shells out to the existing pipeline scripts and returns JSON text content.

The wrappers reuse the current sidecar scripts instead of duplicating the workflow logic. Extraction-related wrappers expose a higher-level `connection_preset` first and still forward the extractor auth options (`provider_api_key_env`, `auth_mode`, `oauth_token_env`, `oauth_token_file`, `oauth_token_command`, `codex_auth_file`) when advanced overrides are needed. If both are provided, `connection_preset` takes precedence for provider/auth defaults:

- `pipeline/planner/extract_reference_layout.py`
- `pipeline/workflows/run_reference_to_resolved_blueprint.py`
- `pipeline/workflows/run_verification_repair_loop.py`
- `pipeline/workflows/build_mcp_handoff_bundle.py`

For Unity-side usage, keep using the generated handoff bundles with `apply_ui_blueprint` and `manage_camera`.

Client setup examples:

- [docs/mcp-client-setup.md](../../docs/mcp-client-setup.md)
- [examples/mcp/mcp-client-config.example.json](../../examples/mcp/mcp-client-config.example.json)
