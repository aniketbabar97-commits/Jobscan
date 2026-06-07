#!/usr/bin/env python3
"""
resume.py — Generate a tailored HTML resume for a specific job.
Uses Groq to rewrite the summary and highlight matching bullets.
Open the output HTML in any browser, then File → Print → Save as PDF.

Usage:
  python resume.py --url <job_url> --title "SAP Hybris Dev" --company "Valtech"
  python resume.py --url <url>  (title/company parsed from URL if omitted)
"""

import argparse
import json
import os
import re
import sys
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
OUTPUT_DIR  = Path("output")

RESUME_PROMPT = """You are tailoring Kranti Chavan's resume for a specific job.
Read her CV and the job description carefully. Rephrase and reorder — NEVER fabricate.

CV:
{cv}

JOB:
Title: {title}
Company: {company}
Description:
{desc}

Return ONLY valid JSON (no markdown fences, no extra text outside the JSON):
{{
  "tagline": "one-line professional tagline tailored to this exact role (max 12 words)",
  "summary": "3-sentence professional summary using this JD's exact terminology. Be specific.",
  "experience": [
    {{
      "company": "company name from CV",
      "title": "job title from CV",
      "period": "date range from CV",
      "bullets": [
        "bullet reordered/reworded to echo JD language (honest only)",
        "bullet 2",
        "bullet 3"
      ]
    }}
  ],
  "skills_featured": ["skill1", "skill2", "skill3", "skill4", "skill5", "skill6", "skill7", "skill8"],
  "keywords": ["keyword from JD that matches CV"]
}}

Rules:
- Include ALL work experience entries from her CV (don't drop any role)
- For each role: keep ALL original bullets but reorder so most JD-relevant come first
- skills_featured: pick 8 skills from her CV that best match this JD (exact names from CV)
- keywords: list the JD tech/skill terms that appear in her CV (for ATS awareness)"""


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{name} — Resume</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.45;
    color: #1a1a1a;
    background: #fff;
    padding: 0.6in 0.7in;
    max-width: 8.5in;
    margin: 0 auto;
  }}
  header {{ border-bottom: 2.5px solid #1e3a5f; padding-bottom: 10px; margin-bottom: 14px; }}
  h1 {{ font-size: 22pt; font-weight: 700; color: #1e3a5f; letter-spacing: -0.5px; }}
  .tagline {{ font-size: 10pt; color: #2563eb; font-weight: 500; margin: 3px 0 6px; }}
  .contact {{ font-size: 9pt; color: #555; }}
  .contact a {{ color: #555; text-decoration: none; }}
  .tailored-badge {{
    display: inline-block; background: #eff6ff; color: #1d4ed8;
    font-size: 8pt; font-weight: 600; padding: 2px 7px; border-radius: 10px;
    border: 1px solid #bfdbfe; margin-left: 8px; vertical-align: middle;
  }}
  h2 {{
    font-size: 10pt; font-weight: 700; text-transform: uppercase;
    letter-spacing: 1.2px; color: #1e3a5f;
    border-bottom: 1px solid #cbd5e1; padding-bottom: 3px;
    margin: 16px 0 8px;
  }}
  .summary {{ font-size: 10pt; color: #222; line-height: 1.55; }}
  .job {{ margin-bottom: 12px; page-break-inside: avoid; }}
  .job-header {{ display: flex; justify-content: space-between; align-items: baseline; }}
  .job-title {{ font-size: 10.5pt; font-weight: 700; color: #1a1a1a; }}
  .job-company {{ font-size: 10pt; color: #374151; }}
  .job-period {{ font-size: 9pt; color: #6b7280; white-space: nowrap; }}
  ul {{ padding-left: 14px; margin: 5px 0 0; }}
  li {{ margin-bottom: 2px; font-size: 10pt; }}
  .skills-grid {{
    display: flex; flex-wrap: wrap; gap: 5px; margin-top: 4px;
  }}
  .skill-tag {{
    background: #f1f5f9; color: #1e3a5f; font-size: 9pt; font-weight: 500;
    padding: 2px 8px; border-radius: 4px; border: 1px solid #e2e8f0;
  }}
  .skill-tag.featured {{
    background: #dbeafe; color: #1d4ed8; border-color: #93c5fd;
  }}
  .keywords-bar {{
    font-size: 8.5pt; color: #6b7280; margin-top: 8px;
  }}
  .keywords-bar strong {{ color: #374151; }}
  .cert-item {{ font-size: 10pt; margin-bottom: 3px; }}
  @media print {{
    body {{ padding: 0; }}
    .no-print {{ display: none; }}
    a {{ color: inherit; text-decoration: none; }}
    .tailored-badge {{ background: #e0e7ff; }}
  }}
</style>
</head>
<body>

<div class="no-print" style="background:#fef3c7;padding:8px 12px;margin-bottom:16px;border-radius:6px;font-size:9pt;color:#92400e;">
  <strong>Review before sending.</strong> Tailored for: <em>{title} at {company}</em>.
  To save as PDF: File → Print → Destination: Save as PDF → A4, margins: Minimum.
</div>

<header>
  <h1>{name} <span class="tailored-badge">Tailored for {company}</span></h1>
  <div class="tagline">{tagline}</div>
  <div class="contact">{contact}</div>
</header>

<h2>Professional Summary</h2>
<p class="summary">{summary}</p>

<h2>Work Experience</h2>
{experience_html}

<h2>Key Skills</h2>
<div class="skills-grid">
{skills_html}
</div>

{education_html}

{certs_html}

<div class="keywords-bar">
  <strong>ATS Keywords matched:</strong> {keywords_str}
</div>

</body>
</html>"""


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
        text = re.sub(r"<script[^>]*>.*?</script>", " ", resp.text, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>",  " ", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()[:5000]
    except Exception as e:
        print(f"  Warning: could not fetch URL ({e})")
        return ""


def extract_cv_meta(cv_text: str):
    """Pull name, contact line, education, and certs from raw cv.md."""
    lines = cv_text.splitlines()
    name = ""
    contact = ""
    edu_lines = []
    cert_lines = []
    section = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") and not name:
            name = stripped.lstrip("# ").strip()
        elif re.search(r"@|linkedin|github|tel:|phone|email|\+\d{2}", stripped, re.I) and not contact:
            contact = stripped
        elif re.match(r"^#{1,3}\s+(education|ausbildung)", stripped, re.I):
            section = "edu"
        elif re.match(r"^#{1,3}\s+(certif|zertif)", stripped, re.I):
            section = "cert"
        elif re.match(r"^#{1,3}\s+", stripped):
            section = None
        elif section == "edu" and stripped:
            edu_lines.append(stripped)
        elif section == "cert" and stripped:
            cert_lines.append(stripped)

    return name or "Kranti Chavan", contact, edu_lines, cert_lines


def call_groq(client, cv, title, company, description, model):
    prompt = RESUME_PROMPT.format(
        cv=cv[:2500], title=title, company=company,
        desc=(description or "[description not available]")[:3000],
    )
    resp = client.chat.completions.create(
        model=model, max_tokens=3500, temperature=0.25,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.choices[0].message.content.strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError("No JSON found in LLM response")
    return json.loads(m.group())


def render_experience(experience: list) -> str:
    parts = []
    for job in experience:
        bullets_html = "\n".join(f"    <li>{b}</li>" for b in job.get("bullets", []))
        parts.append(
            f'<div class="job">'
            f'<div class="job-header">'
            f'<span><span class="job-title">{job.get("title","")}</span>'
            f' · <span class="job-company">{job.get("company","")}</span></span>'
            f'<span class="job-period">{job.get("period","")}</span>'
            f'</div>'
            f'<ul>{bullets_html}</ul>'
            f'</div>'
        )
    return "\n".join(parts)


def render_skills(skills_featured: list, all_skills_from_cv: list) -> str:
    featured_set = {s.lower() for s in skills_featured}
    parts = []
    for s in skills_featured:
        parts.append(f'<span class="skill-tag featured">{s}</span>')
    for s in all_skills_from_cv:
        if s.lower() not in featured_set:
            parts.append(f'<span class="skill-tag">{s}</span>')
    return "\n".join(parts)


def extract_all_skills(cv_text: str) -> list:
    """Extract skills list from cv.md skills section."""
    lines = cv_text.splitlines()
    skills = []
    in_skills = False
    for line in lines:
        stripped = line.strip()
        if re.match(r"^#{1,3}\s+(skills|fähigkeiten|kompetenzen)", stripped, re.I):
            in_skills = True
        elif re.match(r"^#{1,3}\s+", stripped) and in_skills:
            break
        elif in_skills and stripped:
            # Comma-separated or bullet list
            for item in re.split(r"[,\|]|^[-*]\s*", stripped):
                item = item.strip(" -•*")
                if item and len(item) < 40:
                    skills.append(item)
    return skills


def render_education(edu_lines: list) -> str:
    if not edu_lines:
        return ""
    items = "\n".join(f'<p class="cert-item">{line}</p>' for line in edu_lines[:6])
    return f"<h2>Education</h2>\n{items}"


def render_certs(cert_lines: list) -> str:
    if not cert_lines:
        return ""
    items = "\n".join(f'<p class="cert-item">{line}</p>' for line in cert_lines[:8])
    return f"<h2>Certifications</h2>\n{items}"


def generate_resume_html(client, cv, title, company, description, model) -> str:
    print("  Calling Groq for resume tailoring…")
    data = call_groq(client, cv, title, company, description, model)

    name, contact, edu_lines, cert_lines = extract_cv_meta(cv)
    all_skills = extract_all_skills(cv)

    experience_html = render_experience(data.get("experience", []))
    skills_html     = render_skills(data.get("skills_featured", []), all_skills)
    education_html  = render_education(edu_lines)
    certs_html      = render_certs(cert_lines)
    keywords_str    = ", ".join(data.get("keywords", []))

    return HTML_TEMPLATE.format(
        name=name,
        title=title,
        company=company,
        tagline=data.get("tagline", ""),
        contact=contact,
        summary=data.get("summary", ""),
        experience_html=experience_html,
        skills_html=skills_html,
        education_html=education_html,
        certs_html=certs_html,
        keywords_str=keywords_str,
    )


def save_resume(html: str, company: str, title: str) -> str:
    OUTPUT_DIR.mkdir(exist_ok=True)
    slug  = re.sub(r"[^\w-]", "-", company.lower())[:25]
    date  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fname = f"{slug}-{date}.html"
    path  = OUTPUT_DIR / fname
    path.write_text(html, encoding="utf-8")
    return str(path)


def main():
    parser = argparse.ArgumentParser(description="Generate a tailored HTML resume for a job")
    parser.add_argument("url", nargs="?", help="Job URL")
    parser.add_argument("--url",     dest="url_opt")
    parser.add_argument("--title",   default="Role",    help="Job title")
    parser.add_argument("--company", default="Company", help="Company name")
    args = parser.parse_args()

    url = args.url or args.url_opt
    if not url:
        parser.error("Provide a job URL: python resume.py <url>")

    print("=== Jobscan Resume Generator ===\n")

    config = load_config()
    cv     = load_cv()

    api_key = config.get("groq", {}).get("api_key") or os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit("Error: Groq API key not set.")

    model  = config.get("groq", {}).get("model", "llama-3.3-70b-versatile")
    client = Groq(api_key=api_key)

    print(f"Job URL:  {url}")
    print(f"Fetching job description…")
    description = fetch_description(url)
    print(f"  {len(description)} chars fetched")

    html = generate_resume_html(client, cv, args.title, args.company, description, model)
    out_path = save_resume(html, args.company, args.title)

    print(f"\n✓ Resume saved → {out_path}")
    print(f"\nTo create PDF:")
    print(f"  1. Open {out_path} in your browser")
    print(f"  2. File → Print → Save as PDF")
    print(f"  3. Set paper to A4, margins to Minimum")


if __name__ == "__main__":
    main()
