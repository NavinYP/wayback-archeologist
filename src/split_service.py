#!/usr/bin/env python3
"""
Split & Curation Service (Reference)
------------------------------------

This service watches `downloads/` for queries where both:

- direct_download_status == "completed"
- archive_download_status == "completed"

and then:

- Cleans obvious junk/manifest files from `raw/`.
- Deduplicates files by content hash.
- Randomly batches small files into folders of N.
- Sends large files into a `<label>_large/` folder.
- Updates `status.json` with split_status + split_summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import threading
import time
from pathlib import Path
from typing import Dict, List


status_lock = threading.Lock()


def update_status(query_dir: Path, **updates) -> None:
    status_path = query_dir / "status.json"
    with status_lock:
        status: Dict[str, object] = {}
        if status_path.exists():
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                status = {}
        status.update(updates)
        status["last_updated"] = time.time()
        status_path.write_text(json.dumps(status, indent=2, sort_keys=True), encoding="utf-8")


def find_ready_queries(root: Path) -> List[Path]:
    ready: List[Path] = []
    if not root.exists():
        return ready
    for query_dir in root.iterdir():
        if not query_dir.is_dir():
            continue
        status_path = query_dir / "status.json"

        if not status_path.exists():
            continue
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = {}

        if status.get("split_status") == "completed":
            continue

        if status.get("direct_download_status") == "completed" and status.get(
            "archive_download_status"
        ) == "completed":
            ready.append(query_dir)
    return sorted(ready, key=lambda p: (p / "status.json").stat().st_mtime)


def file_hash(path: Path, block_size: int = 65536) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(block_size), b""):
            h.update(chunk)
    return h.hexdigest()


def process_split(query_dir: Path, batch_size: int, threshold_mb: int) -> Dict[str, int]:
    label = query_dir.name
    raw_dir = query_dir / "raw"
    split_dir = query_dir / "split"
    threshold_bytes = threshold_mb * 1024 * 1024

    if not raw_dir.exists():
        update_status(query_dir, split_status="completed", split_summary={})
        return {}

    if split_dir.exists():
        shutil.rmtree(split_dir)
    split_dir.mkdir(parents=True, exist_ok=True)

    # Stage 1: collect files
    files = [p for p in raw_dir.rglob("*") if p.is_file()]
    print(f"[split] {label}: found {len(files)} raw file(s)")

    # Stage 2: filter out manifest-like junk
    allowed_exts = {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".mp4",
        ".webm",
        ".mkv",
        ".mov",
    }
    filtered: List[Path] = []
    for f in files:
        ext = f.suffix.lower()
        if ext in {".m3u8", ".mpd"}:
            f.unlink(missing_ok=True)
            continue
        if ext == ".mp4" and f.stat().st_size < 500 * 1024:
            f.unlink(missing_ok=True)
            continue
        if ext not in allowed_exts:
            f.unlink(missing_ok=True)
            continue
        filtered.append(f)

    print(f"[split] {label}: {len(filtered)} file(s) after filtering")

    if not filtered:
        update_status(query_dir, split_status="completed", split_summary={})
        return {}

    # Stage 3: dedupe
    seen: Dict[str, Path] = {}
    deduped: List[Path] = []
    dupes = 0
    for f in filtered:
        h = file_hash(f)
        if h in seen:
            f.unlink(missing_ok=True)
            dupes += 1
        else:
            seen[h] = f
            deduped.append(f)

    print(f"[split] {label}: {len(deduped)} file(s) after removing {dupes} duplicate(s)")

    # Stage 4: random batches + large bucket
    small: List[Path] = []
    large: List[Path] = []
    for f in deduped:
        if f.stat().st_size <= threshold_bytes:
            small.append(f)
        else:
            large.append(f)

    random.shuffle(small)

    batches = 0
    copied_small = 0
    for i in range(0, len(small), batch_size):
        chunk = small[i : i + batch_size]
        if not chunk:
            continue
        idx = i // batch_size + 1
        batch_dir = split_dir / f"{label}_{idx}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        for src in chunk:
            shutil.copy2(src, batch_dir / src.name)
            copied_small += 1
        batches += 1

    if large:
        large_dir = split_dir / f"{label}_large"
        large_dir.mkdir(parents=True, exist_ok=True)
        for src in large:
            shutil.copy2(src, large_dir / src.name)

    summary = {
        "small_files": len(small),
        "large_files": len(large),
        "batch_folders": batches,
        "copied_small": copied_small,
        "large_folder_created": int(bool(large)),
    }
    update_status(query_dir, split_status="completed", split_summary=summary)
    print(
        f"[split] {label}: {summary['copied_small']} small file(s) into {summary['batch_folders']} batch(es), "
        f"{summary['large_files']} large file(s)",
    )
    return summary


def run_service(args: argparse.Namespace) -> None:
    root: Path = args.output_root
    print(f"[split] watching {root}")

    while True:
        ready = find_ready_queries(root)
        if not ready:
            time.sleep(args.watch_interval)
            continue

        for query_dir in ready:
            process_split(query_dir, batch_size=args.batch_size, threshold_mb=args.threshold_mb)

        time.sleep(args.watch_interval)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Split/curation service for wayback-archeologist.")
    p.add_argument(
        "--output-root",
        type=Path,
        default=Path("downloads"),
        help="Root directory containing per-query folders.",
    )
    p.add_argument(
        "--watch-interval",
        type=float,
        default=10.0,
        help="Seconds between scans of the output root.",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of files per batch folder.",
    )
    p.add_argument(
        "--threshold-mb",
        type=int,
        default=10,
        help="Files larger than this many MB go into the _large bucket.",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    run_service(args)


if __name__ == "__main__":
    main()


