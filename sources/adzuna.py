"""Adzuna Germany job API client. Free tier: developer.adzuna.com"""

import sys
import requests
from datetime import datetime, timezone

BASE_URL = "https://api.adzuna.com/v1/api/jobs/de/search"


def fetch_jobs(queries: list, app_id: str, app_key: str, max_age_days: int = 5) -> list:
    if not app_id or not app_key:
        print("[adzuna] No credentials — skipping", file=sys.stderr)
        return []
    jobs = []
    for item in queries:
        _fetch_query(jobs, item.get("query", ""), item.get("location", ""), app_id, app_key, max_age_days)
    return jobs


def _fetch_query(jobs, query, location, app_id, app_key, max_age_days):
    for page in range(1, 6):
        try:
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "results_per_page": 50,
                "what": query,
                "max_days_old": max_age_days,
                "sort_by": "date",
                "content-type": "application/json",
            }
            if location:
                params["where"] = location

            resp = requests.get(f"{BASE_URL}/{page}", params=params, timeout=15)
            if resp.status_code != 200:
                break

            results = resp.json().get("results", [])
            if not results:
                break

            for r in results:
                try:
                    dt = datetime.fromisoformat(r.get("created", "").replace("Z", "+00:00"))
                    age_days = (datetime.now(timezone.utc) - dt).days
                except Exception:
                    age_days = max_age_days + 1

                if age_days > max_age_days:
                    continue

                title = r.get("title", "").strip()
                loc = r.get("location", {}).get("display_name", "")
                jobs.append({
                    "title": title,
                    "company": r.get("company", {}).get("display_name", "").strip(),
                    "location": loc,
                    "url": r.get("redirect_url", ""),
                    "description": r.get("description", "")[:2000],
                    "age_days": float(age_days),
                    "source": "adzuna",
                    "remote": "remote" in title.lower() or "remote" in loc.lower(),
                })

        except Exception as e:
            print(f"[adzuna] Error (page {page}): {e}", file=sys.stderr)
            break
