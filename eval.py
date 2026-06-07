#!/usr/bin/env python3
"""
eval.py — Score pending jobs against Kranti's CV using Groq (free LLM).

Usage:
  python eval.py                   score all pending jobs (quick 0-5 + reason)
  python eval.py --deep            also generate full career-ops style reports for yes-fits
  python eval.py --dry-run         list pending jobs without calling AI
  python eval.py --limit 20        evaluate at most N jobs
"""

import json
import os
import re
import sys
import time
import argparse
import requests
from pathlib import Path
from datetime import datetime, timezone

import yaml

try:
    from groq import Groq
except ImportError:
    sys.exit("Error: groq package not installed.\nRun: pip install groq")

CONFIG_FILE  = "config.yml"
PIPELINE_FILE = "pipeline.md"
CV_FILE       = "cv.md"
CACHE_FILE    = "job_cache.json"
REPORTS_DIR   = Path("reports")

PENDING_RE = re.compile(r"^(- \[ \] \*\*\[)(.+?)\]\((.+?)\)(\*\*.*)$")


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


def parse_pending(content):
    jobs, lines = [], content.splitlines()
    for i, line in enumerate(lines):
        m = PENDING_RE.match(line)
        if not m:
            continue
        link_text, url = m.group(2).strip(), m.group(3).strip()
        title, company = (link_text.rsplit(" at ", 1) if " at " in link_text else (link_text, ""))
        meta = lines[i + 1].strip() if i + 1 < len(lines) else ""
        jobs.append({"title": title.strip(), "company": company.strip(),
                     "url": url, "meta": meta, "original_line": line})
    return jobs


def fetch_description(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JobScan/1.0)"}
        resp = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
        if resp.status_code != 200:
            return ""
        text = resp.text
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>",  " ", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()[:4000]
    except Exception:
        return ""


# ── Quick evaluation (always runs) ───────────────────────────────────────────

QUICK_PROMPT = """Evaluate job-CV fit. Reply with JSON only — no text outside the JSON object.

CV:
{cv}

JOB:
Title: {title}
Company: {company}
Description:
{desc}

Return exactly:
{{"score": <0.0-5.0>, "fit": "<yes|no>", "reason": "<one sentence, max 20 words>"}}

Score guide: 5=perfect, 4=strong, 3=decent, 2=stretch, 1=weak, 0=wrong field.
fit="yes" when score >= 3.5, else fit="no"."""


