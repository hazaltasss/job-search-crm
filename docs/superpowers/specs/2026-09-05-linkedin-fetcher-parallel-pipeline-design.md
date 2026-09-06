# LinkedIn Fetcher + Parallel Pipeline + Cross-Source Dedup Hardening

## Problem Statement

The Job Search CRM currently ingests from 3 sources (Arbeitnow, WorkingStudentJobs.de, HiringCafe) run sequentially, resulting in pipeline runs of ~70-125 seconds. LinkedIn — the largest professional job board — is missing entirely. Additionally, as we add a 4th source, the risk of cross-source duplicates increases (the same job posted on both Arbeitnow and LinkedIn), and the current deduplication approach (full table scan with Python-side normalization) doesn't scale.

This spec covers three tightly coupled changes:
1. **New LinkedIn fetcher** via `python-jobspy` (no credentials, no account risk)
2. **Source-level parallelism** via `ThreadPoolExecutor` (all 4 fetchers run concurrently)
3. **Dedup hardening** via pre-computed normalized columns with database indexes

---

## 1. LinkedIn Fetcher (`src/fetchers/linkedin.py`)

### 1.1 Data Source: `python-jobspy`

The `python-jobspy` library scrapes LinkedIn's public job listing pages without authentication. It returns a Pandas DataFrame with structured fields (title, company, location, description, job_url, date_posted, etc.).

- **No credentials required** — does not use `li_at` cookie or LinkedIn login
- **No risk to Hazal's Premium account** — scrapes public listing pages only
- **Rate limiting** — we will use conservative delays and limit result counts

### 1.2 Search Strategy

Run multiple targeted queries matching the project's core criteria:

| Query | `search_term` | `location` | `results_wanted` |
|---|---|---|---|
| Data & AI – Berlin | `"working student data science machine learning"` | `"Berlin, Germany"` | 25 |
| Software – Berlin | `"working student software engineer python"` | `"Berlin, Germany"` | 25 |
| Intern – Berlin | `"internship data science software engineer"` | `"Berlin, Germany"` | 25 |
| Remote Germany | `"working student remote data software"` | `"Germany"` | 20 |

