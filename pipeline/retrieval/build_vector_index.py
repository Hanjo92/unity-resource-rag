#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from vector_index import build_tfidf_index, load_jsonl, save_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a vector-searchable index from a Unity resource catalog."
    )
    parser.add_argument("catalog", type=Path, help="Path to resource_catalog.jsonl")
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to write resource_vector_index.json. Defaults next to the catalog.",
    )
    args = parser.parse_args()

    output_path = args.output or args.catalog.with_name("resource_vector_index.json")
    records = load_jsonl(args.catalog)
    vector_index = build_tfidf_index(records)
    save_json(output_path, vector_index)

    print(json.dumps({
        "catalog": str(args.catalog),
        "output": str(output_path),
        "scheme": vector_index["scheme"],
        "documentCount": vector_index["documentCount"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
