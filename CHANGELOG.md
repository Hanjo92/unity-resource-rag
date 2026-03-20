# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

- No unreleased changes yet.

## [0.2.1] - 2026-03-20

Provider runtime and release polish for `unity-resource-rag`.

### Added

- gateway provider module with a minimal `vision_layout_extraction` vertical slice
- Gemini direct gateway adapter with API key, ADC, OAuth token file, and access token modes
- gateway architecture and provider auth contract docs
- provider setup regression tests for preset normalization and auth inspection

### Changed

- `inspect_provider_setup` and planner auth resolution now treat `openai_compatible` as explicit auth instead of silently reusing Codex OAuth
- `connection_preset` now clears conflicting auth fields so the selected preset wins over stale inputs
- MCP client setup docs and workflow guides now distinguish direct OpenAI auth from custom OpenAI-compatible provider auth
- MCP server and UPM package metadata now report version `0.2.1`

### Notes

- Python pipeline files and new provider setup tests were validated locally.
- MCP stdio server startup and provider setup smoke checks were verified locally.

## [0.1.0] - 2026-03-19

Initial public scaffold for `unity-resource-rag`.

### Added

- UPM package `com.hanjo92.unity-resource-rag`
- Unity custom tools `index_project_resources` and `apply_ui_blueprint`
- Unity resource `ui_asset_catalog`
- resource catalog export and preview-aware catalog builder
- blueprint models and Unity asset resolver
- reference image planner and layout-to-blueprint conversion
- TF-IDF vector index and hybrid retrieval flow
- blueprint asset binding and binding report generation
- MCP handoff bundle generation for Unity-side execution
- screenshot verification and repair handoff pipeline
- stdio MCP server wrapper for sidecar tools
- local heuristic extraction fallback when API keys are unavailable
- architecture docs, contracts, examples, and MCP client setup guide

### Notes

- Python scripts were syntax-checked locally.
- Example JSON files were validated locally.
- Final Unity compile/runtime verification still needs a real Unity project with `unity-mcp`.

[Unreleased]: https://github.com/Hanjo92/unity-resource-rag/compare/0.2.1...main
[0.2.1]: https://github.com/Hanjo92/unity-resource-rag/releases/tag/0.2.1
[0.1.0]: https://github.com/Hanjo92/unity-resource-rag/releases/tag/v0.1.0