def quick_eval(client, cv, job, description, model):
    prompt = QUICK_PROMPT.format(
        cv=cv[:2500], title=job["title"], company=job["company"],
        desc=(description or "[no description]")[:2500],
    )
    try:
        resp = client.chat.completions.create(
            model=model, max_tokens=150, temperature=0.1,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content.strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            d = json.loads(m.group())
            return {"score": float(d.get("score", 0)),
                    "fit": d.get("fit", "no").lower(),
                    "reason": d.get("reason", "")}
    except Exception as e:
        print(f"    Groq error (quick): {e}")
    return {"score": 0.0, "fit": "no", "reason": "evaluation failed"}


# ── Deep evaluation (career-ops A–G style, opt-in with --deep) ───────────────

DEEP_PROMPT = """You are a senior career coach writing a structured evaluation for Kranti Chavan,
a SAP Commerce Cloud / Hybris Developer (5+ years, Karlsruhe Germany, open to remote).

CV:
{cv}

JOB:
Title: {title}
Company: {company}
Location: {location}
Description:
{desc}

Write a structured markdown evaluation. Be specific — quote exact CV evidence and exact JD requirements.

## Quick Verdict
**Score: X.X / 5.0** | **FIT: YES / NO**
One sentence summary.

## A — Role Overview
What archetype is this role? (SAP specialist / Java generalist / SAP consulting / DevOps / other)
How well does the core tech stack align with Kranti's skills?

## B — Requirements Match

| Requirement (from JD) | Kranti's Evidence (from CV) | Match |
|---|---|---|
| [requirement 1] | [evidence or "Not found"] | ✓ Strong / ~ Partial / ✗ Gap |
| [requirement 2] | ... | ... |
| [requirement 3] | ... | ... |
| [requirement 4] | ... | ... |
| [requirement 5] | ... | ... |

List at least 5 key requirements from the JD. Be honest about gaps.

## C — Positioning Strategy
In 2–3 sentences: the angle Kranti should lead with for this specific role.
What makes her stand out vs. a typical applicant?
What framing should she use in her cover letter opening?

## D — Compensation & Market
Based on the JD (if salary mentioned) and Germany market rates for this role/seniority:
- Estimated range for this role in Germany: €X–€Y gross/year
- Is the role above / at / below market for Kranti's level?
- Any red flags (equity-only, unpaid trial, vague comp)?
If salary not mentioned, estimate from role/company size/location.

## E — Red Flags & Personalisation
Any ghost job signals, vague JD, unrealistic requirements, seniority mismatch, or location concerns?
Also: 2 specific LinkedIn outreach hooks for this company/role.
If no red flags: "No significant red flags."

## F — Interview STAR Stories
2 stories from Kranti's experience that directly address key JD requirements.
**[Story title]**
- S (Situation): ...
- T (Task): ...
- A (Action): ...
- R (Result): ...

## G — CV Tweaks for This Role
Top 3 specific, actionable changes to tailor Kranti's CV for this application.
1. ...
2. ...
3. ..."""


def deep_eval(client, cv, job, description, model):
    location = job.get("location", "")
    prompt = DEEP_PROMPT.format(
        cv=cv[:2500], title=job["title"], company=job["company"],
        location=location, desc=(description or "[no description]")[:3000],
    )
    try:
        resp = client.chat.completions.create(
            model=model, max_tokens=2000, temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"    Groq error (deep): {e}")
        return None


def save_report(job, report_content, index):
    REPORTS_DIR.mkdir(exist_ok=True)
    slug = re.sub(r"[^\w-]", "-", job["company"].lower())[:30]
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{index:03d}-{slug}-{date}.md"
    path = REPORTS_DIR / filename
    header = f"# Evaluation: {job['title']} at {job['company']}\n\n**URL:** {job['url']}\n\n---\n\n"
    path.write_text(header + report_content)
    return str(path)


# ── Pipeline update ───────────────────────────────────────────────────────────

def update_pipeline(content, job, score, fit, reason, report_path=None):
    icon = "✓" if fit == "yes" else "✗"
    new_line = job["original_line"].replace("- [ ] ", "- [x] ").rstrip()
    new_line += f" — **{score:.1f} {icon}**"
    content = content.replace(job["original_line"], new_line)
    if job["meta"] and job["meta"] in content:
        label = "YES" if fit == "yes" else "NO"
        suffix = f" · [📄 report]({report_path})" if report_path else ""
        content = content.replace(
            job["meta"],
            job["meta"] + f"\n  > **{label}**: {reason}{suffix}"
        )
    return content


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Evaluate pending jobs with Groq LLM")
    parser.add_argument("--deep",    action="store_true", help="Generate full career-ops style reports for yes-fit jobs")
    parser.add_argument("--dry-run", action="store_true", help="List pending jobs without calling AI")
    parser.add_argument("--limit",   type=int, default=0, help="Max jobs to evaluate (0 = all)")
    args = parser.parse_args()

    print("=== Jobscan Evaluator" + (" [DEEP MODE]" if args.deep else "") + " ===\n")

    config  = load_config()
    cv      = load_cv()
    cache   = load_cache()

    if not Path(PIPELINE_FILE).exists():
        sys.exit("No pipeline.md found. Run scan.py first.")

    pipeline = Path(PIPELINE_FILE).read_text()
    pending  = parse_pending(pipeline)

    print(f"Pending jobs: {len(pending)}")
    if not pending:
        print("Nothing to evaluate.")
        return

    if args.dry_run:
        for i, job in enumerate(pending, 1):
            print(f"  {i:3d}. {job['title']} at {job['company']}\n       {job['url']}")
        return

    api_key = config.get("groq", {}).get("api_key") or os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("Error: Groq API key not found.\nSet GROQ_API_KEY or add to config.yml under groq.api_key")

    model     = config.get("groq", {}).get("model", "llama-3.3-70b-versatile")
    threshold = config.get("score_threshold", 3.5)
    client    = Groq(api_key=api_key)

    print(f"Model: {model}  |  Threshold: {threshold}  |  Deep reports: {args.deep}\n")

    to_eval = pending[: args.limit] if args.limit else pending
    yes_count = no_count = report_count = 0

    for i, job in enumerate(to_eval, 1):
        print(f"[{i}/{len(to_eval)}] {job['title']} at {job['company']}")

        description = cache.get(job["url"], "") or fetch_description(job["url"])
        print(f"  Description: {'cached' if job['url'] in cache else 'fetched'} ({len(description)} chars)")

        result = quick_eval(client, cv, job, description, model)
        score, fit, reason = result["score"], result["fit"], result["reason"]
        icon = "✓" if fit == "yes" else "✗"
        print(f"  Quick score: {score:.1f} {icon}  {reason}")

        report_path = None
        if args.deep and fit == "yes":
            print("  Generating deep report…")
            report_md = deep_eval(client, cv, job, description, model)
            if report_md:
                report_path = save_report(job, report_md, i)
                report_count += 1
                print(f"  Report saved → {report_path}")

        if fit == "yes":
            yes_count += 1
        else:
            no_count += 1

        pipeline = update_pipeline(pipeline, job, score, fit, reason, report_path)
        Path(PIPELINE_FILE).write_text(pipeline)

        print()
        if i < len(to_eval):
            time.sleep(0.4)

    print("--- Summary ---")
    print(f"Evaluated  : {len(to_eval)}")
    print(f"Yes (≥{threshold}) : {yes_count}")
    print(f"No  (<{threshold}) : {no_count}")
    if args.deep:
        print(f"Reports    : {report_count} saved to reports/")
    print(f"\nRun `python export.py` to update the web dashboard.")


if __name__ == "__main__":
    main()
