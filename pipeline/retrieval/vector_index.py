#!/usr/bin/env python3
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def tokenize(text: str | None) -> list[str]:
    if not text:
        return []
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text)]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def compose_record_text(record: dict[str, Any]) -> str:
    parts: list[str] = []

    def append(value: str | None, repeat: int = 1) -> None:
        if not value:
            return
        for _ in range(max(1, repeat)):
            parts.append(value)

    append(record.get("semanticText"), repeat=2)
    append(record.get("name"), repeat=2)
    append(record.get("path"))

    labels = record.get("labels") or []
    if labels:
        append(" ".join(labels))

    folder_tokens = record.get("folderTokens") or []
    if folder_tokens:
        append(" ".join(folder_tokens))

    ui_hints = record.get("uiHints") or {}
    preferred_use = ui_hints.get("preferredUse") or []
    if preferred_use:
        append(" ".join(preferred_use))

    prefab_summary = record.get("prefabSummary") or {}
    append(prefab_summary.get("rootName"))

    component_types = prefab_summary.get("componentTypes") or []
    if component_types:
        append(" ".join(component_types))

    child_paths = prefab_summary.get("childPaths") or []
    if child_paths:
        append(" ".join(child_paths[:20]))

    return " ".join(parts)


def build_sparse_tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    if not tokens:
        return {}

    counts = Counter(tokens)
    total = float(sum(counts.values()))
    if total <= 0.0:
        return {}

    weights = {
        token: (count / total) * idf[token]
        for token, count in counts.items()
        if token in idf
    }
    return normalize_sparse_vector(weights)


def normalize_sparse_vector(weights: dict[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(value * value for value in weights.values()))
    if norm <= 0.0:
        return {}
    return {
        token: round(value / norm, 6)
        for token, value in weights.items()
        if value > 0.0
    }


def build_tfidf_index(records: list[dict[str, Any]]) -> dict[str, Any]:
    document_tokens: list[list[str]] = []
    document_frequency: Counter[str] = Counter()

    for record in records:
        tokens = tokenize(compose_record_text(record))
        document_tokens.append(tokens)
        document_frequency.update(set(tokens))

    document_count = len(records)
    idf = {
        token: round(math.log((1.0 + document_count) / (1.0 + frequency)) + 1.0, 6)
        for token, frequency in sorted(document_frequency.items())
    }

    documents: list[dict[str, Any]] = []
    for record, tokens in zip(records, document_tokens):
        embedding_refs = record.get("embeddingRefs") or {}
        documents.append({
            "id": record.get("id"),
            "textEmbeddingId": embedding_refs.get("textEmbeddingId") or record.get("id"),
            "path": record.get("path"),
            "name": record.get("name"),
            "assetType": record.get("assetType"),
            "vector": build_sparse_tfidf_vector(tokens, idf),
        })

    return {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "scheme": "tfidf-sparse-v1",
        "documentCount": document_count,
        "idf": idf,
        "documents": documents,
    }


def load_vector_index(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def score_query_against_index(query_text: str, vector_index: dict[str, Any]) -> dict[str, float]:
    idf = vector_index.get("idf") or {}
    query_vector = build_sparse_tfidf_vector(tokenize(query_text), idf)
    if not query_vector:
        return {}

    scores: dict[str, float] = {}
    for document in vector_index.get("documents") or []:
        document_id = document.get("id")
        document_vector = document.get("vector") or {}
        if not document_id or not document_vector:
            continue
        score = cosine_similarity_sparse(query_vector, document_vector)
        if score > 0.0:
            scores[document_id] = round(score, 4)
    return scores


def cosine_similarity_sparse(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(token, 0.0) for token, value in left.items())
