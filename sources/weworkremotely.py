"""WeWorkRemotely — remote jobs via RSS feeds, no key needed."""

import re
import sys
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

FEEDS = {
    "programming": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "devops": "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    "data": "https://weworkremotely.com/categories/remote-data-science-jobs.rss",
}


def fetch_jobs(categories: list = None, max_age_days: int = 7) -> list:
    feeds = {k: v for k, v in FEEDS.items() if not categories or k in categories}
    jobs = []
    for cat, url in feeds.items():
        _fetch_feed(jobs, cat, url, max_age_days)
    return jobs


def _fetch_feed(jobs, category, feed_url, max_age_days):
    try:
        resp = requests.get(feed_url, headers={"User-Agent": "JobScan Germany/1.0"}, timeout=15)
        if resp.status_code != 200:
            return

        root = ET.fromstring(resp.content)
        now = datetime.now().astimezone()

        for item in root.findall(".//item"):
            raw_title = item.findtext("title", "")
            # WWR format: "Category: Company: Job Title"
            parts = raw_title.split(": ", 2)
            if len(parts) >= 3:
                company, title = parts[1].strip(), parts[2].strip()
            elif len(parts) == 2:
                company, title = parts[0].strip(), parts[1].strip()
            else:
                company, title = "", raw_title.strip()

            url = item.findtext("link") or item.findtext("guid") or ""

            pub_text = item.findtext("pubDate", "")
            age_days = 999.0
            if pub_text:
                try:
                    dt = parsedate_to_datetime(pub_text)
                    age_days = float((now - dt).days)
                except Exception:
                    pass

            if age_days > max_age_days or not title:
                continue

            desc = _strip_html(item.findtext("description", ""))[:2000]

            jobs.append({
                "title": title,
                "company": company,
                "location": "Remote",
                "url": url,
                "description": desc,
                "age_days": age_days,
                "source": "weworkremotely",
                "remote": True,
            })

    except Exception as e:
        print(f"[weworkremotely] Error ({category}): {e}", file=sys.stderr)


def _strip_html(text):
    return re.sub(r"<[^>]+>", " ", text or "")
