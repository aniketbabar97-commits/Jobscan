#!/usr/bin/env python3
"""
eval.py — Score pending jobs in pipeline.md against your CV using Claude.
One API call per job. Reads cached descriptions from job_cache.json when available.

Usage: python eval.py
       python eval.py --dry-run   (show jobs without calling Claude)
       python eval.py --limit 10  (evaluate at most 10 jobs)
"""

import json
import os
import re
import sys
import time
import argparse
import requests
from pathlib import Path

import yaml

try:
    import anthropic
except ImportError:
    sys.exit("Error: anthropic package not installed.\nRun: pip install anthropic")

CONFIG_FILE = "config.yml"
PIPELINE_FILE = "pipeline.md"
CV_FILE = "cv.md"
CACHE_FILE = "job_cache.json"

PENDING_RE = re.compile(r"^(- \[ \] \*\*\[)(.+?)\]\((.+?)\)(\*\*.*)$")


def load_config() -> dict:
    if not Path(CONFIG_FILE).exists():
        sys.exit(f"Error: {CONFIG_FILE} not found.")
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


def load_cv() -> str:
    if not Path(CV_FILE).exists():
        sys.exit(
            "Error: cv.md not found.\n"
            "Create cv.md with your resume in markdown format.\n"
            "Tip: pandoc resume.pdf -o cv.md  (if you have pandoc installed)"
        )
    return Path(CV_FILE).read_text()


def load_cache() -> dict:
    if Path(CACHE_FILE).exists():
        return json.loads(Path(CACHE_FILE).read_text())
    return {}


def parse_pending(pipeline_content: str) -> list:
    """Extract all unchecked jobs from pipeline.md."""
    jobs = []
    lines = pipeline_content.splitlines()
    for i, line in enumerate(lines):
        m = PENDING_RE.match(line)
        if not m:
            continue
        link_text = m.group(2).strip()  # "Title at Company"
        url = m.group(3).strip()
        # Split on last " at " to handle company names containing "at"
        if " at " in link_text:
            title, company = link_text.rsplit(" at ", 1)
        else:
            title, company = link_text, ""
        meta = lines[i + 1].strip() if i + 1 < len(lines) else ""
        jobs.append({"title": title.strip(), "company": company.strip(),
                     "url": url, "meta": meta, "original_line": line})
    return jobs


def fetch_description(url: str) -> str:
    """Fetch and strip HTML from a job page."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JobScan Germany/1.0)"}
        resp = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
        if resp.status_code != 200:
            return ""
        text = resp.text
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:4000]
    except Exception:
        return ""


def evaluate(client, cv: str, job: dict, description: str, model: str) -> dict:
    desc_text = description if description else "[Description unavailable — evaluate from title/company only]"
    prompt = f"""You are evaluating job-CV fit. Reply with a JSON object only.

CV:
{cv[:3000]}

JOB:
Title: {job['title']}
Company: {job['company']}
Description:
{desc_text[:3000]}

Return exactly this JSON (no extra text):
{{"score": <0.0-5.0>, "fit": "<yes|no>", "reason": "<one sentence, max 20 words>"}}

Score guide: 5=perfect, 4=strong, 3=decent, 2=stretch, 1=weak, 0=unrelated.
Set fit="yes" when score >= 3.5, otherwise fit="no"."""

    try:
        msg = client.messages.create(
            model=model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            return {
                "score": float(data.get("score", 0)),
                "fit": data.get("fit", "no").lower(),
                "reason": data.get("reason", ""),
            }
    except Exception as e:
        print(f"    Claude error: {e}")

    return {"score": 0.0, "fit": "no", "reason": "evaluation failed"}


def update_pipeline(content: str, job: dict, score: float, fit: str, reason: str) -> str:
    icon = "✓" if fit == "yes" else "✗"
    new_line = job["original_line"].replace("- [ ] ", "- [x] ").rstrip()
    new_line += f" — **{score:.1f} {icon}**"
    content = content.replace(job["original_line"], new_line)
    if job["meta"] and job["meta"] in content:
        label = "YES" if fit == "yes" else "NO"
        content = content.replace(job["meta"], job["meta"] + f"\n  > **{label}**: {reason}")
    return content


def main():
    parser = argparse.ArgumentParser(description="Evaluate pending jobs with Claude")
    parser.add_argument("--dry-run", action="store_true", help="List pending jobs without calling Claude")
    parser.add_argument("--limit", type=int, default=0, help="Max jobs to evaluate (0 = all)")
    args = parser.parse_args()

    print(f"=== Jobscan Evaluator ===\n")

    config = load_config()
    cv = load_cv()
    cache = load_cache()

    if not Path(PIPELINE_FILE).exists():
        sys.exit("No pipeline.md found. Run scan.py first.")

    pipeline = Path(PIPELINE_FILE).read_text()
    pending = parse_pending(pipeline)

    print(f"Pending jobs: {len(pending)}")
    if not pending:
        print("Nothing to evaluate.")
        return

    if args.dry_run:
        for i, job in enumerate(pending, 1):
            print(f"  {i:3d}. {job['title']} at {job['company']}")
            print(f"       {job['url']}")
        return

    api_key = config.get("anthropic", {}).get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit(
            "Error: Anthropic API key not found.\n"
            "Set the ANTHROPIC_API_KEY environment variable, or add it to config.yml under anthropic.api_key"
        )

    model = config.get("anthropic", {}).get("model", "claude-haiku-4-5-20251001")
    threshold = config.get("score_threshold", 3.5)
    client = anthropic.Anthropic(api_key=api_key)

    print(f"Model: {model}  |  Threshold: {threshold}\n")

    to_eval = pending[: args.limit] if args.limit else pending
    yes_count = no_count = 0

    for i, job in enumerate(to_eval, 1):
        print(f"[{i}/{len(to_eval)}] {job['title']} at {job['company']}")

        # Use cached description if available, else fetch
        norm_url = job["url"]
        description = cache.get(norm_url, "")
        if not description:
            description = fetch_description(job["url"])
            if description:
                print(f"  Fetched description ({len(description)} chars)")
            else:
                print(f"  No description available, using title only")
        else:
            print(f"  Using cached description ({len(description)} chars)")

        result = evaluate(client, cv, job, description, model)
        score, fit, reason = result["score"], result["fit"], result["reason"]

        icon = "✓" if fit == "yes" else "✗"
        print(f"  Score: {score:.1f} {icon}  {reason}\n")

        (yes_count if fit == "yes" else no_count).__class__  # just for type hint
        if fit == "yes":
            yes_count += 1
        else:
            no_count += 1

        pipeline = update_pipeline(pipeline, job, score, fit, reason)

        # Write after each job so partial progress is saved
        Path(PIPELINE_FILE).write_text(pipeline)

        # Brief pause to avoid rate-limit bursts
        if i < len(to_eval):
            time.sleep(0.5)

    print(f"--- Summary ---")
    print(f"Evaluated : {len(to_eval)}")
    print(f"Yes (≥{threshold}) : {yes_count}")
    print(f"No  (<{threshold}) : {no_count}")
    print(f"\nOpen pipeline.md to review your shortlist.")


if __name__ == "__main__":
    main()
