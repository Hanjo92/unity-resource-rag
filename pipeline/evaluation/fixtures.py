from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import (
    BenchmarkFixtureError,
    BenchmarkRetrievalFixture,
    BenchmarkScreenEntry,
    BenchmarkScreenFixture,
    BenchmarkSuiteManifest,
    BenchmarkThresholds,
)
from .report_models import BenchmarkRunReport


@dataclass(frozen=True)
class BenchmarkScreenBundle:
    entry: BenchmarkScreenEntry
    reference_image_path: Path
    retrieval_fixture_path: Path
    screen_fixture_path: Path
    thresholds_path: Path
    retrieval_fixture: BenchmarkRetrievalFixture
    screen_fixture: BenchmarkScreenFixture
    thresholds: BenchmarkThresholds


@dataclass(frozen=True)
class BenchmarkSuiteBundle:
    manifest_path: Path
    manifest: BenchmarkSuiteManifest
    screens: tuple[BenchmarkScreenBundle, ...]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise BenchmarkFixtureError(f"Expected JSON object in {path}.")
    return payload


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def resolve_relative_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base_dir / path).resolve()


def load_retrieval_fixture(path: Path) -> BenchmarkRetrievalFixture:
    return BenchmarkRetrievalFixture.from_dict(load_json(path))


def load_screen_fixture(path: Path) -> BenchmarkScreenFixture:
    return BenchmarkScreenFixture.from_dict(load_json(path))


def load_thresholds(path: Path) -> BenchmarkThresholds:
    return BenchmarkThresholds.from_dict(load_json(path))


def load_benchmark_report(path: Path) -> BenchmarkRunReport:
    return BenchmarkRunReport.from_dict(load_json(path))


def load_benchmark_suite(manifest_path: Path) -> BenchmarkSuiteBundle:
    manifest_path = manifest_path.expanduser().resolve()
    manifest = BenchmarkSuiteManifest.from_dict(load_json(manifest_path))
    root_dir = manifest_path.parent
    screens: list[BenchmarkScreenBundle] = []
    for entry in manifest.screens:
        reference_image_path = resolve_relative_path(root_dir, entry.reference_image)
        retrieval_fixture_path = resolve_relative_path(root_dir, entry.retrieval_fixture)
        screen_fixture_path = resolve_relative_path(root_dir, entry.screen_fixture)
        thresholds_path = resolve_relative_path(root_dir, entry.thresholds)
        retrieval_fixture = load_retrieval_fixture(retrieval_fixture_path)
        screen_fixture = load_screen_fixture(screen_fixture_path)
        thresholds = load_thresholds(thresholds_path)
        if retrieval_fixture.screen_name != entry.screen_name:
            raise BenchmarkFixtureError(
                f"Retrieval fixture screenName '{retrieval_fixture.screen_name}' does not match manifest screenName '{entry.screen_name}'."
            )
        if screen_fixture.screen_name != entry.screen_name:
            raise BenchmarkFixtureError(
                f"Screen fixture screenName '{screen_fixture.screen_name}' does not match manifest screenName '{entry.screen_name}'."
            )
        screens.append(
            BenchmarkScreenBundle(
                entry=entry,
                reference_image_path=reference_image_path,
                retrieval_fixture_path=retrieval_fixture_path,
                screen_fixture_path=screen_fixture_path,
                thresholds_path=thresholds_path,
                retrieval_fixture=retrieval_fixture,
                screen_fixture=screen_fixture,
                thresholds=thresholds,
            )
        )
    return BenchmarkSuiteBundle(manifest_path=manifest_path, manifest=manifest, screens=tuple(screens))
