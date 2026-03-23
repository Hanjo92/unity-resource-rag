from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


BUNDLE_MANIFEST_NAME = "unity-resource-rag-sidecar.json"
PACKAGE_JSON_PATH = Path("Packages/com.hanjo92.unity-resource-rag/package.json")
TOP_LEVEL_FILES = ("requirements.txt", "LICENSE")
TOP_LEVEL_DIRS = ("pipeline",)
SKIP_DIR_NAMES = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


@dataclass(frozen=True)
class BundleBuildResult:
    repo_root: Path
    bundle_root: Path
    version: str
    files_copied: int


def _read_package_version(repo_root: Path) -> str:
    package_json = repo_root / PACKAGE_JSON_PATH
    payload = json.loads(package_json.read_text(encoding="utf-8"))
    version = str(payload.get("version") or "").strip()
    if not version:
        raise ValueError(f"Could not read a package version from {package_json}")
    return version


def _validate_repo_root(repo_root: Path) -> None:
    required_paths = [
        repo_root / "requirements.txt",
        repo_root / "pipeline" / "mcp" / "server.py",
        repo_root / "pipeline" / "mcp" / "local_runner.py",
        repo_root / PACKAGE_JSON_PATH,
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        raise ValueError("The repo root is missing required sidecar files:\n- " + "\n- ".join(missing))


def _should_skip(path: Path) -> bool:
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return True
    if path.suffix in SKIP_SUFFIXES:
        return True
    return False


def _copy_file(source: Path, target: Path) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return 1


def _copy_tree(source_root: Path, target_root: Path) -> int:
    copied = 0
    for path in sorted(source_root.rglob("*")):
        relative_path = path.relative_to(source_root)
        if _should_skip(relative_path):
            continue
        target_path = target_root / relative_path
        if path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue
        copied += _copy_file(path, target_path)
    return copied


def _write_manifest(bundle_root: Path, version: str) -> int:
    manifest_path = bundle_root / BUNDLE_MANIFEST_NAME
    manifest = {
        "kind": "unity-resource-rag-sidecar",
        "version": version,
        "entrypoints": {
            "mcpServerModule": "pipeline.mcp",
            "localRunnerModule": "pipeline.mcp.local_runner",
        },
        "expectedRuntimeLayout": {
            "requirements": "requirements.txt",
            "pipelineRoot": "pipeline",
            "venvDirectory": ".venv",
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 1


def build_sidecar_bundle(repo_root: Path, output_dir: Path, version: str | None = None) -> BundleBuildResult:
    repo_root = repo_root.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    _validate_repo_root(repo_root)

    resolved_version = version or _read_package_version(repo_root)
    bundle_root = output_dir / f"unity-resource-rag-sidecar-{resolved_version}"
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True, exist_ok=True)

    files_copied = 0
    for relative_file in TOP_LEVEL_FILES:
        source = repo_root / relative_file
        files_copied += _copy_file(source, bundle_root / relative_file)

    for relative_dir in TOP_LEVEL_DIRS:
        source_dir = repo_root / relative_dir
        files_copied += _copy_tree(source_dir, bundle_root / relative_dir)

    files_copied += _write_manifest(bundle_root, resolved_version)
    return BundleBuildResult(
        repo_root=repo_root,
        bundle_root=bundle_root,
        version=resolved_version,
        files_copied=files_copied,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a portable unity-resource-rag sidecar bundle for non-dev distribution."
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Path to the unity-resource-rag repository root.",
    )
    parser.add_argument(
        "--output-dir",
        default="dist",
        help="Directory where the portable sidecar bundle should be written.",
    )
    parser.add_argument(
        "--version",
        help="Override the bundle version. Defaults to the UPM package version.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = build_sidecar_bundle(Path(args.repo_root), Path(args.output_dir), args.version)
    print(
        json.dumps(
            {
                "bundleRoot": str(result.bundle_root),
                "version": result.version,
                "filesCopied": result.files_copied,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
