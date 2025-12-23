"""
wayback-archeologist public reference implementation.

This package contains small, self-contained services:

- scraper_service      – produce links.txt + status.json from queries
- proxy_pool_service   – maintain a shared proxies_cached.json
- media_download_worker – download non-archive media
- archive_worker       – resurrect media via an archive-style host
- split_service        – clean, dedupe, and batch downloaded files
- monitor              – show high-level pipeline status

All services coordinate via the filesystem only.
"""


