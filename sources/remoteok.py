"""RemoteOK — global remote jobs, free JSON API, no key needed."""

import re
import sys
import time
import requests

API_URL = "https://remoteok.com/api"


def fetch_jobs(tags: list = None, max_age_days: int = 7) -> list:
    jobs = []
    try:
        headers = {"User-Agent": "JobScan Germany/1.0 (job search automation)"}
        resp = requests.get(API_URL, headers=headers, timeout=20)
        if resp.status_code != 200:
            print(f"[remoteok] HTTP {resp.status_code}", file=sys.stderr)
            return []

        data = resp.json()
        listings = [j for j in data if isinstance(j, dict) and j.get("id") and j.get("position")]

        now = time.time()
        tag_set = {t.lower() for t in (tags or [])}

        for job in listings:
            age_days = (now - float(job.get("epoch", now))) / 86400
            if age_days > max_age_days:
                continue

            if tag_set:
                job_tags = {t.lower() for t in job.get("tags", [])}
                if not tag_set.intersection(job_tags):
                    continue

            jobs.append({
                "title": job.get("position", "").strip(),
                "company": job.get("company", "").strip(),
                "location": job.get("location", "") or "Remote",
                "url": job.get("url", ""),
                "description": _strip_html(job.get("description", ""))[:2000],
                "age_days": round(age_days, 1),
                "source": "remoteok",
                "remote": True,
            })

    except Exception as e:
        print(f"[remoteok] Error: {e}", file=sys.stderr)

    return jobs


def _strip_html(text):
    return re.sub(r"<[^>]+>", " ", text or "")
