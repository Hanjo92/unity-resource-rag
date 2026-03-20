from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RETRIEVAL_DIR = REPO_ROOT / "pipeline" / "retrieval"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(RETRIEVAL_DIR) not in sys.path:
    sys.path.insert(0, str(RETRIEVAL_DIR))

import bind_blueprint_assets as binder
from vector_index import build_tfidf_index


def _vector_index() -> dict[str, object]:
    records = [
        {
            "id": "hero_frame",
            "name": "HeroFrame",
            "path": "Assets/UI/HeroFrame.png",
            "assetType": "sprite",
            "binding": {"kind": "sprite"},
            "semanticText": "hero popup frame gold blue",
        },
        {
            "id": "inventory_panel",
            "name": "InventoryPanel",
            "path": "Assets/UI/InventoryPanel.prefab",
            "assetType": "prefab",
            "binding": {"kind": "prefab"},
            "semanticText": "inventory panel grid tabs",
        },
    ]
    return build_tfidf_index(records)


def _blueprint(query_key: str, query: dict[str, object]) -> dict[str, object]:
    return {
        "screenName": "TestScreen",
        "root": {
            "id": "root",
            "name": "Root",
            "children": [
                {
                    "id": "binding-node",
                    "name": "BindingNode",
                    query_key: query,
                }
            ],
        },
    }


class BindBlueprintAssetsTests(unittest.TestCase):
    def test_hold_policy_preserves_query_and_candidate(self) -> None:
        resolved, report, has_errors = binder.bind_blueprint(
            _blueprint(
                "assetQuery",
                {
                    "queryText": "hero popup frame",
                    "bindingPolicy": "hold_if_uncertain",
                    "minScore": 1.1,
                },
            ),
            [
                {
                    "id": "hero_frame",
                    "name": "HeroFrame",
                    "path": "Assets/UI/HeroFrame.png",
                    "assetType": "sprite",
                    "binding": {"kind": "sprite"},
                    "semanticText": "hero popup frame gold blue",
                },
                {
                    "id": "inventory_panel",
                    "name": "InventoryPanel",
                    "path": "Assets/UI/InventoryPanel.prefab",
                    "assetType": "prefab",
                    "binding": {"kind": "prefab"},
                    "semanticText": "inventory panel grid tabs",
                },
            ],
            _vector_index(),
            allow_partial=True,
        )

        node = resolved["root"]["children"][0]
        entry = report["bindings"][0]

        self.assertFalse(has_errors)
        self.assertEqual(report["summary"]["bindingStates"], {"auto_bind": 0, "hold": 1, "review_needed": 0})
        self.assertEqual(report["issues"], [])
        self.assertIn("assetQuery", node)
        self.assertNotIn("asset", node)
        self.assertEqual(entry["bindingState"], "hold")
        self.assertIsNotNone(entry["chosenCandidate"])
        self.assertIsNone(entry["appliedCandidate"])
        self.assertGreater(len(entry["alternatives"]), 0)

    def test_require_confident_low_score_marks_review_needed(self) -> None:
        resolved, report, has_errors = binder.bind_blueprint(
            _blueprint(
                "text",
                {
                    "value": "Hero",
                    "fontAssetQuery": {
                        "queryText": "hero popup frame",
                        "bindingPolicy": "require_confident",
                        "minScore": 1.1,
                    },
                },
            ),
            [
                {
                    "id": "hero_frame",
                    "name": "HeroFrame",
                    "path": "Assets/UI/HeroFrame.png",
                    "assetType": "sprite",
                    "binding": {"kind": "sprite"},
                    "semanticText": "hero popup frame gold blue",
                },
                {
                    "id": "inventory_panel",
                    "name": "InventoryPanel",
                    "path": "Assets/UI/InventoryPanel.prefab",
                    "assetType": "prefab",
                    "binding": {"kind": "prefab"},
                    "semanticText": "inventory panel grid tabs",
                },
            ],
            _vector_index(),
            allow_partial=False,
        )

        text = resolved["root"]["children"][0]["text"]
        entry = report["bindings"][0]

        self.assertTrue(has_errors)
        self.assertEqual(report["summary"]["bindingStates"], {"auto_bind": 0, "hold": 0, "review_needed": 1})
        self.assertEqual(len(report["issues"]), 1)
        self.assertIn("fontAssetQuery", text)
        self.assertNotIn("fontAsset", text)
        self.assertEqual(entry["bindingState"], "review_needed")
        self.assertIsNotNone(entry["chosenCandidate"])
        self.assertIsNone(entry["appliedCandidate"])
        self.assertIn("low_confidence_review", entry["bindingDecision"])

    def test_best_match_still_auto_binds(self) -> None:
        resolved, report, has_errors = binder.bind_blueprint(
            _blueprint(
                "assetQuery",
                {
                    "queryText": "hero popup frame",
                    "bindingPolicy": "best_match",
                    "minScore": 1.1,
                },
            ),
            [
                {
                    "id": "hero_frame",
                    "name": "HeroFrame",
                    "path": "Assets/UI/HeroFrame.png",
                    "assetType": "sprite",
                    "binding": {"kind": "sprite"},
                    "semanticText": "hero popup frame gold blue",
                },
                {
                    "id": "inventory_panel",
                    "name": "InventoryPanel",
                    "path": "Assets/UI/InventoryPanel.prefab",
                    "assetType": "prefab",
                    "binding": {"kind": "prefab"},
                    "semanticText": "inventory panel grid tabs",
                },
            ],
            _vector_index(),
            allow_partial=True,
        )

        node = resolved["root"]["children"][0]
        entry = report["bindings"][0]

        self.assertFalse(has_errors)
        self.assertEqual(report["summary"]["bindingStates"], {"auto_bind": 1, "hold": 0, "review_needed": 0})
        self.assertEqual(report["issues"], [])
        self.assertNotIn("assetQuery", node)
        self.assertIn("asset", node)
        self.assertEqual(node["asset"]["path"], "Assets/UI/HeroFrame.png")
        self.assertEqual(entry["bindingState"], "auto_bind")
        self.assertIsNotNone(entry["appliedCandidate"])


if __name__ == "__main__":
    unittest.main()
