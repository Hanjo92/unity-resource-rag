# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

- Repository polish, badges, and changelog maintenance on `main`

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

[Unreleased]: https://github.com/Hanjo92/unity-resource-rag/compare/v0.1.0...main
[0.1.0]: https://github.com/Hanjo92/unity-resource-rag/releases/tag/v0.1.0
