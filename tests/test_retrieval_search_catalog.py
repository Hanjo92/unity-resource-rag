from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.retrieval.search_catalog import Query, search
from pipeline.retrieval.vector_index import build_tfidf_index, score_query_against_index


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


def _texture_record() -> dict[str, object]:
    return {
        "id": "reward_frame_texture",
        "guid": "texture-guid",
        "localFileId": 21300002,
        "name": "RewardFrame",
        "path": "Assets/UI/RewardFrame.png",
        "subAssetName": "RewardFrame",
        "assetType": "Sprite",
        "binding": {
            "kind": "sprite",
            "unityLoadPath": "Assets/UI/RewardFrame.png",
            "subAssetName": "RewardFrame",
            "localFileId": 21300002,
        },
        "semanticText": "reward popup frame background texture",
        "metadataTokens": [
            "texture_backed",
            "alpha_transparency",
            "clamp",
            "bilinear",
            "ui",
            "sprite",
        ],
        "uiHints": {
            "isNineSliceCandidate": True,
            "isSingleImageRegion": True,
            "isTextureBacked": True,
            "prefersPreserveAspect": False,
            "hasTransparency": True,
            "preferredUse": ["popup_frame"],
            "componentRoles": [],
        },
        "assetProvenance": {
            "mainAssetPath": "Assets/UI/RewardFrame.png",
            "mainAssetName": "RewardFrameTexture",
            "mainAssetType": "Texture2D",
            "importerType": "TextureImporter",
        },
        "textureSummary": {
            "sourceTexturePath": "Assets/UI/RewardFrame.png",
            "sourceTextureName": "RewardFrameTexture",
            "sourceTextureAssetType": "Texture2D",
            "textureImporterType": "Sprite",
            "spriteImportMode": "Single",
            "textureFormat": "RGBA32",
            "wrapMode": "Clamp",
            "filterMode": "Bilinear",
            "hasAlpha": True,
            "alphaIsTransparency": True,
            "sRgbTexture": True,
            "mipmapEnabled": False,
            "isReadable": False,
            "pixelsPerUnit": 100.0,
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

    def test_vector_index_documents_keep_texture_metadata_for_reuse(self) -> None:
        vector_index = build_tfidf_index([_texture_record()])

        document = vector_index["documents"][0]

        self.assertIn("texture_backed", document["metadataTokens"])
        self.assertEqual(document["assetProvenance"]["mainAssetType"], "Texture2D")
        self.assertEqual(document["textureSummary"]["sourceTextureName"], "RewardFrameTexture")

    def test_vector_index_uses_metadata_tokens_for_texture_matching(self) -> None:
        vector_index = build_tfidf_index([_prefab_record(), _texture_record()])

        scores = score_query_against_index("transparent popup texture clamp", vector_index)

        self.assertGreater(scores["reward_frame_texture"], scores.get("inventory_panel", 0.0))

    def test_search_results_keep_texture_metadata_for_review(self) -> None:
        results = search(
            Query(
                query_text="reward popup texture",
                region_type="popup_frame",
                preferred_kind="sprite",
                aspect_ratio=None,
                top_k=1,
            ),
            [_texture_record()],
            {"reward_frame_texture": 1.0},
        )

        self.assertEqual(results[0]["textureSummary"]["sourceTextureName"], "RewardFrameTexture")
        self.assertEqual(results[0]["assetProvenance"]["mainAssetType"], "Texture2D")
        self.assertTrue(results[0]["uiHints"]["isTextureBacked"])


if __name__ == "__main__":
    unittest.main()
