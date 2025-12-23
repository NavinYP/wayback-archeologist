# 🏛️ wayback-archeologist

> A self-contained pipeline for responsible one-shot "internet archaeology" runs

**wayback-archeologist** is a small, self-contained pipeline for doing one-shot "internet archaeology" runs:

- 🔍 Scrape public search results from anonymized platforms
- 🔗 Normalize and deduplicate outbound media links
- ⬇️ Download media using host-aware strategies
- 🗄️ Resurrect media from an archive-style host (e.g., via the Internet Archive)
- 📦 Split and dedupe the final corpus into human-sized, random batches

### ✨ Design Philosophy

The design is intentionally simple:

- 📁 **Filesystem-based coordination** – Uses `links.txt`, `status.json`, `raw/`, `split/` for state
- 🔄 **Independent processes** – Each stage runs as its own process you can start/stop independently
- 🔒 **Security-first** – All sensitive credentials live in `.env` and are never committed

> 💡 **Note:** This repo is the **public, anonymized companion** to the `Wayback Archeologist` article. It focuses on architecture and patterns, not on scraping any specific site.

---

## 🏗️ High-Level Architecture

### Directory Structure

Each search query is represented on disk as:

```
downloads/<label>/
├─ links.txt          # outbound URLs for this query
├─ manifest.json      # per-URL download state
├─ status.json        # per-stage pipeline state
├─ raw/               # downloaded files, organized by host
└─ split/             # randomized batches and large-file bucket
```

### 🛠️ Services

The pipeline consists of several independent services:

#### 📥 `scraper_service.py`
Reads `queries.txt`, calls platform search endpoints (abstracted behind a simple interface here), and writes:
- `downloads/<label>/links.txt`
- `downloads/<label>/status.json` (with `"pending"` statuses for later stages)

#### 🔄 `proxy_pool_service.py`
Background "proxy herd" that:
- Fetches candidate proxies from configured sources
- Tests and scores them
- Writes a shared `proxies_cached.json` file that other workers read

#### ⬇️ `media_download_worker.py`
Watches `downloads/` for `links.txt` files and downloads **non-archive** media:
- Uses a `MultiHostDownloader` to select the right handler per host
- Writes into `raw/<host>/...`
- Updates `status.json` with `direct_download_status` and counters

#### 🗄️ `archive_worker.py`
Handles links from a "dead" media host that now lives on an archive (e.g., via the Internet Archive):
- Normalizes original URLs to archive URLs
- Stores them in `archive_links.txt`
- Optionally runs in sequential or resolve+download parallel mode
- Updates `status.json` with `archive_download_status` and counters

#### 📦 `split_service.py`
Runs once both download stages are complete:
- Cleans up obvious junk/manifest files
- Deduplicates by content hash
- Randomly batches small files into folders of N (e.g., 100)
- Sends large files into `<label>_large/`
- Updates `status.json` with `split_status` and a `split_summary`

#### 📊 `monitor.py`
Periodically scans `status.json` files and prints a summary of:
- How many queries are pending / in progress / completed
- Per-query progress for direct vs archive downloads
- Split status and batch counts

> 💬 **Communication:** All services communicate only through the filesystem. There is no database, no message queue, and no external state beyond `status.json`, `manifest.json`, and the shared `proxies_cached.json`.

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- pip

### Demo Workflow

#### 1️⃣ Clone and set up

```bash
git clone <your-repo-url>.git
cd wayback-archeologist

python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

#### 2️⃣ Create a `.env` file

Copy `.env.example` to `.env` and fill in any credentials you plan to use (or leave them blank if you're just experimenting locally).

#### 3️⃣ Create a `queries.txt`

Create a `queries.txt` file with one query per line:

```text
project-name 2024-01-01 memes
another-topic 2023-06-01 archive
```

Each line becomes a `QuerySpec` with:
- **`label`** – a filesystem-safe label derived from the line
- **`content`** – the literal search string to send to your platform-specific clients

#### 4️⃣ Run the services

Run each service in a separate terminal window:

**Scraper Service:**
```bash
python -m src.scraper_service \
  --queries-file queries.txt \
  --output-root downloads
```

**Proxy Pool Service** (optional, for archive-heavy workloads):
```bash
python -m src.proxy_pool_service \
  --cache-file proxies_cached.json
```

**Media Download Worker:**
```bash
python -m src.media_download_worker \
  --output-root downloads
```

**Archive Worker:**
```bash
python -m src.archive_worker \
  --output-root downloads
```

**Split Service:**
```bash
python -m src.split_service \
  --output-root downloads
```

**Monitor:**
```bash
python -m src.monitor \
  --output-root downloads
```

> 💡 **Tip:** You can start/stop these processes independently. Each will pick up where it left off by reading `status.json` and `manifest.json`.

---

## ⚖️ Ethics & Responsible Use

> ⚠️ **Important:** This repo is **not** a how‑to guide for ignoring terms of service. It's a reference architecture for responsible, one‑shot archival of already‑public content.

**Please read [`ETHICS.md`](ETHICS.md) before using any of this code**, and adapt the principles to your own project. In particular:

- ✅ Only access content you are allowed to see in the normal UI
- ⏱️ Use conservative rate limits and respect `Retry-After` headers
- 🔒 Don't commit real tokens, cookies, or credentials
- 📋 Don't re‑host or publish archived content in ways that violate legal or ethical norms

---

## 📝 Limitations & Non-Goals

- This is a **reference implementation**, not a turnkey scraper for any specific platform
- The "platform clients" are intentionally abstracted; you're expected to plug in your own search callers where appropriate
- There is no database or job queue; everything is file‑backed and meant for finite, one‑off runs

### 🔮 Future Considerations

If you adapt this for your own needs, consider:

- 📊 Adding structured logging and richer monitoring as your job size grows
- 🔄 Introducing a job queue if you need to coordinate many machines and hundreds of queries

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


