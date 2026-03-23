# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Changed

- simplified the Unity window auth wording around three user-facing sign-in methods: current Codex sign-in, API key from environment, and offline local fallback
- moved Codex auth file overrides into the advanced setup area so first-run users can stay on the recommended sign-in path without seeing low-level preset jargon
- renamed readiness auth status from provider-centric wording to `AI Access` summaries that explain the next action in user language
- generalized catalog-first draft templates beyond popup-only mode so `popup`, `hud`, and `list` drafts can be selected from the Unity window and MCP entrypoints
- added a `Last Run Artifacts` panel in the Unity window so blueprint, search report, handoff, capture, repair, and case export outputs can be reopened without digging through logs

## [0.5.0] - 2026-03-22

Stable Unity-first usability release for `unity-resource-rag`.

### Added

- Unity editor readiness dashboard with `Ready / Attention / Blocked` setup summaries
- repo-local Python runtime bootstrap assistant from inside `Window > Unity Resource RAG`
- non-blocking multi-phase build flow that checks readiness before starting `unity_rag.start_ui_build`
- in-window `Capture Result` and `Run Repair Handoff` follow-up actions
- case export writer that saves markdown and JSON quality reports under `Library/ResourceRag/Cases/`
- local runner bridge commands for `doctor`, `capture_result`, and verification repair handoff execution

### Changed

- moved the gateway default port to `8090` so it does not collide with Unity MCP HTTP Local's common `8080` default
- clarified the Unity MCP HTTP Local setup path, including `Project Scoped Tools` behavior and the fact that `ui_asset_catalog` is an MCP resource rather than a callable tool
- promoted the Unity window from beta setup helper to the main stable path for `Quick Setup -> Readiness -> Start UI Build -> Capture & Repair -> Case Export`
- package metadata, MCP server metadata, and gateway metadata now report version `0.5.0`

### Notes

- the stable path assumes a full local checkout so the Unity package can reach the root `pipeline/` sidecar
- `Run Repair Handoff` still requires a reference image; catalog-first draft flows without a reference stop at capture and manual review
- the long-lived untracked example draft blueprint was intentionally left outside the release payload

## [0.4.0-beta] - 2026-03-21

### Added

- beta release notes for real-project validation under `docs/releases/0.4.0-beta.md`
- GitHub quality case report template for collecting real-project validation results

### Changed

- validated the `catalog -> blueprint -> Unity output` flow in a real Unity project
- fixed Unity hookup issues discovered during live package installation, including the editor assembly reference and `ApplyUiBlueprintTool` compile path
- aligned upcoming release positioning around a beta milestone focused on real-project validation rather than full quality sign-off

### Notes

- current evidence supports a beta release for functional validation
- generation quality still needs additional real-project cases across multiple screen types before a broader stability-oriented release

## [0.3.0] - 2026-03-21

Gateway-first benchmarkable pipeline release for `unity-resource-rag`.

### Added

- gateway capability router with `vision_layout_extraction`, `vision_layout_repair_analysis`, `text_embedding`, and preview `image_embedding`
- retrieval embedding seam and low-confidence binding states with candidate preservation
- structured repair patch candidate artifacts
- benchmark fixture scaffold, retrieval/screen scorecard runners, and baseline gate publisher
- team troubleshooting docs and image embedding preview ADR

### Changed

- gateway startup now exposes benchmark-oriented capability and adapter registration instead of a single extraction slice
- retrieval bridge can score generic sparse gateway embedding outputs, including the preview visual-token path
- benchmark assets and sample scorecards are checked in as portable repo-relative artifacts
- MCP server, gateway server, and UPM package metadata now report version `0.3.0`

### Notes

- The checked-in `v0.3.0` gate artifacts are generated from sample benchmark inputs and are suitable as an engineering baseline.
- Before a stricter release-candidate sign-off, rerun the same gate with real project captures.

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

[Unreleased]: https://github.com/Hanjo92/unity-resource-rag/compare/0.5.0...main
[0.5.0]: https://github.com/Hanjo92/unity-resource-rag/releases/tag/0.5.0
[0.4.0-beta]: https://github.com/Hanjo92/unity-resource-rag/releases/tag/0.4.0-beta
[0.3.0]: https://github.com/Hanjo92/unity-resource-rag/releases/tag/0.3.0
[0.2.1]: https://github.com/Hanjo92/unity-resource-rag/releases/tag/0.2.1
[0.1.0]: https://github.com/Hanjo92/unity-resource-rag/releases/tag/v0.1.0
