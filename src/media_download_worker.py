#!/usr/bin/env python3
"""
Media Download Worker (Reference)
---------------------------------

This worker watches `downloads/` for queries with `links.txt` and downloads
non-archive media (e.g., CDN or file-host links) into:

- downloads/<label>/raw/<host>/

It updates per-query `status.json` with:

- direct_download_status
- direct_download_count / direct_download_total

This implementation is intentionally generic and focuses on the coordination
pattern, not on any particular host.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


USER_AGENT = "wayback-archeologist/1.0"


def build_retrying_session(total_retries: int = 3, backoff: float = 0.5) -> requests.Session:
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "HEAD"]),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def host_key(url: str) -> str:
    return urlparse(url).netloc or "unknown-host"


def load_links(links_path: Path) -> Set[str]:
    urls: Set[str] = set()
    if not links_path.exists():
        return urls
    with links_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.add(line)
    return urls


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


@dataclass
class DownloadJob:
    url: str
    target_path: Path


class SimpleDownloader:
    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout
        self.session = build_retrying_session()

    def download(self, job: DownloadJob) -> Tuple[bool, Optional[Path], Optional[str]]:
        if job.target_path.exists():
            return True, job.target_path, None
        tmp = job.target_path.with_suffix(job.target_path.suffix + ".part")
        try:
            with self.session.get(job.url, stream=True, timeout=self.timeout) as resp:
                resp.raise_for_status()
                tmp.parent.mkdir(parents=True, exist_ok=True)
                with tmp.open("wb") as fh:
                    for chunk in resp.iter_content(chunk_size=1 << 15):
                        if not chunk:
                            continue
                        fh.write(chunk)
            tmp.replace(job.target_path)
            return True, job.target_path, None
        except requests.RequestException as exc:
            if tmp.exists():
                tmp.unlink()
            return False, None, str(exc)


def find_pending_queries(download_root: Path) -> List[Path]:
    pending: List[Path] = []
    if not download_root.exists():
        return pending
    for query_dir in download_root.iterdir():
        if not query_dir.is_dir():
            continue
        links_path = query_dir / "links.txt"
        status_path = query_dir / "status.json"
        if not links_path.exists() or not status_path.exists():
            continue
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = {}
        if status.get("direct_download_status") in (None, "pending", "in_progress"):
            pending.append(query_dir)
    return sorted(pending, key=lambda p: (p / "status.json").stat().st_mtime)


def run_worker(args: argparse.Namespace) -> None:
    root: Path = args.output_root
    timeout: int = args.timeout
    downloader = SimpleDownloader(timeout=timeout)

    print(f"[media-worker] watching {root}")
    while True:
        pending = find_pending_queries(root)
        if not pending:
            time.sleep(args.watch_interval)
            continue

        for query_dir in pending:
            label = query_dir.name
            links_path = query_dir / "links.txt"
            raw_dir = query_dir / "raw"
            urls = load_links(links_path)

            print(f"[media-worker] processing {label}: {len(urls)} URL(s)")
            update_status(query_dir, direct_download_status="in_progress")

            completed = 0
            total = 0
            for url in sorted(urls):
                # In this reference worker, treat anything from "archive-host"
                # as the responsibility of the archive_worker, not this one.
                if "archive-host.example" in host_key(url):
                    continue

                total += 1
                host = host_key(url)
                target = raw_dir / host / (Path(urlparse(url).path).name or "file.bin")
                ok, _, err = downloader.download(DownloadJob(url=url, target_path=target))
                if ok:
                    completed += 1
                else:
                    print(f"[media-worker]   failed: {url} ({err})")

            update_status(
                query_dir,
                direct_download_status="completed",
                direct_download_count=completed,
                direct_download_total=total,
            )
            print(f"[media-worker] {label}: {completed}/{total} direct download(s) completed")

        time.sleep(args.watch_interval)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Media download worker for wayback-archeologist.")
    p.add_argument(
        "--output-root",
        type=Path,
        default=Path("downloads"),
        help="Root directory containing per-query folders.",
    )
    p.add_argument(
        "--watch-interval",
        type=float,
        default=5.0,
        help="Seconds between scans of the output root.",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Per-request timeout in seconds.",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    run_worker(args)


if __name__ == "__main__":
    main()


