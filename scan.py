#!/usr/bin/env python3
"""
scan.py — Pull jobs from all sources, filter, deduplicate, write to pipeline.md.
Zero Claude tokens. Run this first, then run eval.py.

Usage: python scan.py
"""

import csv
import json
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from sources import adzuna, arbeitnow, remoteok, remotive, weworkremotely

CONFIG_FILE = "config.yml"
PIPELINE_FILE = "pipeline.md"
HISTORY_FILE = "scan_history.tsv"
CACHE_FILE = "job_cache.json"

PIPELINE_ACTIVE_MARKER = "<!-- ACTIVE_JOBS -->"


def load_config() -> dict:
    if not Path(CONFIG_FILE).exists():
        sys.exit(f"Error: {CONFIG_FILE} not found.\nCopy config.example.yml to config.yml and fill in your settings.")
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


def load_history() -> set:
    seen = set()
    if not Path(HISTORY_FILE).exists():
        return seen
    with open(HISTORY_FILE) as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            seen.add(row.get("url", ""))
    return seen


def save_history(jobs: list):
    exists = Path(HISTORY_FILE).exists()
    with open(HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["url", "title", "company", "source", "added_at"], delimiter="\t")
        if not exists:
            writer.writeheader()
        for job in jobs:
            writer.writerow({
                "url": job["url"],
                "title": job["title"],
                "company": job["company"],
                "source": job["source"],
                "added_at": datetime.now(timezone.utc).isoformat(),
            })


def update_cache(jobs: list):
    cache = {}
    if Path(CACHE_FILE).exists():
        cache = json.loads(Path(CACHE_FILE).read_text())
    for job in jobs:
        if job.get("description") and job.get("url"):
            cache[normalize_url(job["url"])] = job["description"]
    Path(CACHE_FILE).write_text(json.dumps(cache, ensure_ascii=False, indent=2))


def normalize_url(url: str) -> str:
    """Strip common tracking query params for dedup purposes."""
    try:
        parsed = urllib.parse.urlparse(url)
        drop = {"utm_source", "utm_medium", "utm_campaign", "ref", "source", "aref", "scid", "cid"}
        qs = {k: v for k, v in urllib.parse.parse_qs(parsed.query).items() if k not in drop}
        return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(qs, doseq=True)))
    except Exception:
        return url


def passes_filters(job: dict, config: dict) -> tuple:
    """Returns (True, '') if the job passes all filters, or (False, reason) if not."""
    filters = config.get("filters", {})
    title = job.get("title", "").lower()
    location = job.get("location", "").lower()
    description = job.get("description", "").lower()

    if job.get("age_days", 0) > config.get("max_age_days", 5):
        return False, f"too old ({job['age_days']:.0f}d)"

    if not job.get("url"):
        return False, "no URL"

    # Title must contain at least one required keyword
    keywords = filters.get("keywords", {}).get("require_one", [])
    if keywords and not any(kw.lower() in title for kw in keywords):
        return False, "title keyword mismatch"

    for term in filters.get("seniority", {}).get("block", []):
        if term.lower() in title:
            return False, f"seniority: {term.strip()}"

    for term in filters.get("domain", {}).get("block", []):
        if term.lower() in title:
            return False, f"domain: {term.strip()}"

    loc_config = filters.get("location", {})
    block_terms = [t.lower() for t in loc_config.get("block", [])]
    allow_terms = [t.lower() for t in loc_config.get("allow", [])]
    is_remote = job.get("remote", False) or "remote" in location or "anywhere" in location

    for term in block_terms:
        if term in location:
            return False, f"location blocked: {term}"

    if not is_remote and allow_terms and location:
        if not any(term in location for term in allow_terms):
            return False, f"not in allowlist: {location}"

    for tech in filters.get("tech_stack", {}).get("negative", []):
        if tech.lower() in description:
            return False, f"negative tech: {tech}"

    return True, ""


def init_pipeline():
    if Path(PIPELINE_FILE).exists():
        return
    Path(PIPELINE_FILE).write_text(
        "# Job Pipeline\n\n"
        "> Run `python scan.py` to add jobs, then `python eval.py` to score them.\n\n"
        "## Active\n\n"
        f"{PIPELINE_ACTIVE_MARKER}\n\n"
        "---\n\n"
        "## Evaluated\n\n"
        "<!-- Scored jobs appear here after running eval.py -->\n"
    )


