from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pipeline.retrieval.vector_index import tokenize

from ..models import GatewayRequestEnvelope, GatewayRunOptions
from ..router import GatewayCapabilityRouter


CAPABILITY_NAME = "text_embedding"
ADAPTER_ID = "local_text_embedding"
PROVIDER_FAMILY = "local_retrieval"


class TextEmbeddingInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    texts: list[str] = Field(min_length=1)


class TextEmbeddingRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    capability: str = CAPABILITY_NAME
    providerPreference: list[str] = Field(default_factory=list)
    input: TextEmbeddingInput
    outputSchema: str
    options: GatewayRunOptions = Field(default_factory=GatewayRunOptions)


def _normalize_request(request: GatewayRequestEnvelope | dict[str, Any]) -> TextEmbeddingRequest:
    if isinstance(request, dict):
        return TextEmbeddingRequest.model_validate(request)
    return TextEmbeddingRequest.model_validate(
        {
            "capability": request.capability,
            "providerPreference": request.providerPreference,
            "input": request.input,
            "outputSchema": request.outputSchema,
            "options": request.options.model_dump(mode="python"),
        }
    )


def _token_weights(text: str) -> tuple[dict[str, float], int]:
    tokens = tokenize(text)
    if not tokens:
        return {}, 0
    counts = Counter(tokens)
    total = sum(counts.values())
    weights = {
        token: round(count / total, 6)
        for token, count in sorted(counts.items())
    }
    return weights, total


def run_text_embedding(request: GatewayRequestEnvelope | dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_request(request)
    items: list[dict[str, Any]] = []
    total_tokens = 0

    for index, text in enumerate(normalized.input.texts):
        weights, token_count = _token_weights(text)
        total_tokens += token_count
        items.append(
            {
                "index": index,
                "text": text,
                "tokenWeights": weights,
                "tokenCount": token_count,
            }
        )

    return {
        "adapterId": ADAPTER_ID,
        "authMode": "none",
        "providerFamily": PROVIDER_FAMILY,
        "output": {
            "scheme": "token-frequency-v1",
            "embedding": items[0]["tokenWeights"] if len(items) == 1 else None,
            "items": items,
        },
        "usage": {
            "inputTexts": len(items),
            "totalTokens": total_tokens,
        },
        "trace": {
            "capability": CAPABILITY_NAME,
            "outputSchema": normalized.outputSchema,
        },
    }


def handle(request: GatewayRequestEnvelope) -> dict[str, Any]:
    return run_text_embedding(request)


def register(router: GatewayCapabilityRouter) -> None:
    router.register(
        CAPABILITY_NAME,
        handle,
        adapter_id=ADAPTER_ID,
    )
