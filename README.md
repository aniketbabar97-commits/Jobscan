# Jobscan Germany

Automated job search pipeline for **Germany + remote** roles.
Pulls listings from multiple sources, filters out 90%+ automatically, then uses Claude to score the remainder against your CV — one API call per role.

**Before**: hours scrolling job boards
**After**: ~20 minutes reviewing a shortlisted set of genuinely relevant roles

Inspired by [chimera878/jobscan](https://github.com/chimera878/jobscan), rebuilt in pure Python and focused on the German market + global remote.

---

## How It Works

```
scan.py  ──►  pipeline.md  ──►  eval.py  ──►  pipeline.md (with scores)
 (free)        (raw list)      (Claude)        (your shortlist)
```

**Step 1 — Scan** (`python scan.py`): Pulls jobs from 5 sources, applies title/location/seniority/domain filters, deduplicates against history. Zero Claude tokens.

**Step 2 — Eval** (`python eval.py`): For each pending job, fetches the description and asks Claude for a 0–5 fit score against your CV. Updates pipeline.md in-place.

**Step 3 — Review**: Open pipeline.md. Focus on the `✓` entries — those are Claude's "yes" picks.

---

## Job Sources

| Source | Focus | Auth required |
|--------|-------|---------------|
| [Adzuna](https://developer.adzuna.com) | Germany (API) | Free API key |
| [Arbeitnow](https://www.arbeitnow.com) | Germany / Europe | None |
| [RemoteOK](https://remoteok.com) | Global remote | None |
| [Remotive](https://remotive.com) | Global remote | None |
| [WeWorkRemotely](https://weworkremotely.com) | Global remote | None |

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

```bash
cp config.example.yml config.yml
```

Open `config.yml` and fill in:
- **`anthropic.api_key`** — get one at console.anthropic.com (or set `ANTHROPIC_API_KEY` env var)
- **`adzuna.app_id` / `adzuna.app_key`** — optional but recommended; free tier at [developer.adzuna.com](https://developer.adzuna.com)
- Adjust filters (seniority, domain, location allow/block) to match your situation

### 3. Add your CV

Create `cv.md` with your resume in markdown format. If you have a PDF:

```bash
# Using pandoc (if installed):
pandoc resume.pdf -o cv.md

# Or paste your CV manually into cv.md
```

The more detail the better — Claude uses this to evaluate fit.

### 4. Run

```bash
python scan.py    # fetch + filter jobs
python eval.py    # score with Claude
# open pipeline.md
```

---

## Configuration

Key settings in `config.yml`:

| Setting | Default | Description |
|---------|---------|-------------|
| `max_age_days` | `5` | Skip jobs older than this |
| `score_threshold` | `3.5` | Minimum score for "yes" |
| `anthropic.model` | `claude-haiku-4-5-20251001` | Model for evaluation |

### Tuning filters

The default filters target mid-level software engineering roles. Adjust in `config.yml`:

- **`filters.keywords.require_one`** — required keywords in job title
- **`filters.seniority.block`** — remove terms for levels you're open to (e.g. remove `"senior"`)
- **`filters.domain.block`** — domains to ignore (e.g. remove `"frontend"` if you do full-stack)
- **`filters.location.allow`** — city/region names to accept

---

## Pipeline Format

```markdown
- [ ] **[Software Engineer at ACME GmbH](https://...)** `remote`
  `arbeitnow` · Berlin · 2d old · 2024-01-15
```

After eval.py:
```markdown
- [x] **[Software Engineer at ACME GmbH](https://...)** `remote` — **4.3 ✓**
  `arbeitnow` · Berlin · 2d old · 2024-01-15
  > **YES**: Strong Python/backend match, remote-friendly, aligned with your ML experience
```

Manually track your applications by changing `- [x]` to `- [~]`.

---

## Cost

Using the default `claude-haiku-4-5-20251001` model, a typical run evaluating 30–60 shortlisted jobs costs **under $0.10** in Claude API credits.

Switch to `claude-sonnet-4-6` in `config.yml` for higher-quality reasoning (~10× more per call).

---

## Privacy

`config.yml`, `cv.md`, `pipeline.md`, `scan_history.tsv`, and `job_cache.json` are all gitignored. Your CV and API keys never leave your machine (except for the Claude API call during eval).

---

## Requirements

- Python 3.9+
- Claude API key (Anthropic)
- Adzuna API key (optional but recommended for German listings)
