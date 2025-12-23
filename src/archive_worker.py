#!/usr/bin/env python3
"""
Archive Worker (Reference)
--------------------------

This worker is responsible for handling links that point at a "dead" media host
whose content now lives via an archive (e.g., the Internet Archive).

It:
- Normalizes original URLs into archive URLs.
- Stores them in `archive_links.txt`.
- Downloads media into `raw/archive_host/`.
- Updates `status.json` with archive_download_* fields.

For simplicity, this reference worker:
- Uses a basic resolve+download loop (no aggressive parallelism).
- Optionally reads a `proxies_cached.json` written by proxy_pool_service.py.
"""

from __future__ import annotations

import argparse
import json
import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
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


def normalize_archive_link(url: str) -> str:
    parsed = urlparse(url)
    if "web.archive.org" in parsed.netloc:
        return url
    return f"https://web.archive.org/web/{url}"


def load_links(path: Path) -> Set[str]:
    urls: Set[str] = set()
    if not path.exists():
        return urls
    with path.open("r", encoding="utf-8") as fh:
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


def load_proxy_list(cache_file: Path) -> List[str]:
    if not cache_file.exists():
        return []
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    proxies: List[str] = []
    for item in data:
        proxy = item.get("proxy")
        if isinstance(proxy, str):
            proxies.append(proxy)
    return proxies


@dataclass
class ArchiveJob:
    original_url: str
    archive_url: str
    target_path: Path


class ArchiveDownloader:
    def __init__(self, timeout: int = 45, proxies: Optional[List[str]] = None) -> None:
        self.timeout = timeout
        self.proxies = proxies or []
        self.base_session = build_retrying_session()

    def _session_for_job(self) -> requests.Session:
        if not self.proxies:
            return self.base_session
        proxy = random.choice(self.proxies)
        s = build_retrying_session()
        s.proxies = {"http": proxy, "https": proxy}
        return s

    def download(self, job: ArchiveJob) -> Tuple[bool, Optional[Path], Optional[str]]:
        if job.target_path.exists():
            return True, job.target_path, None
        tmp = job.target_path.with_suffix(job.target_path.suffix + ".part")
        session = self._session_for_job()

        try:
            with session.get(job.archive_url, stream=True, timeout=self.timeout) as resp:
                if resp.status_code == 404:
                    return False, None, "404 Not Found (no snapshot)"
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
        status_path = query_dir / "status.json"
        if not status_path.exists():
            continue
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = {}
        if status.get("archive_download_status") in (None, "pending", "in_progress"):
            pending.append(query_dir)
    return sorted(pending, key=lambda p: (p / "status.json").stat().st_mtime)


def run_worker(args: argparse.Namespace) -> None:
    root: Path = args.output_root
    cache_file: Path = args.proxy_cache_file

    proxies = load_proxy_list(cache_file) if args.use_proxies else []
    downloader = ArchiveDownloader(timeout=args.timeout, proxies=proxies)

    print(f"[archive-worker] watching {root}")
    if proxies:
        print(f"[archive-worker] loaded {len(proxies)} proxy/proxies from {cache_file}")

    while True:
        pending = find_pending_queries(root)
        if not pending:
            time.sleep(args.watch_interval)
            continue

        for query_dir in pending:
            label = query_dir.name
            links_path = query_dir / "links.txt"
            archive_txt = query_dir / "archive_links.txt"
            raw_dir = query_dir / "raw" / "archive_host"
            raw_dir.mkdir(parents=True, exist_ok=True)

            all_links = load_links(links_path)

            # Filter for "dead host" URLs – in a real deployment, match your host(s).
            ghost_links = [u for u in all_links if "ghostclips.example" in urlparse(u).netloc]

            if not ghost_links:
                update_status(query_dir, archive_download_status="completed", archive_download_count=0)
                continue

            # Normalize to archive URLs and write archive_links.txt
            normalized = [normalize_archive_link(u) for u in ghost_links]
            with archive_txt.open("w", encoding="utf-8") as fh:
                for u in normalized:
                    fh.write(u + "\n")

            print(f"[archive-worker] {label}: {len(normalized)} archive URL(s)")
            update_status(query_dir, archive_download_status="in_progress")

            total = len(normalized)
            downloaded = 0

            for url in normalized:
                filename = Path(urlparse(url).path).name or "archive.bin"
                target = raw_dir / filename
                job = ArchiveJob(original_url=url, archive_url=url, target_path=target)
                ok, _, err = downloader.download(job)
                if ok:
                    downloaded += 1
                else:
                    print(f"[archive-worker]   failed: {url} ({err})")

            update_status(
                query_dir,
                archive_download_status="completed",
                archive_download_count=downloaded,
                archive_download_total=total,
            )
            print(f"[archive-worker] {label}: {downloaded}/{total} archive download(s) completed")

        time.sleep(args.watch_interval)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Archive worker for wayback-archeologist.")
    p.add_argument(
        "--output-root",
        type=Path,
        default=Path("downloads"),
        help="Root directory containing per-query folders.",
    )
    p.add_argument(
        "--proxy-cache-file",
        type=Path,
        default=Path("proxies_cached.json"),
        help="Proxy cache file written by proxy_pool_service.py.",
    )
    p.add_argument(
        "--use-proxies",
        action="store_true",
        help="Use proxies from the cache when talking to the archive host.",
    )
    p.add_argument(
        "--watch-interval",
        type=float,
        default=10.0,
        help="Seconds between scans of the output root.",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=45,
        help="Per-request timeout in seconds.",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    run_worker(args)


if __name__ == "__main__":
    main()


