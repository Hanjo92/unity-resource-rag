from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.retrieval.embedding_bridge import (
    EmbeddingBridgeError,
    normalize_gateway_sparse_embedding_response,
    score_gateway_embedding_response,
    normalize_gateway_text_embedding_response,
    score_gateway_text_embedding_response,
    score_query_against_index_with_optional_gateway_embedding,
)
from pipeline.retrieval.vector_index import build_tfidf_index, score_query_against_index


def _vector_index() -> dict[str, object]:
    records = [
        {
            "id": "reward-popup-frame",
            "name": "RewardPopupFrame",
            "path": "Assets/UI/Popup/RewardPopupFrame.png",
            "assetType": "sprite",
            "semanticText": "gold popup frame reward unlock",
        },
        {
            "id": "inventory-panel-frame",
            "name": "InventoryPanelFrame",
            "path": "Assets/UI/Inventory/InventoryPanel.prefab",
            "assetType": "prefab",
            "semanticText": "inventory panel tabs grid frame",
        },
    ]
    return build_tfidf_index(records)


def _image_vector_index() -> dict[str, object]:
    return {
        "scheme": "visual-token-sparse-v1",
        "documents": [
            {
                "id": "reward-preview",
                "vector": {
                    "orientation_landscape": 0.4,
                    "palette_warm": 0.35,
                    "cell_1_1_bright": 0.25,
                },
            },
            {
                "id": "inventory-preview",
                "vector": {
                    "orientation_landscape": 0.3,
                    "palette_cool": 0.4,
                    "cell_1_1_dark": 0.3,
                },
            },
        ],
    }


class RetrievalEmbeddingBridgeTests(unittest.TestCase):
    def test_normalize_gateway_text_embedding_response_accepts_sparse_mapping(self) -> None:
        response = {
            "status": "ok",
            "capability": "text_embedding",
            "output": {
                "embedding": {
                    "reward": 0.9,
                    "popup": 0.8,
                    "frame": 0.7,
                    "inventory": 0.0,
                }
            },
        }

        embedding = normalize_gateway_text_embedding_response(response)

        self.assertEqual(
            embedding,
            {
                "reward": 0.9,
                "popup": 0.8,
                "frame": 0.7,
            },
        )

    def test_score_gateway_text_embedding_response_scores_sparse_index(self) -> None:
        vector_index = _vector_index()
        response = {
            "status": "ok",
            "capability": "text_embedding",
            "output": {
                "embedding": {
                    "reward": 0.95,
                    "popup": 0.85,
                    "frame": 0.75,
                }
            },
        }

        scores = score_gateway_text_embedding_response(response, vector_index)

        self.assertIn("reward-popup-frame", scores)
        self.assertGreater(scores["reward-popup-frame"], 0.0)
        self.assertGreater(scores["reward-popup-frame"], scores["inventory-panel-frame"])

    def test_score_gateway_text_embedding_response_accepts_capability_item_shape(self) -> None:
        vector_index = _vector_index()
        response = {
            "status": "ok",
            "capability": "text_embedding",
            "output": {
                "scheme": "token-frequency-v1",
                "items": [
                    {
                        "index": 0,
                        "text": "reward popup frame",
                        "tokenWeights": {
                            "reward": 0.4,
                            "popup": 0.3,
                            "frame": 0.3,
                        },
                    }
                ],
            },
        }

        scores = score_gateway_text_embedding_response(response, vector_index)

        self.assertGreater(scores["reward-popup-frame"], scores["inventory-panel-frame"])

    def test_generic_embedding_helpers_accept_image_embedding_preview_shape(self) -> None:
        vector_index = _image_vector_index()
        response = {
            "status": "ok",
            "capability": "image_embedding",
            "output": {
                "scheme": "visual-token-sparse-v1",
                "preview": True,
                "items": [
                    {
                        "index": 0,
                        "tokenWeights": {
                            "orientation_landscape": 0.4,
                            "palette_warm": 0.35,
                            "cell_1_1_bright": 0.25,
                        },
                    }
                ],
            },
        }

        embedding = normalize_gateway_sparse_embedding_response(response)
        scores = score_gateway_embedding_response(response, vector_index)

        self.assertIn("palette_warm", embedding)
        self.assertGreater(scores["reward-preview"], scores["inventory-preview"])

    def test_optional_gateway_embedding_falls_back_to_baseline(self) -> None:
        vector_index = _vector_index()
        query_text = "inventory panel frame"

        baseline_scores = score_query_against_index(query_text, vector_index)
        bridge_scores = score_query_against_index_with_optional_gateway_embedding(query_text, vector_index)

        self.assertEqual(bridge_scores, baseline_scores)

    def test_dense_embedding_without_token_labels_fails_fast(self) -> None:
        response = {
            "status": "ok",
            "capability": "text_embedding",
            "output": {
                "embedding": [0.9, 0.8, 0.7],
            },
        }

        with self.assertRaises(EmbeddingBridgeError):
            normalize_gateway_text_embedding_response(response)


if __name__ == "__main__":
    unittest.main()
