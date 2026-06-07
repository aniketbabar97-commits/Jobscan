#!/usr/bin/env python3
"""
eval.py — Score pending jobs in pipeline.md against your CV using Groq (free LLM API).
One API call per job. Uses job_cache.json for descriptions saved during scan.

Usage: python eval.py
       python eval.py --dry-run      (list pending jobs without calling AI)
       python eval.py --limit 20     (evaluate at most N jobs)
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
    from groq import Groq
except ImportError:
    sys.exit("Error: groq package not installed.\nRun: pip install groq")

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
            "Create cv.md with your resume in markdown format."
        )
    return Path(CV_FILE).read_text()


def load_cache() -> dict:
    if Path(CACHE_FILE).exists():
        return json.loads(Path(CACHE_FILE).read_text())
    return {}


def parse_pending(pipeline_content: str) -> list:
    jobs = []
    lines = pipeline_content.splitlines()
    for i, line in enumerate(lines):
        m = PENDING_RE.match(line)
        if not m:
            continue
        link_text = m.group(2).strip()
        url = m.group(3).strip()
        title, company = (link_text.rsplit(" at ", 1) if " at " in link_text else (link_text, ""))
        meta = lines[i + 1].strip() if i + 1 < len(lines) else ""
        jobs.append({"title": title.strip(), "company": company.strip(),
                     "url": url, "meta": meta, "original_line": line})
    return jobs


def fetch_description(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; JobScan/1.0)"}
        resp = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
        if resp.status_code != 200:
            return ""
        text = resp.text
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()[:4000]
    except Exception:
        return ""


def evaluate(client, cv: str, job: dict, description: str, model: str) -> dict:
    desc_text = description or "[Description unavailable — evaluate from title and company only]"
    prompt = f"""You are evaluating job-CV fit. Reply with a JSON object ONLY — no explanation outside JSON.

CV:
{cv[:3000]}

JOB:
Title: {job['title']}
Company: {job['company']}
Description:
{desc_text[:3000]}

Return exactly this JSON (no extra text):
{{"score": <0.0-5.0>, "fit": "<yes|no>", "reason": "<one sentence, max 20 words>"}}

Score guide: 5=perfect match, 4=strong, 3=decent, 2=stretch, 1=weak, 0=wrong field.
Set fit="yes" when score >= 3.5, otherwise fit="no"."""

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.1,
        )
        text = completion.choices[0].message.content.strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            return {
                "score": float(data.get("score", 0)),
                "fit": data.get("fit", "no").lower(),
                "reason": data.get("reason", ""),
            }
    except Exception as e:
        print(f"    Groq error: {e}")

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
    parser = argparse.ArgumentParser(description="Evaluate pending jobs with Groq LLM")
    parser.add_argument("--dry-run", action="store_true", help="List pending jobs without calling AI")
    parser.add_argument("--limit", type=int, default=0, help="Max jobs to evaluate (0 = all)")
    args = parser.parse_args()

    print("=== Jobscan Evaluator (Groq) ===\n")

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

    api_key = config.get("groq", {}).get("api_key") or os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit(
            "Error: Groq API key not found.\n"
            "Get a free key at https://console.groq.com\n"
            "Then set GROQ_API_KEY env var or add to config.yml under groq.api_key"
        )

    model = config.get("groq", {}).get("model", "llama-3.3-70b-versatile")
    threshold = config.get("score_threshold", 3.5)
    client = Groq(api_key=api_key)

    print(f"Model: {model}  |  Threshold: {threshold}\n")

    to_eval = pending[: args.limit] if args.limit else pending
    yes_count = no_count = 0

    for i, job in enumerate(to_eval, 1):
        print(f"[{i}/{len(to_eval)}] {job['title']} at {job['company']}")

        description = cache.get(job["url"], "")
        if not description:
            description = fetch_description(job["url"])
            status = f"fetched ({len(description)} chars)" if description else "no description"
        else:
            status = f"cached ({len(description)} chars)"
        print(f"  Description: {status}")

        result = evaluate(client, cv, job, description, model)
        score, fit, reason = result["score"], result["fit"], result["reason"]
        icon = "✓" if fit == "yes" else "✗"
        print(f"  Score: {score:.1f} {icon}  {reason}\n")

        if fit == "yes":
            yes_count += 1
        else:
            no_count += 1

        pipeline = update_pipeline(pipeline, job, score, fit, reason)
        Path(PIPELINE_FILE).write_text(pipeline)

        if i < len(to_eval):
            time.sleep(0.3)

    print("--- Summary ---")
    print(f"Evaluated : {len(to_eval)}")
    print(f"Yes (≥{threshold}) : {yes_count}")
    print(f"No  (<{threshold}) : {no_count}")
    print(f"\nOpen pipeline.md or run the dashboard to review results.")


if __name__ == "__main__":
    main()
