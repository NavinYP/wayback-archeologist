#!/usr/bin/env python3
"""
Proxy Pool Service (Reference)
------------------------------

This service maintains a shared `proxies_cached.json` file that other workers
can read from. It is intentionally generic:

- Fetches candidate proxies from one or more HTTP endpoints (or a local file).
- Tests them against a configurable target URL (e.g., an archive host).
- Scores proxies based on latency and success rate.
- Periodically refreshes the cache.

Workers should treat `proxies_cached.json` as read-only and never attempt to
modify it themselves.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

import requests


DEFAULT_PROXY_SOURCES = [
    # These are placeholders; in your own deployment, configure real lists.
    "https://example.com/public-proxies.txt",
]


@dataclass
class ProxyScore:
    proxy: str
    latency_ms: float
    success_rate: float

    @property
    def overall_score(self) -> float:
        # Lower is better; tune as desired
        return self.latency_ms / 1000.0 - self.success_rate


def fetch_proxies_from_sources(sources: Iterable[str]) -> List[str]:
    proxies: list[str] = []
    session = requests.Session()

    for url in sources:
        try:
            resp = session.get(url, timeout=10)
            resp.raise_for_status()
            for line in resp.text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                proxies.append(line)
        except requests.RequestException:
            # Best-effort only; skip failing sources
            continue

    return proxies


def test_proxy(proxy: str, target_url: str, timeout: int = 8) -> ProxyScore | None:
    session = requests.Session()
    session.proxies = {"http": proxy, "https": proxy}
    session.headers.update({"User-Agent": "wayback-archeologist/1.0"})

    ok = 0
    attempts = 3
    total_latency = 0.0

    for _ in range(attempts):
        start = time.perf_counter()
        try:
            resp = session.get(target_url, timeout=timeout)
            resp.raise_for_status()
            ok += 1
        except requests.RequestException:
            pass
        total_latency += (time.perf_counter() - start) * 1000.0

    if ok == 0:
        return None

    return ProxyScore(
        proxy=proxy,
        latency_ms=total_latency / attempts,
        success_rate=ok / attempts,
    )


def save_proxy_cache(cache_file: Path, scores: List[ProxyScore]) -> None:
    data = [
        {
            "proxy": s.proxy,
            "latency_ms": s.latency_ms,
            "success_rate": s.success_rate,
            "overall_score": s.overall_score,
            "tested_at": time.time(),
        }
        for s in scores
    ]
    cache_file.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def run_proxy_service(args: argparse.Namespace) -> None:
    cache_file: Path = args.cache_file
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"[proxy-pool] writing cache to {cache_file}")
    print(f"[proxy-pool] refresh interval: {args.refresh_interval}s")

    while True:
        print("[proxy-pool] refreshing proxies…")
        raw_proxies = fetch_proxies_from_sources(args.proxy_source)
        unique = sorted(set(raw_proxies))
        print(f"[proxy-pool] fetched {len(unique)} unique candidates")

        scores: list[ProxyScore] = []
        for p in unique:
            score = test_proxy(p, args.test_url, timeout=args.test_timeout)
            if score:
                scores.append(score)

        scores.sort(key=lambda s: s.overall_score)
        if scores:
            save_proxy_cache(cache_file, scores[: args.max_proxies])
            print(f"[proxy-pool] cached {min(len(scores), args.max_proxies)} working proxies")
        else:
            print("[proxy-pool] no working proxies found this round")

        if args.run_once:
            break

        time.sleep(args.refresh_interval)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Proxy pool service for wayback-archeologist.")
    p.add_argument(
        "--cache-file",
        type=Path,
        default=Path("proxies_cached.json"),
        help="Where to write the shared proxy cache.",
    )
    p.add_argument(
        "--proxy-source",
        nargs="*",
        default=DEFAULT_PROXY_SOURCES,
        help="One or more URLs that return newline-delimited proxies.",
    )
    p.add_argument(
        "--test-url",
        default="https://web.archive.org/",
        help="Target URL to test proxies against (default: Internet Archive).",
    )
    p.add_argument(
        "--test-timeout",
        type=int,
        default=8,
        help="Timeout in seconds for each proxy test request.",
    )
    p.add_argument(
        "--max-proxies",
        type=int,
        default=50,
        help="Maximum number of proxies to keep in the cache.",
    )
    p.add_argument(
        "--refresh-interval",
        type=int,
        default=3600,
        help="Seconds between refreshes in continuous mode.",
    )
    p.add_argument(
        "--run-once",
        action="store_true",
        help="Fetch and test proxies once, then exit.",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    run_proxy_service(args)


if __name__ == "__main__":
    main()