def append_to_pipeline(jobs: list):
    init_pipeline()
    content = Path(PIPELINE_FILE).read_text()

    if PIPELINE_ACTIVE_MARKER not in content:
        content = content.replace("## Active\n", f"## Active\n\n{PIPELINE_ACTIVE_MARKER}\n")

    entries = []
    for job in jobs:
        remote_badge = " `remote`" if job.get("remote") else ""
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry = (
            f"- [ ] **[{job['title']} at {job['company']}]({job['url']})**{remote_badge}\n"
            f"  `{job['source']}` · {job['location'] or 'Unknown'} · {job['age_days']:.0f}d old · {date_str}\n"
        )
        entries.append(entry)

    new_block = "\n".join(entries)
    content = content.replace(PIPELINE_ACTIVE_MARKER, PIPELINE_ACTIVE_MARKER + "\n\n" + new_block)
    Path(PIPELINE_FILE).write_text(content)


def run_source(name, fn, *args, **kwargs):
    try:
        jobs = fn(*args, **kwargs)
        print(f"  [{name:20s}] {len(jobs):4d} raw")
        return jobs
    except Exception as e:
        print(f"  [{name:20s}] ERROR: {e}")
        return []


def main():
    print(f"=== Jobscan Germany · {datetime.now().strftime('%Y-%m-%d %H:%M')} ===\n")

    config = load_config()
    max_age = config.get("max_age_days", 5)
    seen_urls = load_history()

    print(f"History: {len(seen_urls)} previously seen jobs\n")
    print("Fetching from sources...")

    all_jobs = []

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {}

        adzuna_cfg = config.get("adzuna", {})
        adzuna_queries = config.get("adzuna_queries", [])
        if adzuna_queries and adzuna_cfg.get("app_id"):
            futures[pool.submit(run_source, "adzuna", adzuna.fetch_jobs,
                                adzuna_queries, adzuna_cfg["app_id"], adzuna_cfg["app_key"], max_age)] = "adzuna"

        arbeitnow_queries = config.get("arbeitnow_queries", [])
        if arbeitnow_queries:
            futures[pool.submit(run_source, "arbeitnow", arbeitnow.fetch_jobs,
                                arbeitnow_queries, max_age)] = "arbeitnow"

        futures[pool.submit(run_source, "remoteok", remoteok.fetch_jobs,
                            config.get("remote_tags", []), max(max_age, 7))] = "remoteok"

        futures[pool.submit(run_source, "remotive", remotive.fetch_jobs,
                            config.get("remotive_categories", ["software-dev", "data"]),
                            max(max_age, 7))] = "remotive"

        futures[pool.submit(run_source, "weworkremotely", weworkremotely.fetch_jobs,
                            config.get("wwr_categories", ["programming", "data"]),
                            max(max_age, 7))] = "weworkremotely"

        for future in as_completed(futures):
            all_jobs.extend(future.result())

    print(f"\nTotal raw: {len(all_jobs)}")

    # Filter + deduplicate
    new_jobs = []
    filter_stats: dict = {}
    seen_in_batch: set = set()

    for job in all_jobs:
        url = normalize_url(job.get("url", ""))
        if not url:
            continue

        if url in seen_urls or url in seen_in_batch:
            filter_stats["duplicate"] = filter_stats.get("duplicate", 0) + 1
            continue
        seen_in_batch.add(url)

        passed, reason = passes_filters(job, config)
        if not passed:
            filter_stats[reason] = filter_stats.get(reason, 0) + 1
            continue

        job["url"] = url
        new_jobs.append(job)

    print(f"New after dedup + filter: {len(new_jobs)}")

    if filter_stats:
        print("\nFiltered out:")
        for reason, count in sorted(filter_stats.items(), key=lambda x: -x[1]):
            print(f"  {count:4d}  {reason}")

    if new_jobs:
        print(f"\nWriting {len(new_jobs)} jobs to pipeline.md ...")
        append_to_pipeline(new_jobs)
        save_history(new_jobs)
        update_cache(new_jobs)
        print("Done. Run `python eval.py` to score them with Claude.")
    else:
        print("\nNo new jobs found.")


if __name__ == "__main__":
    main()
