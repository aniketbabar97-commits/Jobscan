#!/usr/bin/env python3
"""
apply.py — Generate tailored application materials for a specific job.
Adapted from career-ops apply / pdf / contacto modes.

Generates (no fabrication — all content grounded in cv.md):
  • ATS keyword list extracted from the JD
  • Tailored professional summary
  • Top bullet points reworded to match JD terminology
  • Cover letter (3 paragraphs, ~200 words)
  • LinkedIn messages (recruiter / hiring manager / peer) — under 300 chars each
  • Answers to common application form questions

Output saved to: applications/{company-slug}-{YYYY-MM-DD}/materials.md

Usage:
  python apply.py <job_url>
  python apply.py --url <url> --title "SAP Hybris Dev" --company "Acme"
  python apply.py --help
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

CONFIG_FILE = "config.yml"
CV_FILE     = "cv.md"
TRACKER_FILE = "applications.tsv"
APPS_DIR    = Path("applications")

APPLY_PROMPT = """You are a career coach helping Kranti Chavan apply for a job.
All content must be honest and directly grounded in her CV — never fabricate skills or experience.

KRANTI'S CV:
{cv}

JOB:
Title: {title}
Company: {company}
Location: {location}
Description:
{desc}

Generate tailored application materials using EXACTLY these section headers:

## KEYWORDS
12–15 ATS keywords from the JD (comma-separated, exact JD terminology).

## TAILORED SUMMARY
Rewrite Kranti's professional summary (3–4 sentences) for THIS specific role.
Use the JD's exact terminology. Make it specific, not generic.

## TOP BULLETS
4–5 bullet points from Kranti's experience that best match this JD.
Rephrase each to naturally echo the JD's language (honest rephrasing, not fabrication).

## COVER LETTER
3-paragraph cover letter (~200 words total):
Para 1: Why THIS role at THIS company — reference something specific about them.
Para 2: Kranti's strongest matching achievement with a concrete result.
Para 3: Brief close with a call to action.
Sign off: "Kind regards, Kranti Chavan"

## LINKEDIN MESSAGES
Three versions, each strictly under 300 characters:

**To Recruiter:**
[message — lead with role fit, provide screening data, ask for next step]

**To Hiring Manager:**
[message — reference a specific team challenge, showcase matching achievement]

**To Peer:**
[message — acknowledge their work, share common focus, propose a chat — no direct job ask]

## COMMON QUESTIONS
Short answers (2–3 sentences each):
**Why this company?** ...
**Why this role?** ...
**What's your notice period?** [Kranti: fill in your actual notice period]
**Salary expectation?** [Research {company} {title} Germany benchmarks on Glassdoor / Levels.fyi first]
**Are you authorized to work in Germany?** Yes — Kranti is currently based in Karlsruhe, Germany."""


def load_config():
    if not Path(CONFIG_FILE).exists():
        sys.exit(f"Error: {CONFIG_FILE} not found.")
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


def load_cv():
    if not Path(CV_FILE).exists():
        sys.exit("Error: cv.md not found.")
    return Path(CV_FILE).read_text()


def fetch_description(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JobScan/1.0)"}
        resp = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
        if resp.status_code != 200:
            return ""
        text = resp.text
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>",  " ", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()[:5000]
    except Exception as e:
        print(f"  Warning: could not fetch URL ({e})")
        return ""


def generate_materials(client, cv, title, company, location, description, model):
    prompt = APPLY_PROMPT.format(
        cv=cv[:2500], title=title, company=company, location=location,
        desc=(description or "[description not available]")[:3500],
    )
    resp = client.chat.completions.create(
        model=model, max_tokens=3000, temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


def save_materials(title, company, url, content):
    APPS_DIR.mkdir(exist_ok=True)
    slug = re.sub(r"[^\w-]", "-", company.lower())[:25]
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    folder = APPS_DIR / f"{slug}-{date}"
    folder.mkdir(exist_ok=True)

    header = (
        f"# Application: {title} at {company}\n\n"
        f"**URL:** {url}  \n"
        f"**Date:** {date}  \n\n"
        f"---\n\n"
        f"> Review everything below before using. Edit to personalise further.\n\n"
        f"---\n\n"
    )
    out_path = folder / "materials.md"
    out_path.write_text(header + content)
    return str(out_path)


def add_to_tracker(title, company, url, score=None):
    exists = Path(TRACKER_FILE).exists()
    rows = []
    if exists:
        with open(TRACKER_FILE) as f:
            for line in f:
                rows.append(line.rstrip("\n"))
    # Determine next ID
    next_id = len([r for r in rows if r and not r.startswith("#")]) + 1
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    score_str = f"{score:.1f}" if score is not None else ""
    new_row = "\t".join([str(next_id), date, company, title, score_str, "Evaluated", url])
    with open(TRACKER_FILE, "a") as f:
        if not exists:
            f.write("#\tdate\tcompany\trole\tscore\tstatus\turl\n")
        f.write(new_row + "\n")
    return next_id


def main():
    parser = argparse.ArgumentParser(description="Generate tailored application materials")
    parser.add_argument("url", nargs="?", help="Job URL")
    parser.add_argument("--url",     dest="url_opt",  help="Job URL (alternative to positional)")
    parser.add_argument("--title",   default="",      help="Job title (skip fetch if known)")
    parser.add_argument("--company", default="",      help="Company name")
    parser.add_argument("--location",default="",      help="Location")
    args = parser.parse_args()

    url = args.url or args.url_opt
    if not url:
        parser.error("Provide a job URL: python apply.py <url>")

    print("=== Jobscan Apply ===\n")

    config = load_config()
    cv     = load_cv()

    api_key = config.get("groq", {}).get("api_key") or os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("Error: Groq API key not set.")

    model  = config.get("groq", {}).get("model", "llama-3.3-70b-versatile")
    client = Groq(api_key=api_key)

    print(f"Job URL: {url}")
    print("Fetching job description...")
    description = fetch_description(url)
    print(f"  {len(description)} chars fetched")

    # Check job_cache.json for description
    cache_file = Path("job_cache.json")
    if cache_file.exists() and not description:
        cache = json.loads(cache_file.read_text())
        description = cache.get(url, "")
        if description:
            print(f"  Using cached description ({len(description)} chars)")

    title    = args.title    or "Role"
    company  = args.company  or "Company"
    location = args.location or ""

    # Try to parse title/company from URL if not provided
    if not args.title and "greenhouse" in url:
        pass  # could parse but skip for simplicity

    print(f"\nGenerating tailored materials with {model}...")
    print("  (CV keywords · summary · cover letter · LinkedIn messages · form answers)")

    materials = generate_materials(client, cv, title, company, location, description, model)

    out_path = save_materials(title, company, url, materials)
    entry_id = add_to_tracker(title, company, url)

    print(f"\n✓ Materials saved → {out_path}")
    print(f"✓ Added to tracker as #{entry_id} (status: Evaluated)")
    print(f"\nNext steps:")
    print(f"  1. Open {out_path} and review everything")
    print(f"  2. Apply on the company's website (copy-paste from the file)")
    print(f"  3. Run: python tracker.py update \"{url}\" Applied")


if __name__ == "__main__":
    main()
