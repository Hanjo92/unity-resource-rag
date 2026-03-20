from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

try:
    from pipeline.retrieval.vector_index import cosine_similarity_sparse, score_query_against_index
except ImportError:  # pragma: no cover - script execution fallback
    from vector_index import cosine_similarity_sparse, score_query_against_index


class EmbeddingBridgeError(ValueError):
    """Raised when an embedding response cannot be normalized for the current sparse index flow."""


RESPONSE_CONTAINER_KEYS = ("output", "result", "data")
EMBEDDING_VECTOR_KEYS = ("embedding", "vector", "values", "weights")
EMBEDDING_TOKEN_KEYS = ("tokens", "terms", "dimensions")
EMBEDDING_VALUE_KEYS = ("weights", "values", "scores")


def _coerce_number(value: Any, *, key: str) -> float:
    if not isinstance(value, (int, float)):
        raise EmbeddingBridgeError(f"Expected a numeric value for '{key}'.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise EmbeddingBridgeError(f"Expected a finite numeric value for '{key}'.")
    return numeric


def _normalize_sparse_mapping(mapping: Mapping[str, Any]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for key, value in mapping.items():
        if not isinstance(key, str) or not key:
            continue
        numeric = _coerce_number(value, key=key)
        if numeric > 0.0:
            normalized[key] = round(numeric, 6)
    if not normalized:
        raise EmbeddingBridgeError("Embedding response did not contain any usable sparse dimensions.")
    return normalized


def _normalize_labeled_sequence(items: list[Any]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for item in items:
        if isinstance(item, Mapping):
            key = None
            for candidate in ("token", "term", "dimension", "name", "key"):
                value = item.get(candidate)
                if isinstance(value, str) and value:
                    key = value
                    break
            if key is None:
                continue
            numeric_value = None
            for candidate in EMBEDDING_VALUE_KEYS:
                value = item.get(candidate)
                if isinstance(value, (int, float)):
                    numeric_value = float(value)
                    break
            if numeric_value is None:
                continue
            if math.isfinite(numeric_value) and numeric_value > 0.0:
                normalized[key] = round(numeric_value, 6)
            continue

        if isinstance(item, (list, tuple)) and len(item) == 2:
            key, value = item
            if isinstance(key, str) and key:
                numeric_value = _coerce_number(value, key=key)
                if numeric_value > 0.0:
                    normalized[key] = round(numeric_value, 6)

    if not normalized:
        raise EmbeddingBridgeError("Embedding response did not contain labeled sparse values.")
    return normalized


def _normalize_dense_sequence(values: list[Any], tokens: list[str] | None) -> dict[str, float]:
    if tokens is None:
        raise EmbeddingBridgeError(
            "Dense embedding responses need a token list or dimension labels to align with the sparse index."
        )
    if len(tokens) != len(values):
        raise EmbeddingBridgeError("Dense embedding values and tokens must have the same length.")

    normalized: dict[str, float] = {}
    for token, value in zip(tokens, values, strict=True):
        if not isinstance(token, str) or not token:
            continue
        numeric = _coerce_number(value, key=token)
        if numeric > 0.0:
            normalized[token] = round(numeric, 6)

    if not normalized:
        raise EmbeddingBridgeError("Dense embedding response did not contain any positive values.")
    return normalized


def _extract_embedding_payload(response: Mapping[str, Any]) -> Any:
    candidates: list[Any] = [response]
    for key in RESPONSE_CONTAINER_KEYS:
        value = response.get(key)
        if value is not None:
            candidates.append(value)

    for candidate in candidates:
        if isinstance(candidate, list) and candidate:
            first = candidate[0]
            if isinstance(first, Mapping):
                nested = first.get("embedding") or first.get("vector") or first.get("values")
                if nested is not None:
                    return {"container": first, "embedding": nested}
            return candidate

        if not isinstance(candidate, Mapping):
            continue

        items = candidate.get("items")
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, Mapping):
                token_weights = first.get("tokenWeights") or first.get("embedding")
                if token_weights is not None:
                    return {"container": first, "embedding": token_weights}

        for key in EMBEDDING_VECTOR_KEYS:
            value = candidate.get(key)
            if value is not None:
                return {"container": candidate, "embedding": value}

    raise EmbeddingBridgeError("Could not find an embedding payload in the gateway response.")


def normalize_gateway_text_embedding_response(response: Mapping[str, Any]) -> dict[str, float]:
    if not isinstance(response, Mapping):
        raise EmbeddingBridgeError("Gateway embedding response must be a mapping.")

    payload = _extract_embedding_payload(response)
    container: Mapping[str, Any]

    if isinstance(payload, Mapping) and "container" in payload and "embedding" in payload:
        container = payload["container"]
        embedding = payload["embedding"]
    else:
        container = response
        embedding = payload

    if isinstance(embedding, Mapping):
        return _normalize_sparse_mapping(embedding)

    if isinstance(embedding, list):
        if not embedding:
            raise EmbeddingBridgeError("Embedding response contained an empty vector.")

        tokens: list[str] | None = None
        for token_key in EMBEDDING_TOKEN_KEYS:
            candidate_tokens = container.get(token_key)
            if isinstance(candidate_tokens, list) and all(isinstance(item, str) and item for item in candidate_tokens):
                tokens = candidate_tokens
                break

        if all(isinstance(item, (int, float)) for item in embedding):
            return _normalize_dense_sequence(embedding, tokens)

        if any(isinstance(item, Mapping) for item in embedding) or any(
            isinstance(item, (list, tuple)) and len(item) == 2 for item in embedding
        ):
            return _normalize_labeled_sequence(embedding)

    raise EmbeddingBridgeError("Unsupported embedding payload shape for the current sparse retrieval index.")


def score_embedding_vector_against_index(
    embedding_vector: Mapping[str, Any],
    vector_index: Mapping[str, Any],
) -> dict[str, float]:
    sparse_embedding = _normalize_sparse_mapping(embedding_vector)
    scores: dict[str, float] = {}
    for document in vector_index.get("documents") or []:
        if not isinstance(document, Mapping):
            continue
        document_id = document.get("id")
        document_vector = document.get("vector") or {}
        if not isinstance(document_id, str) or not document_id or not isinstance(document_vector, Mapping):
            continue
        score = cosine_similarity_sparse(sparse_embedding, document_vector)  # type: ignore[arg-type]
        if score > 0.0:
            scores[document_id] = round(score, 4)
    return scores


def score_gateway_text_embedding_response(
    response: Mapping[str, Any],
    vector_index: Mapping[str, Any],
) -> dict[str, float]:
    embedding_vector = normalize_gateway_text_embedding_response(response)
    return score_embedding_vector_against_index(embedding_vector, vector_index)


def score_query_against_index_with_optional_gateway_embedding(
    query_text: str,
    vector_index: Mapping[str, Any],
    gateway_embedding_response: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    if gateway_embedding_response is None:
        return score_query_against_index(query_text, vector_index)
    return score_gateway_text_embedding_response(gateway_embedding_response, vector_index)
