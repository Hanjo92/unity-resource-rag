from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Mapping

from .models import (
    BenchmarkFixtureError,
    _require_float,
    _require_int,
    _require_list,
    _require_schema_version,
    _require_str,
)


@dataclass(frozen=True)
class BenchmarkScreenResult:
    screen_name: str
    retrieval_top1_hit_rate: float
    retrieval_top3_hit_rate: float
    normalized_mean_absolute_error: float
    foreground_bbox_iou: float
    repair_iterations: int
    has_meaningful_mismatch: bool
    status: str
    notes: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkScreenResult":
        notes = payload.get("notes", [])
        if not isinstance(notes, list):
            raise BenchmarkFixtureError("Expected list at 'notes'.")
        return cls(
            screen_name=_require_str(payload, "screenName"),
            retrieval_top1_hit_rate=_require_float(payload, "retrievalTop1HitRate"),
            retrieval_top3_hit_rate=_require_float(payload, "retrievalTop3HitRate"),
            normalized_mean_absolute_error=_require_float(payload, "normalizedMeanAbsoluteError"),
            foreground_bbox_iou=_require_float(payload, "foregroundBboxIoU"),
            repair_iterations=_require_int(payload, "repairIterations"),
            has_meaningful_mismatch=bool(payload.get("hasMeaningfulMismatch", False)),
            status=_require_str(payload, "status"),
            notes=tuple(item for item in notes if isinstance(item, str) and item),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "screenName": self.screen_name,
            "retrievalTop1HitRate": self.retrieval_top1_hit_rate,
            "retrievalTop3HitRate": self.retrieval_top3_hit_rate,
            "normalizedMeanAbsoluteError": self.normalized_mean_absolute_error,
            "foregroundBboxIoU": self.foreground_bbox_iou,
            "repairIterations": self.repair_iterations,
            "hasMeaningfulMismatch": self.has_meaningful_mismatch,
            "status": self.status,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class BenchmarkRunSummary:
    screen_count: int
    passed_screens: int
    failed_screens: int
    average_retrieval_top1_hit_rate: float
    average_retrieval_top3_hit_rate: float
    max_normalized_mean_absolute_error: float
    min_foreground_bbox_iou: float

    @classmethod
    def from_results(cls, results: tuple[BenchmarkScreenResult, ...]) -> "BenchmarkRunSummary":
        if not results:
            raise BenchmarkFixtureError("Benchmark summary requires at least one screen result.")
        return cls(
            screen_count=len(results),
            passed_screens=sum(1 for result in results if result.status == "pass"),
            failed_screens=sum(1 for result in results if result.status != "pass"),
            average_retrieval_top1_hit_rate=round(mean(result.retrieval_top1_hit_rate for result in results), 4),
            average_retrieval_top3_hit_rate=round(mean(result.retrieval_top3_hit_rate for result in results), 4),
            max_normalized_mean_absolute_error=max(result.normalized_mean_absolute_error for result in results),
            min_foreground_bbox_iou=min(result.foreground_bbox_iou for result in results),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkRunSummary":
        return cls(
            screen_count=_require_int(payload, "screenCount"),
            passed_screens=_require_int(payload, "passedScreens"),
            failed_screens=_require_int(payload, "failedScreens"),
            average_retrieval_top1_hit_rate=_require_float(payload, "averageRetrievalTop1HitRate"),
            average_retrieval_top3_hit_rate=_require_float(payload, "averageRetrievalTop3HitRate"),
            max_normalized_mean_absolute_error=_require_float(payload, "maxNormalizedMeanAbsoluteError"),
            min_foreground_bbox_iou=_require_float(payload, "minForegroundBboxIoU"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "screenCount": self.screen_count,
            "passedScreens": self.passed_screens,
            "failedScreens": self.failed_screens,
            "averageRetrievalTop1HitRate": self.average_retrieval_top1_hit_rate,
            "averageRetrievalTop3HitRate": self.average_retrieval_top3_hit_rate,
            "maxNormalizedMeanAbsoluteError": self.max_normalized_mean_absolute_error,
            "minForegroundBboxIoU": self.min_foreground_bbox_iou,
        }


@dataclass(frozen=True)
class BenchmarkRunReport:
    schema_version: str
    benchmark_name: str
    project_name: str
    generated_at_utc: str
    results: tuple[BenchmarkScreenResult, ...]
    summary: BenchmarkRunSummary
    notes: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkRunReport":
        notes = payload.get("notes", [])
        if not isinstance(notes, list):
            raise BenchmarkFixtureError("Expected list at 'notes'.")
        results = tuple(BenchmarkScreenResult.from_dict(item) for item in _require_list(payload, "results"))
        summary = BenchmarkRunSummary.from_dict(_require_mapping(payload, "summary"))
        if summary.screen_count != len(results):
            raise BenchmarkFixtureError(
                f"Benchmark summary screenCount {summary.screen_count} does not match result count {len(results)}."
            )
        if summary.passed_screens + summary.failed_screens != len(results):
            raise BenchmarkFixtureError(
                "Benchmark summary passedScreens plus failedScreens must equal the number of results."
            )
        return cls(
            schema_version=_require_schema_version(payload),
            benchmark_name=_require_str(payload, "benchmarkName"),
            project_name=_require_str(payload, "projectName"),
            generated_at_utc=_require_str(payload, "generatedAtUtc"),
            results=results,
            summary=summary,
            notes=tuple(item for item in notes if isinstance(item, str) and item),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "benchmarkName": self.benchmark_name,
            "projectName": self.project_name,
            "generatedAtUtc": self.generated_at_utc,
            "results": [result.to_dict() for result in self.results],
            "summary": self.summary.to_dict(),
            "notes": list(self.notes),
        }


def _require_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise BenchmarkFixtureError(f"Expected mapping at '{key}'.")
    return value
