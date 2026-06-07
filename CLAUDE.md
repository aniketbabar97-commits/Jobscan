# Jobscan Germany — Claude Code Commands

Job search automation for Germany + remote roles.
Pulls ~1000+ listings, filters aggressively, scores remainder against your CV.

## Setup (first time)

```bash
pip install -r requirements.txt
cp config.example.yml config.yml   # then edit config.yml
# Create cv.md with your resume in markdown format
```

## Daily Workflow

```
Step 1: python scan.py     — fetch + filter jobs (no Claude tokens used)
Step 2: python eval.py     — score pending jobs with Claude
Step 3: open pipeline.md   — review your shortlist
```

## Commands

### /scan
```bash
python scan.py
```
Pulls jobs from Adzuna DE, Arbeitnow, RemoteOK, Remotive, WeWorkRemotely.
Applies title/location/seniority/domain filters. Deduplicates against history.
Writes new jobs to pipeline.md and appends to scan_history.tsv.

### /eval
```bash
python eval.py
```
Reads pending `- [ ]` entries from pipeline.md.
Fetches each job page (uses job_cache.json when available to avoid re-fetching).
Calls Claude once per job with your CV to get a 0–5 fit score.
Updates pipeline.md in-place with scores and Yes/No decisions.

Useful flags:
```bash
python eval.py --dry-run      # list pending jobs without calling Claude
python eval.py --limit 20     # evaluate only the first 20 pending jobs
```

### /setup
Check that setup is complete:
1. `config.yml` exists and has API keys filled in
2. `cv.md` exists with resume content
3. `pip install -r requirements.txt` has been run
4. (Optional) Get free Adzuna API key at developer.adzuna.com

## Files

| File | Description |
|------|-------------|
| `config.yml` | Your settings + API keys (gitignored) |
| `cv.md` | Your CV in markdown format (gitignored) |
| `pipeline.md` | Job inbox — review this after eval (gitignored) |
| `scan_history.tsv` | Dedup log of all seen jobs (gitignored) |
| `job_cache.json` | Cached job descriptions (gitignored) |

## Job Sources

| Source | Region | Auth |
|--------|--------|------|
| Adzuna | Germany + remote | Free API key |
| Arbeitnow | Germany / Europe | None |
| RemoteOK | Global remote | None |
| Remotive | Global remote | None |
| WeWorkRemotely | Global remote | None |

## Pipeline Format

```
- [ ] **[Job Title at Company](url)** `remote`
  `source` · Location · Nd old · YYYY-MM-DD
```

After eval.py runs:
```
- [x] **[Job Title at Company](url)** `remote` — **4.2 ✓**
  `source` · Location · Nd old · YYYY-MM-DD
  > **YES**: Strong Python/ML match, remote-friendly, EU timezone preferred
```

Manually mark jobs you've applied to with `- [~]` to track progress.

## Cost Estimate

Using `claude-haiku-4-5-20251001` (default):
- ~50 jobs to evaluate after filtering → ~$0.05–0.10 per scan run
- Switch to `claude-sonnet-4-6` in config.yml for better reasoning (~10× more)
