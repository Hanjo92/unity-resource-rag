from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


SCHEMA_VERSION = "0.3.0"
ALLOWED_INTERACTION_LEVELS = {"static", "read_only", "interactive"}
ALLOWED_BINDING_POLICIES = {"require_confident", "review_if_uncertain", "best_match"}


class BenchmarkFixtureError(ValueError):
    """Raised when a benchmark fixture does not match the expected schema."""


def _require_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise BenchmarkFixtureError(f"Expected mapping at '{key}'.")
    return value


def _require_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise BenchmarkFixtureError(f"Expected non-empty string at '{key}'.")
    return value


def _require_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise BenchmarkFixtureError(f"Expected integer at '{key}'.")
    return value


def _require_int_ge(payload: Mapping[str, Any], key: str, minimum: int) -> int:
    value = _require_int(payload, key)
    if value < minimum:
        raise BenchmarkFixtureError(f"Expected integer >= {minimum} at '{key}'.")
    return value


def _require_float(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)):
        raise BenchmarkFixtureError(f"Expected number at '{key}'.")
    return float(value)


def _require_list(payload: Mapping[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise BenchmarkFixtureError(f"Expected list at '{key}'.")
    return value


def _require_allowed_str(payload: Mapping[str, Any], key: str, allowed: set[str]) -> str:
    value = _require_str(payload, key)
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise BenchmarkFixtureError(f"Expected one of {{{allowed_values}}} at '{key}'.")
    return value


def _require_schema_version(payload: Mapping[str, Any]) -> str:
    schema_version = _require_str(payload, "schemaVersion")
    if schema_version != SCHEMA_VERSION:
        raise BenchmarkFixtureError(f"Expected schemaVersion '{SCHEMA_VERSION}', got '{schema_version}'.")
    return schema_version


@dataclass(frozen=True)
class BenchmarkReferenceResolution:
    width: int
    height: int

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkReferenceResolution":
        return cls(
            width=_require_int(payload, "width"),
            height=_require_int(payload, "height"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BenchmarkScreenEntry:
    screen_name: str
    display_name: str
    reference_image: str
    retrieval_fixture: str
    screen_fixture: str
    thresholds: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkScreenEntry":
        return cls(
            screen_name=_require_str(payload, "screenName"),
            display_name=_require_str(payload, "displayName"),
            reference_image=_require_str(payload, "referenceImage"),
            retrieval_fixture=_require_str(payload, "retrievalFixture"),
            screen_fixture=_require_str(payload, "screenFixture"),
            thresholds=_require_str(payload, "thresholds"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "screenName": self.screen_name,
            "displayName": self.display_name,
            "referenceImage": self.reference_image,
            "retrievalFixture": self.retrieval_fixture,
            "screenFixture": self.screen_fixture,
            "thresholds": self.thresholds,
        }


@dataclass(frozen=True)
class BenchmarkSuiteManifest:
    schema_version: str
    benchmark_name: str
    project_name: str
    description: str
    reference_resolution: BenchmarkReferenceResolution
    screens: tuple[BenchmarkScreenEntry, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkSuiteManifest":
        screens = tuple(BenchmarkScreenEntry.from_dict(item) for item in _require_list(payload, "screens"))
        if not screens:
            raise BenchmarkFixtureError("Benchmark suite must contain at least one screen.")
        screen_names = [screen.screen_name for screen in screens]
        if len(screen_names) != len(set(screen_names)):
            raise BenchmarkFixtureError("Benchmark suite screen names must be unique.")
        return cls(
            schema_version=_require_schema_version(payload),
            benchmark_name=_require_str(payload, "benchmarkName"),
            project_name=_require_str(payload, "projectName"),
            description=_require_str(payload, "description"),
            reference_resolution=BenchmarkReferenceResolution.from_dict(_require_mapping(payload, "referenceResolution")),
            screens=screens,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "benchmarkName": self.benchmark_name,
            "projectName": self.project_name,
            "description": self.description,
            "referenceResolution": self.reference_resolution.to_dict(),
            "screens": [screen.to_dict() for screen in self.screens],
        }


@dataclass(frozen=True)
class BenchmarkRegionFixture:
    region_id: str
    region_type: str
    query_text: str
    normalized_bounds: dict[str, float]
    preferred_asset_kinds: tuple[str, ...] = field(default_factory=tuple)
    repeat_count: int = 1
    interaction_level: str = "static"
    binding_policy: str = "require_confident"
    min_score: float | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkRegionFixture":
        preferred_asset_kinds = tuple(
            kind for kind in _require_list(payload, "preferredAssetKinds") if isinstance(kind, str) and kind
        )
        if not preferred_asset_kinds:
            raise BenchmarkFixtureError("preferredAssetKinds must contain at least one string.")
        normalized_bounds = _require_mapping(payload, "normalizedBounds")
        return cls(
            region_id=_require_str(payload, "regionId"),
            region_type=_require_str(payload, "regionType"),
            query_text=_require_str(payload, "queryText"),
            normalized_bounds={
                "x": _require_float(normalized_bounds, "x"),
                "y": _require_float(normalized_bounds, "y"),
                "w": _require_float(normalized_bounds, "w"),
                "h": _require_float(normalized_bounds, "h"),
            },
            preferred_asset_kinds=preferred_asset_kinds,
            repeat_count=_require_int_ge(payload, "repeatCount", 1) if "repeatCount" in payload else 1,
            interaction_level=_require_allowed_str(payload, "interactionLevel", ALLOWED_INTERACTION_LEVELS)
            if "interactionLevel" in payload
            else "static",
            binding_policy=_require_allowed_str(payload, "bindingPolicy", ALLOWED_BINDING_POLICIES)
            if "bindingPolicy" in payload
            else "require_confident",
            min_score=float(payload["minScore"]) if payload.get("minScore") is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "regionId": self.region_id,
            "regionType": self.region_type,
            "queryText": self.query_text,
            "normalizedBounds": self.normalized_bounds,
            "preferredAssetKinds": list(self.preferred_asset_kinds),
            "repeatCount": self.repeat_count,
            "interactionLevel": self.interaction_level,
            "bindingPolicy": self.binding_policy,
        }
        if self.min_score is not None:
            payload["minScore"] = self.min_score
        return payload


@dataclass(frozen=True)
class BenchmarkRetrievalFixture:
    schema_version: str
    screen_name: str
    regions: tuple[BenchmarkRegionFixture, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkRetrievalFixture":
        regions = tuple(BenchmarkRegionFixture.from_dict(item) for item in _require_list(payload, "regions"))
        if not regions:
            raise BenchmarkFixtureError("Retrieval fixture must contain at least one region.")
        region_ids = [region.region_id for region in regions]
        if len(region_ids) != len(set(region_ids)):
            raise BenchmarkFixtureError("Retrieval fixture region ids must be unique.")
        return cls(
            schema_version=_require_schema_version(payload),
            screen_name=_require_str(payload, "screenName"),
            regions=regions,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "screenName": self.screen_name,
            "regions": [region.to_dict() for region in self.regions],
        }


@dataclass(frozen=True)
class BenchmarkScreenFixture:
    schema_version: str
    screen_name: str
    expected_layout: str
    expected_mismatch_classes: tuple[str, ...] = field(default_factory=tuple)
    max_repair_iterations: int = 1
    acceptance_notes: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkScreenFixture":
        mismatch_classes = payload.get("expectedMismatchClasses", [])
        if not isinstance(mismatch_classes, list):
            raise BenchmarkFixtureError("Expected list at 'expectedMismatchClasses'.")
        notes = payload.get("acceptanceNotes", [])
        if not isinstance(notes, list):
            raise BenchmarkFixtureError("Expected list at 'acceptanceNotes'.")
        return cls(
            schema_version=_require_schema_version(payload),
            screen_name=_require_str(payload, "screenName"),
            expected_layout=_require_str(payload, "expectedLayout"),
            expected_mismatch_classes=tuple(item for item in mismatch_classes if isinstance(item, str) and item),
            max_repair_iterations=int(payload.get("maxRepairIterations", 1)),
            acceptance_notes=tuple(item for item in notes if isinstance(item, str) and item),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "screenName": self.screen_name,
            "expectedLayout": self.expected_layout,
            "expectedMismatchClasses": list(self.expected_mismatch_classes),
            "maxRepairIterations": self.max_repair_iterations,
            "acceptanceNotes": list(self.acceptance_notes),
        }


@dataclass(frozen=True)
class BenchmarkThresholds:
    schema_version: str
    retrieval_top1_min: float
    retrieval_top3_min: float
    normalized_mean_absolute_error_max: float
    foreground_bbox_iou_min: float
    max_repair_iterations: int

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "BenchmarkThresholds":
        return cls(
            schema_version=_require_schema_version(payload),
            retrieval_top1_min=_require_float(payload, "retrievalTop1Min"),
            retrieval_top3_min=_require_float(payload, "retrievalTop3Min"),
            normalized_mean_absolute_error_max=_require_float(payload, "normalizedMeanAbsoluteErrorMax"),
            foreground_bbox_iou_min=_require_float(payload, "foregroundBboxIoUMin"),
            max_repair_iterations=int(payload.get("maxRepairIterations", 1)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "retrievalTop1Min": self.retrieval_top1_min,
            "retrievalTop3Min": self.retrieval_top3_min,
            "normalizedMeanAbsoluteErrorMax": self.normalized_mean_absolute_error_max,
            "foregroundBboxIoUMin": self.foreground_bbox_iou_min,
            "maxRepairIterations": self.max_repair_iterations,
        }
