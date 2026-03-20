# Benchmarks

This directory holds concrete benchmark fixtures and sample reports for `v0.3.0`.

Current scaffold:

- `v0.3.0-reference-suite/`: a two-screen example suite that future retrieval and verification runners can consume

Conventions:

- keep fixture paths relative to the suite root
- keep JSON camelCase to match the rest of the repository
- keep sample reports small enough to use as schema fixtures in tests

Runner entrypoints:

- `python3 -m pipeline.evaluation.run_retrieval_benchmark <suite-manifest> <result-payload>`
- `python3 -m pipeline.evaluation.run_screen_benchmark <suite-manifest> <report-payload>`
- `python3 -m pipeline.evaluation.publish_benchmark_gate_report <suite-manifest> <result-payload> <report-payload> --output-dir <dir>`

Retrieval runners expect a file with `schemaVersion`, `benchmarkName`, `projectName`, `generatedAtUtc`, and a `screens` array. Each screen entry should include `screenName` and a `regions` array with `regionId`, `top1HitRate`, `top3HitRate`, and an optional `selectedCandidateScore`.

Screen runners expect a benchmark report shaped like `sample-benchmark-report.json`, then compare each screen result against fixture thresholds and verification metrics.

Both runners emit deterministic scorecards with:

- `kind`
- `summary`
- `screenChecks`
- `hasErrors`

The default output filename is derived from the input payload name and ends in `.retrieval-scorecard.json` or `.screen-scorecard.json`.

The gate publisher writes a portable baseline artifact set:

- `retrieval-scorecard.json`
- `screen-scorecard.json`
- `benchmark-gate-report.json`
- `benchmark-gate-report.md`

The checked-in `v0.3.0-reference-suite/baseline-artifacts/` directory is generated from `sample-retrieval-result.json` and `sample-benchmark-report.json` so the team can diff the gate output over time without machine-local absolute paths.
