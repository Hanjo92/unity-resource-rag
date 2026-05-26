from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.retrieval.search_catalog import Query, search
from pipeline.retrieval.vector_index import build_tfidf_index


def _prefab_record() -> dict[str, object]:
    return {
        "id": "inventory_panel",
        "guid": "prefab-guid",
        "localFileId": 100100,
        "name": "PF_InventoryPanel",
        "path": "Assets/UI/PF_InventoryPanel.prefab",
        "assetType": "Prefab",
        "binding": {"kind": "prefab", "unityLoadPath": "Assets/UI/PF_InventoryPanel.prefab"},
        "semanticText": "inventory list panel shell reusable prefab",
        "preview": {
            "path": "Library/ResourceRag/previews/prefab-guid_100100.png",
            "width": 256,
            "height": 128,
        },
        "embeddingRefs": {
            "imageEmbeddingId": "inventory_panel_preview",
            "textEmbeddingId": "inventory_panel",
        },
        "prefabSummary": {
            "rootName": "PF_InventoryPanel",
            "componentTypes": ["RectTransform", "VerticalLayoutGroup"],
            "childPaths": ["PF_InventoryPanel", "PF_InventoryPanel/Rows"],
        },
    }


class RetrievalSearchCatalogTests(unittest.TestCase):
    def test_vector_index_documents_keep_prefab_preview_references(self) -> None:
        vector_index = build_tfidf_index([_prefab_record()])

        document = vector_index["documents"][0]

        self.assertEqual(document["imageEmbeddingId"], "inventory_panel_preview")
        self.assertEqual(document["preview"]["path"], "Library/ResourceRag/previews/prefab-guid_100100.png")

    def test_search_results_keep_prefab_preview_metadata_for_reuse(self) -> None:
        record = _prefab_record()

        results = search(
            Query(
                query_text="inventory reusable panel",
                region_type="inventory",
                preferred_kind="prefab",
                aspect_ratio=None,
                top_k=1,
            ),
            [record],
            {"inventory_panel": 1.0},
        )

        self.assertEqual(results[0]["preview"]["path"], "Library/ResourceRag/previews/prefab-guid_100100.png")
        self.assertEqual(results[0]["embeddingRefs"]["imageEmbeddingId"], "inventory_panel_preview")
        self.assertEqual(results[0]["prefabSummary"]["rootName"], "PF_InventoryPanel")


if __name__ == "__main__":
    unittest.main()
