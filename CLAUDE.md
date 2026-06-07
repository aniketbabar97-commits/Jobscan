# Jobscan Germany — Claude Code Commands

Job search automation for Germany + remote SAP Commerce / Java Developer roles.
Pulls 500–2000 listings, filters aggressively, scores remainder against Kranti's CV.

---

## Complete Step-by-Step Usage Guide

### First-Time Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy config template and fill in your keys
cp config.example.yml config.yml
# Your Groq key and Adzuna key are already configured in config.yml

# 3. Make sure cv.md exists (created from your CV upload)
ls cv.md
```

---

### Daily Workflow (5 minutes)

```
Step 1: python scan.py          — fetch + filter jobs (free, no AI)
Step 2: python eval.py          — score jobs with Groq AI (free)
Step 3: python export.py        — write results.json for dashboard
Step 4: git add public/results.json && git commit -m "Update results" && git push
         → Vercel auto-deploys in ~30 seconds
```

---

### Quick Auto-Pipeline (one command for everything)

```bash
# URL → score + full A-G report + tailored HTML resume + tracker entry
python auto.py "https://jobs.example.com/job/123"

# With known title/company:
python auto.py --url "https://..." --title "SAP Hybris Developer" --company "Valtech"

# Force full report even if score is below threshold:
python auto.py --url "https://..." --force
```

What it does automatically:
1. Fetches the job description
2. Scores it (0–5) against your CV
3. If score ≥ 3.5: generates full A-G deep report + tailored HTML resume
4. Adds to tracker as "Evaluated"
5. Tells you exactly what to do next

**After auto.py:**
- Open `reports/NNN-company-date.md` — read the A-G analysis
- Open `output/company-date.html` in browser → Print → Save as PDF
- Apply on the company's website using the materials
- Run: `python tracker.py update "https://..." Applied`

---

### Generate Just the HTML Resume

```bash
python resume.py "https://jobs.example.com/job/123" --title "SAP Hybris Dev" --company "Valtech"
# Saves to output/company-date.html
# Open in browser → File → Print → Save as PDF (A4, Minimum margins)
```

---

### Generate Just the Application Materials (cover letter etc.)

```bash
# 1. Generate cover letter, LinkedIn messages, form answers
python apply.py "https://jobs.example.com/job/123"

# With known title/company (skips web fetch):
python apply.py --url "https://..." --title "SAP Hybris Developer" --company "Valtech"

# 2. Open applications/{company}-{date}/materials.md and copy-paste into the application form

# 3. Mark yourself as Applied
python tracker.py update "https://..." Applied
```

---

### Track Your Applications

```bash
# View all tracked applications
python tracker.py

# Filter by status
python tracker.py list --status Applied
python tracker.py list --status Interview

# Update status as things progress
python tracker.py update "https://..." Responded   # they replied
python tracker.py update "https://..." Interview   # interview scheduled
python tracker.py update "https://..." Offer       # offer received
python tracker.py update "https://..." Rejected    # no go

# See funnel statistics
python tracker.py stats
```

**Status progression:**
`Evaluated` → `Applied` → `Responded` → `Interview` → `Offer` or `Rejected`

---

### Deep Evaluation (for borderline jobs)

```bash
# Score + full career-ops A-G report for promising jobs
python eval.py --deep

# Preview what would be evaluated (no API calls)
python eval.py --dry-run

# Limit how many to evaluate in one run
python eval.py --limit 20
```

Deep reports are saved to `reports/NNN-company-YYYY-MM-DD.md` (gitignored, local only).
The dashboard shows a `📄 deep report` badge when a report exists.

---

### Local Interactive Dashboard

```bash
streamlit run dashboard.py
# Opens at http://localhost:8501
# One-click Scan + Evaluate buttons
```

---

### Vercel Dashboard (shareable, mobile-friendly)

**Deploy once:**
1. Go to [vercel.com](https://vercel.com) → **Add New Project**
2. Import `aniketbabar97-commits/Jobscan` repo
3. Leave all settings as default (Framework: Other, Root: `/`)
4. Click **Deploy** — live at `https://jobscan-xxx.vercel.app`

