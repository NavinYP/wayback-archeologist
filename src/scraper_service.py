#!/usr/bin/env python3
"""
Scraper Service (Reference)
---------------------------

This service reads a `queries.txt` file, turns each line into a simple QuerySpec,
and calls a placeholder "platform client" to obtain outbound URLs for each query.

It writes, per query:

- downloads/<label>/links.txt
- downloads/<label>/status.json

The actual HTTP calls are intentionally stubbed; in your own project, plug in
clients for the platforms you care about (chat, forum, etc.) while following
the same on-disk contract.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


@dataclass
class QuerySpec:
    label: str
    content: str


def sanitize_label(text: str) -> str:
    """Turn an arbitrary query line into a filesystem-safe label."""
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in text.strip())
    safe = safe.strip("_") or "query"
    return safe[:64]


def parse_queries(path: Path) -> List[QuerySpec]:
    if not path.exists():
        raise SystemExit(f"queries file not found: {path}")

    specs: List[QuerySpec] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            label = sanitize_label(line.split()[0])
            specs.append(QuerySpec(label=label, content=line))

    if not specs:
        raise SystemExit("No valid queries in queries file.")
    return specs


def fake_platform_search(query: QuerySpec, seed: int | None = None) -> Iterable[str]:
    """
    Placeholder "search client".

    In a real deployment, replace this with calls to your chat/forum search
    endpoints and extract outbound media URLs from the JSON responses.

    Here we just generate a few deterministic fake URLs for demonstration.
    """
    rng = random.Random(seed or hash(query.label) & 0xFFFF)
    hosts = [
        "https://cdn.example.com/media/",
        "https://files.examplefilehost.com/",
        "https://archive.example.org/download/",
    ]
    count = rng.randint(3, 10)
    for i in range(count):
        host = rng.choice(hosts)
        yield f"{host}{query.label}_{i}.bin"


def write_status(query_dir: Path, label: str, links_count: int) -> None:
    status = {
        "query_label": label,
        "links_count": links_count,
        "scraped_at": time.time(),
        "direct_download_status": "pending",
        "archive_download_status": "pending",
        "split_status": "pending",
        "last_updated": time.time(),
    }
    status_path = query_dir / "status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status, indent=2, sort_keys=True), encoding="utf-8")


def run_scraper(args: argparse.Namespace) -> None:
    output_root: Path = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)

    specs = parse_queries(args.queries_file)

    for spec in specs:
        query_dir = output_root / spec.label
        query_dir.mkdir(parents=True, exist_ok=True)
        links_path = query_dir / "links.txt"

        print(f"[scraper] Query {spec.label!r} → {links_path}")
        links = sorted(set(fake_platform_search(spec)))

        # Write links.txt
        with links_path.open("w", encoding="utf-8") as fh:
            for url in links:
                fh.write(url + "\n")

        # Write initial status.json
        write_status(query_dir, spec.label, len(links))
        print(f"[scraper]   wrote {len(links)} links")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Reference scraper service for wayback-archeologist.")
    p.add_argument(
        "--queries-file",
        type=Path,
        default=Path("queries.txt"),
        help="Text file with one query per line.",
    )
    p.add_argument(
        "--output-root",
        type=Path,
        default=Path("downloads"),
        help="Root directory for per-query folders.",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    run_scraper(args)


if __name__ == "__main__":
    main()


