"""Arbeitnow API — Germany/Europe focused, completely free, no key needed."""

import sys
import time
import requests

BASE_URL = "https://www.arbeitnow.com/api/job-board-api"


def fetch_jobs(queries: list, max_age_days: int = 5) -> list:
    jobs = []
    for query in queries:
        _fetch_query(jobs, query, max_age_days)
    return jobs


def _fetch_query(jobs, query, max_age_days):
    now = time.time()
    for page in range(1, 4):
        try:
            resp = requests.get(BASE_URL, params={"search": query, "page": page}, timeout=15)
            if resp.status_code != 200:
                break

            listings = resp.json().get("data", [])
            if not listings:
                break

            found_fresh = False
            for job in listings:
                created_at = job.get("created_at", 0)
                age_days = (now - float(created_at)) / 86400 if created_at else 999
                if age_days > max_age_days:
                    continue

                found_fresh = True
                remote = bool(job.get("remote", False))
                location = job.get("location", "").strip()

                jobs.append({
                    "title": job.get("title", "").strip(),
                    "company": job.get("company_name", "").strip(),
                    "location": "Remote" if remote else location,
                    "url": job.get("url", ""),
                    "description": job.get("description", "")[:2000],
                    "age_days": round(age_days, 1),
                    "source": "arbeitnow",
                    "remote": remote or "remote" in location.lower(),
                })

            if not found_fresh:
                break

            time.sleep(0.3)

        except Exception as e:
            print(f"[arbeitnow] Error (page {page}): {e}", file=sys.stderr)
            break
