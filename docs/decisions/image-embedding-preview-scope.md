# Image Embedding Preview Scope

Status: accepted for `v0.3.0`

## Context

`image_embedding` was tracked as a stretch spike because visual similarity can improve frame, badge, and slot-style retrieval, but the scope can expand quickly if we try to solve full production reranking in the same release.

For `v0.3.0`, we want one clear preview path that helps the team validate the boundary without pulling the release into a larger multimodal rollout.

## Decision

We will treat `image_embedding` as a preview-only local gateway capability in `v0.3.0`.

The preview output will stay sparse and token-like so it can plug into the existing retrieval bridge without introducing a new vector-store contract. The capability should produce a visual-token representation that is easy to score, inspect, and diff in benchmarks.

Production rollout, external provider integration, and broader multimodal rerank policies are deferred to `0.3.x`.

## What Is Implemented Now

- A local preview capability can exist behind the gateway boundary.
- The output shape should remain sparse and inspectable, not a dense production embedding API.
- The preview is meant to support benchmark exploration and contract validation only.

## What Is Explicitly Deferred

- Production-grade `image_embedding` rollout.
- Vendor-specific multimodal adapter work.
- Dense image vector contracts.
- New retrieval index formats or external vector database changes.
- Any promise that image-based rerank becomes part of the `v0.3.0` release gate.

## Rationale

This keeps the release focused on the `v0.3.0` goals that are already on the critical path: gateway-first routing, retrieval measurability, bounded repair, and reproducible benchmark artifacts.

The preview approach gives us two benefits:

- It proves the gateway and retrieval seams can carry a visual signal without destabilizing the current sparse retrieval flow.
- It leaves room to redesign the final production shape after the benchmark baseline is established.

## Tradeoffs

The preview path is intentionally smaller than a full multimodal rollout, so it will not capture every visual nuance.

That tradeoff is acceptable because the goal is to validate the architecture boundary and benchmark workflow first. If the preview shows value, the `0.3.x` work can choose a denser or more provider-specific contract with less risk.

## Follow-Up

If this preview proves useful, the next step is a separate `0.3.x` decision that defines the production `image_embedding` contract, adapter policy, and benchmark gate criteria.
