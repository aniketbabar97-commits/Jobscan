"""Scan company career pages directly via Greenhouse, Ashby, and Lever public APIs.
No authentication required — all three expose free public job listing endpoints.
"""

import re
import sys
import time
import requests

_HTML_RE = re.compile(r"<[^>]+>")
_GH_RE   = re.compile(r"(?:boards|job-boards)\.greenhouse\.io/([^/?#\s]+)", re.I)
_LV_RE   = re.compile(r"jobs\.lever\.co/([^/?#\s]+)", re.I)
_AB_RE   = re.compile(r"jobs\.ashbyhq\.com/([^/?#\s]+)", re.I)


def detect_ats(url: str) -> tuple:
    """Return (ats_type, slug) from a careers URL, or (None, None)."""
    for pattern, kind in [(_GH_RE, "greenhouse"), (_LV_RE, "lever"), (_AB_RE, "ashby")]:
        m = pattern.search(url or "")
        if m:
            return kind, m.group(1)
    return None, None


def fetch_jobs(companies: list) -> list:
    all_jobs = []
    for company in companies:
        if not company.get("enabled", True):
            continue
        name = company.get("name", "")
        ats  = company.get("ats", "")
        slug = company.get("slug", "")

        if not (ats and slug):
            detected_ats, detected_slug = detect_ats(company.get("careers_url", ""))
            ats  = ats  or detected_ats  or ""
            slug = slug or detected_slug or ""

        if not (ats and slug):
            print(f"[ats] Cannot detect ATS for {name} — skipping", file=sys.stderr)
            continue

        try:
            if ats == "greenhouse":
                jobs = _greenhouse(slug, name)
            elif ats == "lever":
                jobs = _lever(slug, name)
            elif ats == "ashby":
                jobs = _ashby(slug, name)
            else:
                continue
            all_jobs.extend(jobs)
            time.sleep(0.4)
        except Exception as e:
            print(f"[ats] Error scanning {name} ({ats}): {e}", file=sys.stderr)

    return all_jobs


def _greenhouse(slug: str, company: str) -> list:
    resp = requests.get(
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
        timeout=15,
    )
    if resp.status_code != 200:
        return []
    jobs = []
    for j in resp.json().get("jobs", []):
        loc = j.get("location", {})
        location = loc.get("name", "") if isinstance(loc, dict) else str(loc)
        jobs.append(_make_job(
            title=j.get("title", ""),
            company=company,
            location=location,
            url=j.get("absolute_url", ""),
            desc=_strip(j.get("content", "")),
            source="ats-greenhouse",
            remote="remote" in location.lower(),
        ))
    return jobs


def _lever(slug: str, company: str) -> list:
    resp = requests.get(
        f"https://api.lever.co/v0/postings/{slug}?mode=json",
        timeout=15,
    )
    if resp.status_code != 200:
        return []
    jobs = []
    for j in resp.json():
        cats = j.get("categories") or {}
        location = cats.get("location", "") or j.get("workplaceType", "")
        body = j.get("descriptionBody") or {}
        desc = _strip(" ".join(str(v) for v in body.values()) if isinstance(body, dict) else str(body))
        jobs.append(_make_job(
            title=j.get("text", ""),
            company=company,
            location=location,
            url=j.get("hostedUrl", "") or j.get("applyUrl", ""),
            desc=desc,
            source="ats-lever",
            remote="remote" in location.lower(),
        ))
    return jobs


def _ashby(slug: str, company: str) -> list:
    resp = requests.get(
        f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true",
        timeout=15,
    )
    if resp.status_code != 200:
        return []
    jobs = []
    for j in resp.json().get("jobs", []):
        loc = j.get("location") or j.get("locationName") or ""
        if isinstance(loc, dict):
            loc = loc.get("name", "")
        job_url = j.get("jobUrl") or f"https://jobs.ashbyhq.com/{slug}/{j.get('id','')}"
        desc = _strip(j.get("descriptionHtml") or j.get("descriptionPlain") or "")
        jobs.append(_make_job(
            title=j.get("title", ""),
            company=company,
            location=loc,
            url=job_url,
            desc=desc,
            source="ats-ashby",
            remote=bool(j.get("isRemote")) or "remote" in loc.lower(),
        ))
    return jobs


def _make_job(title, company, location, url, desc, source, remote):
    return {
        "title":       title.strip(),
        "company":     company,
        "location":    location,
        "url":         url,
        "description": desc[:2000],
        "age_days":    0.0,
        "source":      source,
        "remote":      remote,
    }


def _strip(text):
    return re.sub(r"\s+", " ", _HTML_RE.sub(" ", text or "")).strip()
