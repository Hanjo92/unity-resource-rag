from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.gateway.capabilities.text_embedding import CAPABILITY_NAME, run_text_embedding


class GatewayTextEmbeddingTests(unittest.TestCase):
    def test_run_text_embedding_returns_token_frequency_output(self) -> None:
        result = run_text_embedding(
            {
                "capability": CAPABILITY_NAME,
                "providerPreference": ["gateway:auto"],
                "input": {
                    "texts": [
                        "gold trimmed reward popup frame",
                        "reward popup frame",
                    ]
                },
                "outputSchema": "text_embedding_v1",
                "options": {
                    "detail": "high",
                    "timeoutMs": 30000,
                },
            }
        )

        self.assertEqual(result["adapterId"], "local_text_embedding")
        self.assertEqual(result["authMode"], "none")
        self.assertEqual(result["providerFamily"], "local_retrieval")
        self.assertEqual(result["output"]["scheme"], "token-frequency-v1")
        self.assertEqual(len(result["output"]["items"]), 2)
        self.assertIn("reward", result["output"]["items"][0]["tokenWeights"])
        self.assertGreater(result["usage"]["totalTokens"], 0)


if __name__ == "__main__":
    unittest.main()
