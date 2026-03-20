"""Benchmark fixture and report helpers for Unity Resource RAG."""

from .fixtures import (
    BenchmarkFixtureError,
    BenchmarkScreenBundle,
    BenchmarkSuiteBundle,
    load_benchmark_report,
    load_benchmark_suite,
    load_retrieval_fixture,
    load_screen_fixture,
    load_thresholds,
)
from .models import (
    BenchmarkReferenceResolution,
    BenchmarkRegionFixture,
    BenchmarkRetrievalFixture,
    BenchmarkScreenEntry,
    BenchmarkScreenFixture,
    BenchmarkSuiteManifest,
    BenchmarkThresholds,
)
from .report_models import (
    BenchmarkRunReport,
    BenchmarkRunSummary,
    BenchmarkScreenResult,
)
from .run_retrieval_benchmark import evaluate_retrieval_benchmark, main as run_retrieval_benchmark
from .run_screen_benchmark import evaluate_screen_benchmark, main as run_screen_benchmark

__all__ = [
    "BenchmarkFixtureError",
    "BenchmarkReferenceResolution",
    "BenchmarkRegionFixture",
    "BenchmarkRetrievalFixture",
    "BenchmarkRunReport",
    "BenchmarkRunSummary",
    "BenchmarkScreenBundle",
    "BenchmarkScreenEntry",
    "BenchmarkScreenFixture",
    "BenchmarkScreenResult",
    "BenchmarkSuiteBundle",
    "BenchmarkSuiteManifest",
    "BenchmarkThresholds",
    "evaluate_retrieval_benchmark",
    "evaluate_screen_benchmark",
    "load_benchmark_report",
    "load_benchmark_suite",
    "load_retrieval_fixture",
    "load_screen_fixture",
    "load_thresholds",
    "run_retrieval_benchmark",
    "run_screen_benchmark",
]
