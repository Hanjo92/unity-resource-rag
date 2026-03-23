from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_sidecar_bundle.py"
spec = importlib.util.spec_from_file_location("build_sidecar_bundle", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class BuildSidecarBundleTests(unittest.TestCase):
    def test_build_sidecar_bundle_copies_required_runtime_surface(self) -> None:
        with tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as out_dir:
            repo_root = Path(repo_dir)
            (repo_root / "requirements.txt").write_text("pydantic>=2.7\n", encoding="utf-8")
            (repo_root / "LICENSE").write_text("MIT\n", encoding="utf-8")
            (repo_root / "Packages" / "com.hanjo92.unity-resource-rag").mkdir(parents=True)
            (repo_root / "Packages" / "com.hanjo92.unity-resource-rag" / "package.json").write_text(
                json.dumps({"version": "0.6.0-dev"}),
                encoding="utf-8",
            )
            (repo_root / "pipeline" / "mcp").mkdir(parents=True)
            (repo_root / "pipeline" / "__pycache__").mkdir(parents=True)
            (repo_root / "pipeline" / "__init__.py").write_text("", encoding="utf-8")
            (repo_root / "pipeline" / "mcp" / "__init__.py").write_text("", encoding="utf-8")
            (repo_root / "pipeline" / "mcp" / "server.py").write_text("print('server')\n", encoding="utf-8")
            (repo_root / "pipeline" / "mcp" / "local_runner.py").write_text("print('runner')\n", encoding="utf-8")
            (repo_root / "pipeline" / "__pycache__" / "junk.pyc").write_bytes(b"compiled")

            result = module.build_sidecar_bundle(repo_root, Path(out_dir))

            bundle_root = result.bundle_root
            self.assertEqual(result.version, "0.6.0-dev")
            self.assertTrue((bundle_root / "requirements.txt").exists())
            self.assertTrue((bundle_root / "LICENSE").exists())
            self.assertTrue((bundle_root / "pipeline" / "mcp" / "server.py").exists())
            self.assertTrue((bundle_root / "pipeline" / "mcp" / "local_runner.py").exists())
            self.assertFalse((bundle_root / "pipeline" / "__pycache__").exists())

            manifest = json.loads((bundle_root / module.BUNDLE_MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertEqual(manifest["kind"], "unity-resource-rag-sidecar")
            self.assertEqual(manifest["version"], "0.6.0-dev")


if __name__ == "__main__":
    unittest.main()