Parameters:
- `site_name=["linkedin"]`
- `hours_old=72` (last 3 days, matching HiringCafe's window)
- `linkedin_fetch_description=True` (get full descriptions for filter/match pipeline)

### 1.3 Position Filtering

Before converting to `Job` objects, filter for Werkstudent/Intern titles only — reuse the same `WORKING_STUDENT_PATTERNS` and `INTERN_PATTERNS` from `src/config.py`.

### 1.4 Conversion to `Job` Dataclass

Map Jobspy DataFrame columns to the existing `Job` dataclass:

| Jobspy Column | `Job` Field |
|---|---|
| `title` | `title` |
| `company` | `company` |
| `location` | `location` |
| `job_url` | `url` |
| `description` | `description` |
| `date_posted` | `posted_at` |
| `is_remote` | `is_remote` |
| *(generated)* | `job_id` = `"li_" + md5(job_url)[:12]` |
| *(constant)* | `source` = `"linkedin"` |

### 1.5 Error Handling

- If `python-jobspy` raises an exception (network, rate limit, parsing), catch and log the error — return an empty list.
- If LinkedIn blocks the request (429), log a warning with guidance to add proxy support.
- Each search query is independent — one failing doesn't abort the others.

---

## 2. Parallel Pipeline (`scripts/run_pipeline.py`)

### 2.1 Source-Level Parallelism

Replace the sequential fetcher calls with `concurrent.futures.ThreadPoolExecutor`:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

fetcher_tasks = {
    "Arbeitnow": lambda: fetch_arbeitnow(max_pages=8),
    "WorkingStudentJobs": lambda: fetch_wsj(max_pages=2),
    "HiringCafe": lambda: fetch_hiringcafe(),
    "LinkedIn": lambda: fetch_linkedin(),
}

raw_jobs = []
fetch_errors = []

with ThreadPoolExecutor(max_workers=4) as pool:
    futures = {
        pool.submit(fn): name
        for name, fn in fetcher_tasks.items()
    }
    for future in as_completed(futures):
        name = futures[future]
        try:
            jobs = future.result()
            raw_jobs.extend(jobs)
            logger.info("%s: %d raw jobs fetched", name, len(jobs))
        except Exception as exc:
            logger.error("%s fetch failed: %s", name, exc)
            fetch_errors.append(f"{name}: {exc}")
```

**Why threads, not asyncio?** The fetchers use synchronous `httpx.Client` and `time.sleep()`. Rewriting all 4 fetchers to async would be a much larger change. Threads give us source-level parallelism with zero changes to fetcher internals. Each fetcher runs in its own thread with its own HTTP client — no shared state.

### 2.2 Intra-Source Async for WSJ Detail Pages

The WorkingStudentJobs fetcher is the slowest because it fetches each job's detail page sequentially (0.3s sleep between each). We'll optimize this specific bottleneck:

**Phase 1 (listing pages):** Keep synchronous — sequential page fetches are fine (only 3 pages).

**Phase 2 (detail pages):** Switch to `asyncio` + `httpx.AsyncClient` with a semaphore to limit concurrency:

```python
import asyncio
import httpx

async def _fetch_descriptions_batch(urls: list[str], max_concurrent: int = 5) -> dict[str, str]:
    """Fetch multiple detail pages concurrently, returning {url: description}."""
    sem = asyncio.Semaphore(max_concurrent)
    results = {}

    async def _fetch_one(client: httpx.AsyncClient, url: str):
        async with sem:
            resp = await client.get(url, headers=_HEADERS, timeout=REQUEST_TIMEOUT)
            # ... parse JSON-LD description ...
            results[url] = parsed_description
            await asyncio.sleep(0.1)  # Minimal politeness delay

    async with httpx.AsyncClient(follow_redirects=True) as client:
        tasks = [_fetch_one(client, url) for url in urls]
        await asyncio.gather(*tasks, return_exceptions=True)

    return results
```

The main `fetch_jobs()` function calls this via `asyncio.run()` after collecting all card URLs from listing pages.

**Concurrency limit:** 5 concurrent requests. This is polite (WSJ is a small site) while still being ~6x faster than sequential.

---

## 3. Cross-Source Deduplication Hardening (`src/database.py`)

### 3.1 The Problem

The same job often appears on multiple boards with:
- Different URLs (`arbeitnow.com/...` vs `linkedin.com/jobs/view/...`)
- Different `job_id` values
- Same company name + same title (with minor formatting differences like `GmbH`, `(m/f/d)`)

The current `is_duplicate()` implementation:
1. Checks URL (fast, indexed) ✓
2. Fetches **all rows** from `jobs` table, normalizes company + title **in Python** on every call ✗

This is O(n) per job checked, with n = total jobs in the database. With 4 sources and hundreds of jobs, this becomes the bottleneck during the dedup step.

### 3.2 The Solution: Pre-Computed Normalized Columns

Add two columns to the `jobs` table:
```sql
ALTER TABLE jobs ADD COLUMN norm_company TEXT DEFAULT '';
ALTER TABLE jobs ADD COLUMN norm_title TEXT DEFAULT '';
```

Create a composite index:
```sql
CREATE INDEX IF NOT EXISTS idx_dedup_norm ON jobs(norm_company, norm_title);
```

**At insert time:** Compute `normalize_company()` and `normalize_title()` once and store the results.

**At dedup check time:** Query the index directly:
```python
def is_duplicate(url: str, title: str = "", company: str = "") -> bool:
    with _connection() as conn:
        # Fast path: exact URL match
        if conn.execute("SELECT 1 FROM jobs WHERE url = ?", (url,)).fetchone():
            return True

        if not title or not company:
            return False

        norm_c = normalize_company(company)
        norm_t = normalize_title(title)
        if not norm_c or not norm_t:
            return False

        # Indexed lookup — O(1) instead of O(n)
        row = conn.execute(
            "SELECT 1 FROM jobs WHERE norm_title = ? AND norm_company = ?",
            (norm_t, norm_c),
        ).fetchone()
        if row:
            return True

        # Fuzzy: one company name is a substring of the other
        rows = conn.execute(
            "SELECT norm_company FROM jobs WHERE norm_title = ?",
            (norm_t,),
        ).fetchall()
        for r in rows:
            ex_c = r[0] or ""
            if (len(norm_c) >= 4 and norm_c in ex_c) or (len(ex_c) >= 4 and ex_c in norm_c):
                return True

    return False
```

This preserves the existing fuzzy substring matching for company names (e.g., "autarc" matching "autarc energy") but only for jobs with the same normalized title — a much smaller set.

### 3.3 Migration Strategy

The `init_db()` function will:
1. Add `norm_company` and `norm_title` columns (safe `ALTER TABLE` with try/except)
2. Backfill existing rows: `UPDATE jobs SET norm_company = ?, norm_title = ? WHERE id = ?`
3. Create the composite index

This is non-destructive and backward-compatible.

---

## 4. Dependency Changes (`requirements.txt`)

Add:
```
python-jobspy>=1.1.0
```

`python-jobspy` pulls in `pandas`, `beautifulsoup4`, and `httpx` — all of which are either already in our deps or are standard.

---

## 5. Files Changed Summary

| File | Action | Description |
|---|---|---|
| `src/fetchers/linkedin.py` | **NEW** | Jobspy-based LinkedIn fetcher with multi-query search |
| `scripts/run_pipeline.py` | **MODIFY** | ThreadPoolExecutor for parallel source fetching |
| `src/fetchers/workingstudentjobs.py` | **MODIFY** | Async detail-page fetching with semaphore |
| `src/database.py` | **MODIFY** | Pre-computed norm columns, indexed dedup, backfill migration |
| `requirements.txt` | **MODIFY** | Add `python-jobspy` |

---

## 6. Performance Impact

| Metric | Before | After |
|---|---|---|
| Sources | 3 | 4 (+ LinkedIn) |
| Pipeline execution | Sequential (~70-125s) | Parallel (~15-25s) |
| WSJ detail fetches | Sequential (0.3s each) | 5-concurrent async (~6x faster) |
| Dedup check per job | O(n) Python scan | O(1) indexed SQL query |
| Cross-source duplicates | Caught (slow) | Caught (fast, same logic) |

---

## 7. What This Does NOT Include

- No use of Hazal's LinkedIn credentials or Premium session
- No applicant insights/demographics scraping
- No browser automation or Playwright
- No proxy configuration (can be added later if rate limits become an issue)
- No changes to dashboard UI, filters, Telegram, or Sheets integration
