#!/usr/bin/env python3
"""
Monitor Service (Reference)
---------------------------

This small utility scans `downloads/` for `status.json` files and prints a
summary of pipeline progress:

- how many queries are pending / in progress / completed
- per-query direct vs archive download status
- split status and batch counts
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict


def load_status_files(root: Path) -> Dict[str, Dict]:
    result: Dict[str, Dict] = {}
    if not root.exists():
        return result
    for query_dir in root.iterdir():
        if not query_dir.is_dir():
            continue
        status_path = query_dir / "status.json"
        if not status_path.exists():
            continue
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        result[query_dir.name] = status
    return result


def summarize(root: Path) -> None:
    statuses = load_status_files(root)
    total = len(statuses)
    if total == 0:
        print("No status.json files found yet.")
        return

    states = {"pending": 0, "in_progress": 0, "completed": 0, "failed": 0}

    for label, s in statuses.items():
        # Consider a query "completed" when split_status is completed
        st = s.get("split_status") or s.get("archive_download_status") or s.get("direct_download_status")
        st = st or "pending"
        if st not in states:
            states[st] = 0
        states[st] += 1

    print(f"Queries: {total}")
    for k in ("completed", "in_progress", "pending", "failed"):
        if k in states:
            print(f"  {k:>11}: {states[k]}")

    print()
    for label, s in sorted(statuses.items(), key=lambda x: x[0]):
        dd = s.get("direct_download_status", "pending")
        ad = s.get("archive_download_status", "pending")

        split = s.get("split_status", "pending")
        batches = None
        summary = s.get("split_summary")
        if isinstance(summary, dict):
            batches = summary.get("batch_folders")

        line = f"[{label}] direct={dd}, archive={ad}, split={split}"
        if batches is not None:
            line += f" ({batches} batch folder(s))"
        print(line)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Simple status monitor for wayback-archeologist.")
    p.add_argument(
        "--output-root",
        type=Path,
        default=Path("downloads"),
        help="Root directory containing per-query folders.",
    )
    p.add_argument(
        "--refresh-interval",
        type=float,
        default=5.0,
        help="Seconds between refreshes.",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        while True:
            print("\x1b[2J\x1b[H", end="")  # clear screen
            print(f"wayback-archeologist monitor – {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            summarize(args.output_root)
            time.sleep(args.refresh_interval)
    except KeyboardInterrupt:
        print("\nMonitor stopped.")


if __name__ == "__main__":
    main()


