#!/usr/bin/env python3
import argparse
import json
from collections import Counter
from pathlib import Path


def load_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            yield json.loads(line)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a Unity resource catalog JSONL file.")
    parser.add_argument("catalog", type=Path, help="Path to resource_catalog.jsonl")
    args = parser.parse_args()

    if not args.catalog.exists():
        raise SystemExit(f"Catalog not found: {args.catalog}")

    records = list(load_jsonl(args.catalog))
    counts = Counter(record.get("assetType", "Unknown") for record in records)

    print(f"records: {len(records)}")
    for asset_type, count in sorted(counts.items()):
        print(f"{asset_type}: {count}")

    print("")
    print("sample:")
    for record in records[:5]:
        print(json.dumps({
            "id": record.get("id"),
            "assetType": record.get("assetType"),
            "path": record.get("path"),
            "name": record.get("name"),
            "binding": record.get("binding", {}),
        }, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
