# Jobscan Germany — Claude Code Commands

Job search automation for Germany + remote SAP Commerce / Java Developer roles.
Pulls 500–2000 listings, filters aggressively, scores remainder against Kranti's CV.

## Setup (first time)

```bash
pip install -r requirements.txt
# Edit config.yml and add your GROQ_API_KEY (free at console.groq.com)
# cv.md is already created from your uploaded CV
```

## Daily Workflow

```
Step 1: python scan.py           — fetch + filter jobs (free, no AI tokens)
Step 2: python eval.py           — score pending jobs with Groq LLM (free)
Step 3: streamlit run dashboard.py  — visual review in browser
```

## Commands

### /scan
```bash
python scan.py
```
Pulls jobs from Adzuna DE, Arbeitnow, RemoteOK, Remotive, WeWorkRemotely.
Applies title/location/seniority/domain filters. Deduplicates against history.
Writes new jobs to `pipeline.md`, appends to `scan_history.tsv`.

### /eval
```bash
python eval.py
python eval.py --dry-run      # preview pending jobs
python eval.py --limit 20     # evaluate only first 20
```
Scores each pending job against cv.md using Groq (llama-3.3-70b-versatile, free).
Updates pipeline.md in-place with scores and Yes/No decisions.

### /dashboard
```bash
streamlit run dashboard.py
```
Opens the web dashboard at http://localhost:8501.
- Visual job cards color-coded by fit score
- One-click Scan and Evaluate buttons
- Tabs: Good Fits / Pending / No Fits / All
- Auto-refresh toggle (30s)
- Filter by source and remote

**To share the dashboard publicly:**

Option A — ngrok (instant, temporary URL):
```bash
pip install pyngrok
ngrok http 8501
# Copy the https://xxxx.ngrok.io URL and share it
```

Option B — Streamlit Community Cloud (permanent free URL):
1. Push this repo to GitHub (public or private)
2. Go to share.streamlit.io
3. Deploy `dashboard.py` — get a permanent shareable link

## Files

| File | Description |
|------|-------------|
| `config.yml` | Settings + API keys (gitignored) |
| `cv.md` | Kranti's CV in markdown (gitignored) |
| `pipeline.md` | Job inbox with scores (gitignored) |
| `scan_history.tsv` | Dedup log (gitignored) |
| `job_cache.json` | Cached descriptions (gitignored) |

## Job Sources

| Source | Region | Auth |
|--------|--------|------|
| Adzuna | Germany + remote | Free key (configured) |
| Arbeitnow | Germany / Europe | None |
| RemoteOK | Global remote | None |
| Remotive | Global remote | None |
| WeWorkRemotely | Global remote | None |

## Cost Estimate

Using Groq free tier (llama-3.3-70b-versatile):
- **$0** — Groq's free tier includes 14,400 requests/day
- No credit card required
- Just need a free account at console.groq.com
