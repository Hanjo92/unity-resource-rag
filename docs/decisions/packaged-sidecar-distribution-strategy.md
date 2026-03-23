# Packaged Sidecar Distribution Strategy

Date: 2026-03-24

Status: Accepted

## Context

`unity-resource-rag` now has a usable Unity-first workflow, but the one-click path still depends on a Python sidecar that lives outside the UPM package. Until now, the stable setup path has effectively assumed a full local checkout of this repository plus a manually prepared Python environment.

That is acceptable for developers, but it creates too much friction for non-dev users:

- they do not need the full repo history, tests, or docs
- they should not need to understand the repo layout to point Unity at the sidecar
- they still need a predictable way to bootstrap Python dependencies

## Options Considered

### Option A. Keep guided full checkout as the only supported path

Pros:

- zero new packaging work
- exact parity with the development environment
- easiest path for contributors

Cons:

- still too heavy for non-dev users
- requires understanding `file:` package wiring plus the repo root
- harder to communicate as a "product" workflow

Decision:

- keep as a supported developer path
- do not keep as the only recommended path

### Option B. Portable sidecar bundle plus sidecar-local `.venv`

Definition:

- publish a small folder bundle that contains only the sidecar runtime surface:
  - `pipeline/`
  - `requirements.txt`
  - `LICENSE`
  - bundle manifest
- Unity points `Sidecar Runtime Root` at that folder
- `Bootstrap Python Runtime` creates a `.venv` inside that root and installs requirements there

Pros:

- removes the full-checkout requirement for non-dev users
- reuses the existing Python bootstrap and local-runner architecture
- keeps the MCP/CLI runtime contract unchanged
- bundle generation can happen as a release asset without redesigning the Unity package

Cons:

- Python still has to exist on the machine
- a release process must publish the bundle artifact
- version skew between Unity package and sidecar bundle must be communicated clearly

Decision:

- accepted as the primary next usability path for non-dev users

### Option C. Embedded Python runtime inside the Unity package

Pros:

- the smallest number of setup steps for end users
- easier to present as a self-contained Unity add-on

Cons:

- much higher maintenance cost across macOS / Windows / Linux
- larger release payloads
- more brittle security and patching story
- adds platform-specific installer/runtime ownership before the sidecar contract is fully stabilized

Decision:

- defer

### Option D. Native installer / app-managed runtime

Pros:

- strongest product-like onboarding experience
- can eventually hide bundle/runtime details entirely

Cons:

- requires productization work well beyond the current scope
- duplicates release, update, and repair concerns that are not yet justified

Decision:

- defer

## Decision

The recommended distribution strategy is:

`portable sidecar bundle + sidecar-local .venv bootstrap`

This means:

- contributors may keep using a full repository checkout
- non-dev users should be guided toward a portable sidecar bundle
- the Unity window should treat both paths as valid `Sidecar Runtime Root` values
- embedded Python and native installers remain deferred until the portable bundle path proves insufficient

## Supported Runtime Root Shapes

### Full checkout

Expected contents:

- `requirements.txt`
- `pipeline/mcp/server.py`
- `pipeline/mcp/local_runner.py`
- `Packages/com.hanjo92.unity-resource-rag/package.json`

### Portable sidecar bundle

Expected contents:

- `requirements.txt`
- `pipeline/mcp/server.py`
- `pipeline/mcp/local_runner.py`
- `unity-resource-rag-sidecar.json`

Suggested published artifact shape:

```text
unity-resource-rag-sidecar-<version>/
  LICENSE
  requirements.txt
  unity-resource-rag-sidecar.json
  pipeline/
    ...
```

## Why This Wins Now

- It materially lowers the barrier for non-dev users without rewriting the runtime architecture.
- It keeps the Unity-side code simple: the same local runner and bootstrap flow still work.
- It lets releases ship a sidecar artifact immediately, while preserving the contributor workflow.
- It leaves room for a later native installer if the bundle path still proves too technical.

## Consequences

### Positive

- one-click UX no longer has to be described as checkout-only
- documentation can separate developer setup from non-dev setup
- release assets can include a sidecar payload without changing the package layout

### Negative

- bundle publishing becomes part of release discipline
- sidecar/runtime compatibility must be called out in release notes
- Python installation is still an external prerequisite

## Immediate Follow-Up

1. Keep the Unity window wording on `Sidecar Runtime Root` rather than `Sidecar Repo Root`.
2. Ship a bundle build script in the repo.
3. Publish the portable sidecar bundle as a release asset in the next usability release.
4. Only revisit embedded Python if bundle adoption still leaves major onboarding pain.
