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

### Apply to a Job (when you find a good one)

```bash
# 1. Generate tailored application materials
python apply.py "https://jobs.example.com/job/123"

# With known title/company (skips web fetch):
python apply.py --url "https://..." --title "SAP Hybris Developer" --company "Valtech"

# 2. Open the generated file (shown in output), review and edit it
# File is in: applications/{company}-{date}/materials.md
# Contains: ATS keywords, tailored summary, bullet points,
#           cover letter, LinkedIn messages, common form answers

# 3. Apply on the company website, copy-pasting from materials.md

# 4. Mark yourself as Applied
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
| `reports/` | Deep evaluation reports (gitignored) |
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
