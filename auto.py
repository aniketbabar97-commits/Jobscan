#!/usr/bin/env python3
"""
auto.py — Auto-pipeline: paste a job URL and get everything in one shot.

Runs in order:
  1. Fetch job description
  2. Quick score (0–5) against your CV
  3. If score ≥ threshold: full A-G deep report + tailored HTML resume + tracker entry
  4. Print summary with file paths

Usage:
  python auto.py <job_url>
  python auto.py --url <url> --title "SAP Hybris Dev" --company "Valtech"
  python auto.py --url <url> --force       # generate report even if score < threshold
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

try:
    from groq import Groq
except ImportError:
    sys.exit("Error: pip install groq")

# Import shared utilities from sibling modules
sys.path.insert(0, str(Path(__file__).parent))
from eval   import quick_eval, deep_eval, save_report
from resume import generate_resume_html, save_resume, fetch_description as _fetch

CONFIG_FILE  = "config.yml"
CV_FILE      = "cv.md"
TRACKER_FILE = "applications.tsv"
CACHE_FILE   = "job_cache.json"


def load_config():
    if not Path(CONFIG_FILE).exists():
        sys.exit(f"Error: {CONFIG_FILE} not found.")
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


def load_cv():
    if not Path(CV_FILE).exists():
        sys.exit("Error: cv.md not found.")
    return Path(CV_FILE).read_text()


def load_cache():
    return json.loads(Path(CACHE_FILE).read_text()) if Path(CACHE_FILE).exists() else {}


def add_to_tracker(title, company, url, score):
    exists = Path(TRACKER_FILE).exists()
    rows = []
    if exists:
        with open(TRACKER_FILE) as f:
            for line in f:
                rows.append(line.rstrip("\n"))

    # Check duplicate
    data_rows = [r for r in rows if r and not r.startswith("#")]
    for row in data_rows:
        parts = row.split("\t")
        if len(parts) >= 7 and parts[6] == url:
            return int(parts[0])  # already tracked

    next_id   = len(data_rows) + 1
    date      = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    score_str = f"{score:.1f}" if score is not None else ""
    new_row   = "\t".join([str(next_id), date, company, title, score_str, "Evaluated", url])

    with open(TRACKER_FILE, "a") as f:
        if not exists:
            f.write("#\tdate\tcompany\trole\tscore\tstatus\turl\n")
        f.write(new_row + "\n")
    return next_id


DIVIDER = "─" * 55


def main():
    parser = argparse.ArgumentParser(description="Auto-pipeline: URL → score + report + resume")
    parser.add_argument("url",      nargs="?",     help="Job URL")
    parser.add_argument("--url",    dest="url_opt")
    parser.add_argument("--title",  default="",    help="Job title")
    parser.add_argument("--company",default="",    help="Company name")
    parser.add_argument("--location",default="",   help="Location")
    parser.add_argument("--force",  action="store_true",
                        help="Generate full report even if score below threshold")
    args = parser.parse_args()

    url = args.url or args.url_opt
    if not url:
        parser.error("Provide a job URL: python auto.py <url>")

    print(f"\n{'='*55}")
    print("  Jobscan Auto-Pipeline")
    print(f"{'='*55}\n")

    config = load_config()
    cv     = load_cv()
    cache  = load_cache()

    api_key = config.get("groq", {}).get("api_key") or os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("Error: Groq API key not set.")

    model     = config.get("groq", {}).get("model", "llama-3.3-70b-versatile")
    threshold = config.get("score_threshold", 3.5)
    client    = Groq(api_key=api_key)

    title    = args.title    or "Role"
    company  = args.company  or "Company"
    location = args.location or ""

    # ── Step 1: Fetch description ─────────────────────────────────
    print(f"[1/4] Fetching job description…")
    description = cache.get(url, "") or _fetch(url)
    if description:
        print(f"      {len(description)} chars")
    else:
        print("      Could not fetch — will evaluate without description")

    # ── Step 2: Quick score ───────────────────────────────────────
    print(f"\n[2/4] Quick evaluation…")
    job = {"title": title, "company": company, "url": url,
           "location": location, "meta": "", "original_line": ""}
    result = quick_eval(client, cv, job, description, model)
    score, fit, reason = result["score"], result["fit"], result["reason"]
    icon = "✓" if fit == "yes" else "✗"

    print(f"\n  {DIVIDER}")
    print(f"  Score:  {score:.1f} / 5.0  {icon}  {'GOOD FIT' if fit == 'yes' else 'NOT A FIT'}")
    print(f"  Reason: {reason}")
    print(f"  {DIVIDER}\n")

    should_go_deep = fit == "yes" or args.force
    if not should_go_deep:
        entry_id = add_to_tracker(title, company, url, score)
        print(f"  Score below threshold ({threshold}). Skipping deep report.")
        print(f"  Added to tracker as #{entry_id} (status: Evaluated)")
        print(f"\n  Use --force to generate the full report anyway.")
        return

    report_path = None
    resume_path = None

    # ── Step 3: Deep report ───────────────────────────────────────
    print(f"[3/4] Generating deep A-G report…")
    report_md = deep_eval(client, cv, job, description, model)
    if report_md:
        # Use a simple index based on existing reports
        existing = list(Path("reports").glob("*.md")) if Path("reports").exists() else []
        idx = len(existing) + 1
        report_path = save_report(job, report_md, idx)
        print(f"      Saved → {report_path}")
    else:
        print("      Deep eval failed — skipping report")

    time.sleep(0.5)

    # ── Step 4: Tailored HTML resume ──────────────────────────────
    print(f"\n[4/4] Generating tailored HTML resume…")
    try:
        html = generate_resume_html(client, cv, title, company, description, model)
        resume_path = save_resume(html, company, title)
        print(f"      Saved → {resume_path}")
    except Exception as e:
        print(f"      Resume generation failed: {e}")

    # ── Tracker ───────────────────────────────────────────────────
    entry_id = add_to_tracker(title, company, url, score)

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n{'='*55}")
    print(f"  DONE — {title} at {company}")
    print(f"{'='*55}")
    print(f"  Score      : {score:.1f} / 5.0  {icon}")
    print(f"  Reason     : {reason}")
    if report_path:
        print(f"  Report     : {report_path}")
    if resume_path:
        print(f"  Resume     : {resume_path}")
    print(f"  Tracker    : #{entry_id} (Evaluated)")
    print()
    print("  Next steps:")
    print(f"    1. Read the report:  {report_path or 'reports/ folder'}")
    print(f"    2. Open resume in browser → Print → Save as PDF")
    print(f"       {resume_path or 'output/ folder'}")
    print(f"    3. Apply at: {url}")
    print(f"    4. python tracker.py update \"{url}\" Applied")
    print()


if __name__ == "__main__":
    main()