**Update after every scan+eval:**
```bash
python export.py
git add public/results.json && git commit -m "Update results" && git push
# Live in ~30 seconds
```

---

## Commands

### /scan
```bash
python scan.py
```
Pulls jobs from Adzuna DE, Arbeitnow, RemoteOK, Remotive, WeWorkRemotely, and ATS company pages (Greenhouse/Lever/Ashby).
Applies title/location/seniority/domain filters. Deduplicates against history.
Writes new jobs to `pipeline.md`, appends to `scan_history.tsv`.

### /eval
```bash
python eval.py
python eval.py --deep         # also generate full A-G reports for yes-fit jobs
python eval.py --dry-run      # preview pending jobs without scoring
python eval.py --limit 20     # evaluate only first 20
```
Scores each pending job against cv.md using Groq (llama-3.3-70b-versatile, free).
Updates pipeline.md in-place with scores and Yes/No decisions.

### /export
```bash
python export.py
```
Converts `pipeline.md` → `public/results.json` (includes application tracker stats).
Then push: `git add public/results.json && git commit -m "Update results" && git push`

### /auto
```bash
python auto.py <job_url>
python auto.py --url <url> --title "SAP Hybris Dev" --company "Valtech"
python auto.py --url <url> --force     # full report regardless of score
```
Single-command pipeline: fetch → score → deep report → HTML resume → tracker.
Use this for any interesting job you find. Output goes to `reports/` and `output/`.

### /resume
```bash
python resume.py <job_url> --title "SAP Hybris Dev" --company "Valtech"
```
Generates a tailored HTML resume. Open in browser → File → Print → Save as PDF.
Saves to `output/{company}-{date}.html`.

### /apply
```bash
python apply.py <job_url>
python apply.py --url <url> --title "SAP Hybris Dev" --company "Valtech"
```
Generates tailored materials (ATS keywords, summary, cover letter, LinkedIn messages, form answers).
Saves to `applications/{company}-{date}/materials.md` and adds to `applications.tsv`.

### /tracker
```bash
python tracker.py                            # list all
python tracker.py list --status Applied      # filter by status
python tracker.py update "<url>" Applied     # update status
python tracker.py stats                      # funnel statistics
python tracker.py add --url "<url>" --title "Role" --company "Co"
```

### /dashboard (local only)
```bash
streamlit run dashboard.py
```
Opens full interactive dashboard at http://localhost:8501 with one-click Scan + Evaluate buttons.

---

## Files

| File | Description |
|------|-------------|
| `config.yml` | Settings + API keys (gitignored) |
| `cv.md` | Kranti's CV in markdown (gitignored) |
| `pipeline.md` | Job inbox with scores (gitignored) |
| `scan_history.tsv` | Dedup log (gitignored) |
| `job_cache.json` | Cached descriptions (gitignored) |
| `applications.tsv` | Application tracker (gitignored) |
| `applications/` | Tailored materials per job (gitignored) |
| `reports/` | Deep A-G evaluation reports (gitignored) |
| `output/` | Tailored HTML resumes (gitignored) |
| `public/results.json` | Dashboard data — tracked in git |

---

## Job Sources

| Source | Region | Auth |
|--------|--------|------|
| Adzuna | Germany + remote | Free key (configured) |
| Arbeitnow | Germany / Europe | None |
| RemoteOK | Global remote | None |
| Remotive | Global remote | None |
| WeWorkRemotely | Global remote | None |
| Greenhouse / Lever / Ashby | Direct ATS | None (public APIs) |

---

## Cost Estimate

- **$0** — Groq's free tier includes 14,400 requests/day
- No credit card required
- Just need a free account at console.groq.com
