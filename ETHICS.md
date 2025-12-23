## Ethics & Responsible Use

`wayback-archeologist` exists to demonstrate architecture and patterns for doing *responsible* one‑shot Internet archaeology. It is **not** an invitation to scrape any particular site, ignore platform rules, or harvest private data.

This document captures the principles the original project followed. If you adapt this code, please take them seriously and extend them where needed.

---

### 1. Scope of Content

- Only work with **already‑public** content:
  - Content that is visible in the normal UI without bypassing access controls.
  - Content your account is legitimately allowed to see.
- Do **not** scrape:
  - Private messages, DMs, or invite‑only spaces.
  - Hidden or internal APIs that require reverse‑engineering to access.

If in doubt, assume it’s out of scope.

---

### 2. Terms of Service & Robots.txt

- Read and respect the terms of service for any site you interact with.
- Honor `robots.txt` and similar mechanisms where applicable.
- If a platform disallows automated scraping of certain resources, treat that as a hard boundary.

This repo deliberately anonymizes platform names and does *not* include any platform‑specific scraping recipes.

---

### 3. Rate Limits & Resource Use

- Use **conservative defaults** for delays and concurrency:
  - Back off when you see HTTP 429 (Too Many Requests).
  - Use `Retry-After` headers where available.
- Design for *one‑shot*, finite runs rather than continuous scraping:
  - Start, archive what you need, stop.
  - Don’t run this as a 24/7 crawler.

Remember that you are sharing infrastructure (and the Internet Archive) with everyone else.

---

### 4. Credentials & Secrets

- Never commit:
  - API keys.
  - Session cookies.
  - Authorization tokens.
  - Personal account information.

All secrets should live in a local `.env` file that is excluded from version control. The provided `.env.example` is for structure only and contains no real data.

---

### 5. Privacy & Safety

- Avoid collecting or redistributing:
  - Personally identifiable information (PII) that isn’t already widely public.
  - Sensitive or exploitative content.
- Treat any dataset you build as if it contains **other people’s history**, not just “test data.”

If you’re working with meme clips or similar cultural artifacts, be mindful of context and consent.

---

### 6. Redistribution & Re‑Hosting

- This repo is about **archival workflows**, not about re‑publishing content.
- Before re‑hosting any media:
  - Check licenses.
  - Consider creator intent and platform rules.
  - Err on the side of not making things more public than they already were.

In many cases, it’s safer to keep archives for personal research or preservation rather than public redistribution.

---

### 7. Legal Considerations

This project and its documentation are not legal advice.

- Laws vary by jurisdiction.
- Platform policies change over time.
- You are responsible for ensuring that your use of this code complies with:
  - Applicable laws.
  - Platform terms.
  - Organizational policies (if you’re doing this at work).

If you are unsure, consult a qualified professional before running large‑scale archival jobs.

---

### 8. Design for Ethics, Not Just Disclaimers

The original `wayback-archeologist` pipeline tried to encode these principles in its design:

- Using `.env` for secrets and ignoring it in version control.
- Building scrapers around existing, user‑visible search UIs.
- Adding explicit delays, backoff, and rate‑limit handling.
- Running jobs as finite passes instead of open‑ended crawlers.
- Keeping identities of platforms and content anonymized in public writeups.

If you extend this project, think about how your design decisions can *enforce* good behavior rather than just trusting comments and documentation to do the work.


