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


def evaluate_retrieval_benchmark(*args, **kwargs):
    from .run_retrieval_benchmark import evaluate_retrieval_benchmark as _impl

    return _impl(*args, **kwargs)


def run_retrieval_benchmark(*args, **kwargs):
    from .run_retrieval_benchmark import main as _impl

    return _impl(*args, **kwargs)


def evaluate_screen_benchmark(*args, **kwargs):
    from .run_screen_benchmark import evaluate_screen_benchmark as _impl

    return _impl(*args, **kwargs)


def run_screen_benchmark(*args, **kwargs):
    from .run_screen_benchmark import main as _impl

    return _impl(*args, **kwargs)


def publish_benchmark_gate_report(*args, **kwargs):
    from .publish_benchmark_gate_report import publish_benchmark_gate_report as _impl

    return _impl(*args, **kwargs)


def publish_benchmark_gate(*args, **kwargs):
    from .publish_benchmark_gate_report import main as _impl

    return _impl(*args, **kwargs)

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
    "publish_benchmark_gate",
    "publish_benchmark_gate_report",
    "run_retrieval_benchmark",
    "run_screen_benchmark",
]
