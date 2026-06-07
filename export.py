#!/usr/bin/env python3
"""
export.py — Convert pipeline.md → results.json for the Vercel static dashboard.
Run this after eval.py, then git push to update the live site.

Usage: python export.py
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

PIPELINE_FILE = "pipeline.md"
OUTPUT_FILE = "public/results.json"


def parse_jobs(content: str) -> list:
    jobs = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^- \[(.)\] \*\*\[(.+?)\]\((.+?)\)\*\*(.*)$", line)
        if not m:
            i += 1
            continue

        status_char, link_text, url, suffix = m.groups()
        title, company = (link_text.rsplit(" at ", 1) if " at " in link_text else (link_text, ""))
        status = {"x": "evaluated", " ": "pending"}.get(status_char, "other")
        score, fit, reason = None, None, ""

        if status == "evaluated":
            sm = re.search(r"\*\*(\d+\.?\d*)\s*([✓✗])\*\*", suffix)
            if sm:
                score = float(sm.group(1))
                fit = "yes" if sm.group(2) == "✓" else "no"

        source, location = "", ""
        remote = "`remote`" in line or "🌍" in line

        if i + 1 < len(lines):
            meta = lines[i + 1].strip()
            mm = re.match(r"`([^`]+)`\s*·\s*([^·]+)\s*·", meta)
            if mm:
                source, location = mm.group(1).strip(), mm.group(2).strip()

        reason, report_path = "", ""
        if i + 2 < len(lines):
            detail = lines[i + 2].strip()
            rm = re.match(r">\s*\*\*(YES|NO)\*\*:\s*(.+?)(?:\s*·\s*\[📄 report\]\((.+?)\))?$", detail)
            if rm:
                reason = rm.group(2).strip()
                report_path = rm.group(3) or ""

        jobs.append({
            "title": title.strip(), "company": company.strip(), "url": url,
            "status": status, "score": score, "fit": fit,
            "source": source, "location": location,
            "remote": remote, "reason": reason, "report": report_path,
        })
        i += 1

    return jobs


def main():
    if not Path(PIPELINE_FILE).exists():
        print("No pipeline.md found. Run scan.py first.")
        return

    jobs = parse_jobs(Path(PIPELINE_FILE).read_text())
    yes_jobs = [j for j in jobs if j["fit"] == "yes"]
    no_jobs = [j for j in jobs if j["fit"] == "no"]
    pending_jobs = [j for j in jobs if j["status"] == "pending"]

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total": len(jobs),
            "yes": len(yes_jobs),
            "no": len(no_jobs),
            "pending": len(pending_jobs),
        },
        "jobs": sorted(jobs, key=lambda j: (j["score"] or -1), reverse=True),
    }

    Path("public").mkdir(exist_ok=True)
    Path(OUTPUT_FILE).write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(f"Exported {len(jobs)} jobs → {OUTPUT_FILE}")
    print(f"  ✓ Yes: {len(yes_jobs)}  ⏳ Pending: {len(pending_jobs)}  ✗ No: {len(no_jobs)}")
    print(f"\nNow push to update your Vercel dashboard:")
    print(f"  git add {OUTPUT_FILE} && git commit -m 'Update job results' && git push")


if __name__ == "__main__":
    main()
