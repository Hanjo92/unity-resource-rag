# v0.3.0 Benchmark Gate Report

- Status: `PASS`
- Generated At: `2026-03-20T00:00:00Z`
- Suite: `examples/benchmarks/v0.3.0-reference-suite/benchmark-manifest.json`
- Retrieval Input: `examples/benchmarks/v0.3.0-reference-suite/sample-retrieval-result.json`
- Screen Report Input: `examples/benchmarks/v0.3.0-reference-suite/sample-benchmark-report.json`

## Gate Checks

| Gate | Status | Detail |
| --- | --- | --- |
| `retrieval_benchmark` | `PASS` | failedScreens=0 |
| `screen_benchmark` | `PASS` | failedScreens=0 |
| `must_have_release_gate` | `PASS` | failedChecks=0 |

## Retrieval Scorecard

- Passed Screens: `2/2`
- Failed Screens: `0`
- Failed Regions: `none`

## Screen Scorecard

- Passed Screens: `2/2`
- Failed Screens: `0`
- Failed Screen List: `none`

## Follow-up
- Current baseline uses sample benchmark artifacts; rerun with real project captures before release candidate sign-off.
- Rerun this benchmark gate after any retrieval, repair, or gateway contract change that can affect the two benchmark screens.
