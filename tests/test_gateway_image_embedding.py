from __future__ import annotations

import base64
import unittest

from pipeline.gateway.capabilities.image_embedding import CAPABILITY_NAME, PREVIEW_SCHEME, run_image_embedding


def _portable_pixmap_data_url(body: str) -> str:
    encoded = base64.b64encode(body.encode("ascii")).decode("ascii")
    return f"data:image/x-portable-pixmap;base64,{encoded}"


class GatewayImageEmbeddingTests(unittest.TestCase):
    def test_run_image_embedding_returns_preview_sparse_tokens(self) -> None:
        image_data_url = _portable_pixmap_data_url(
            "\n".join(
                [
                    "P3",
                    "3 2",
                    "255",
                    "255 0 0   255 0 0   255 0 0",
                    "24 24 24  24 24 24  255 255 255",
                ]
            )
        )
        result = run_image_embedding(
            {
                "capability": CAPABILITY_NAME,
                "input": {
                    "images": [
                        {
                            "label": "reward_preview",
                            "imageDataUrl": image_data_url,
                        }
                    ]
                },
                "outputSchema": "image_embedding_v1",
            }
        )

        self.assertEqual(result["adapterId"], "local_image_embedding_preview")
        self.assertEqual(result["providerFamily"], "local_retrieval")
        self.assertEqual(result["output"]["scheme"], PREVIEW_SCHEME)
        self.assertTrue(result["output"]["preview"])
        self.assertEqual(result["output"]["items"][0]["width"], 3)
        self.assertEqual(result["output"]["items"][0]["height"], 2)
        self.assertIn("orientation_landscape", result["output"]["embedding"])
        self.assertIn("palette_warm", result["output"]["embedding"])

    def test_run_image_embedding_accepts_precomputed_visual_tokens(self) -> None:
        result = run_image_embedding(
            {
                "capability": CAPABILITY_NAME,
                "input": {
                    "images": [
                        {
                            "label": "slot_grid",
                            "visualTokens": [
                                "orientation_landscape",
                                "palette_cool",
                                "cell_1_1_bright",
                                "cell_1_1_bright",
                            ],
                        }
                    ]
                },
                "outputSchema": "image_embedding_v1",
            }
        )

        embedding = result["output"]["embedding"]
        self.assertEqual(result["output"]["items"][0]["sourceType"], "visual_tokens")
        self.assertEqual(result["output"]["items"][0]["tokenCount"], 4)
        self.assertEqual(embedding["cell_1_1_bright"], 0.5)
        self.assertEqual(embedding["orientation_landscape"], 0.25)


if __name__ == "__main__":
    unittest.main()
