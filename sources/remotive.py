"""Remotive — remote tech jobs, free JSON API, no key needed."""

import re
import sys
import requests
from datetime import datetime, timezone

API_URL = "https://remotive.com/api/remote-jobs"
DEFAULT_CATEGORIES = ["software-dev", "data", "devops-sysadmin"]


def fetch_jobs(categories: list = None, max_age_days: int = 7) -> list:
    jobs = []
    for cat in (categories or DEFAULT_CATEGORIES):
        _fetch_category(jobs, cat, max_age_days)
    return jobs


def _fetch_category(jobs, category, max_age_days):
    try:
        resp = requests.get(API_URL, params={"category": category, "limit": 100}, timeout=15)
        if resp.status_code != 200:
            return

        now = datetime.now(timezone.utc)
        for job in resp.json().get("jobs", []):
            try:
                dt = datetime.fromisoformat(job.get("publication_date", "").replace("Z", "+00:00"))
                age_days = float((now - dt).days)
            except Exception:
                age_days = 999.0

            if age_days > max_age_days:
                continue

            jobs.append({
                "title": job.get("title", "").strip(),
                "company": job.get("company_name", "").strip(),
                "location": job.get("candidate_required_location", "") or "Remote",
                "url": job.get("url", ""),
                "description": _strip_html(job.get("description", ""))[:2000],
                "age_days": age_days,
                "source": "remotive",
                "remote": True,
            })

    except Exception as e:
        print(f"[remotive] Error ({category}): {e}", file=sys.stderr)


def _strip_html(text):
    return re.sub(r"<[^>]+>", " ", text or "")
