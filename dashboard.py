#!/usr/bin/env python3
"""
dashboard.py — Streamlit web dashboard for Jobscan Germany.

Run locally:    streamlit run dashboard.py
Share publicly: streamlit run dashboard.py  (then use ngrok or deploy to Streamlit Cloud)
"""

import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="Jobscan 🇩🇪",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

ROOT = Path(__file__).parent
PIPELINE_FILE = ROOT / "pipeline.md"
HISTORY_FILE = ROOT / "scan_history.tsv"

# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .job-card {
        background: #1e1e2e;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 10px;
        border-left: 4px solid #555;
    }
    .job-card.yes  { border-left-color: #2ecc71; }
    .job-card.no   { border-left-color: #e74c3c; }
    .job-card.pend { border-left-color: #3498db; }

    .job-title { font-size: 1.05rem; font-weight: 600; margin-bottom: 2px; }
    .job-meta  { font-size: 0.82rem; color: #aaa; margin-top: 4px; }
    .score-yes { color: #2ecc71; font-weight: 700; }
    .score-no  { color: #e74c3c; font-weight: 700; }
    .score-pend{ color: #3498db; }
    .badge {
        display: inline-block;
        padding: 2px 7px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-right: 4px;
    }
    .badge-remote { background:#1a3a5c; color:#5ab4ff; }
    .badge-source { background:#2a2a3a; color:#ccc; }
    div[data-testid="stMetricValue"] { font-size: 2rem !important; }
</style>
""", unsafe_allow_html=True)


# ─── Parsers ─────────────────────────────────────────────────────────────────
def parse_jobs(content: str) -> list:
    jobs = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r"^- \[(.)\] \*\*\[(.+?)\]\((.+?)\)\*\*(.*)$", line)
        if not m:
            i += 1
            continue

        status_char, link_text, url, suffix = m.groups()
        title, company = (link_text.rsplit(" at ", 1) if " at " in link_text else (link_text, ""))

        status = {"x": "evaluated", " ": "pending"}.get(status_char, "other")
        score, fit, reason = None, None, ""

        if status == "evaluated":
            sm = re.search(r"\*\*(\d+\.?\d*)\s*([✓✗])\*\*", suffix)
            if sm:
                score = float(sm.group(1))
                fit = "yes" if sm.group(2) == "✓" else "no"

        source, location, remote = "", "", ("remote" in line.lower() or "`remote`" in line)

        if i + 1 < len(lines):
            meta = lines[i + 1].strip()
            mm = re.match(r"`([^`]+)`\s*·\s*([^·]+)\s*·", meta)
            if mm:
                source = mm.group(1).strip()
                location = mm.group(2).strip()

        if i + 2 < len(lines):
            r_line = lines[i + 2].strip()
            rm = re.match(r">\s*\*\*(YES|NO)\*\*:\s*(.+)", r_line)
            if rm:
                reason = rm.group(2).strip()

        jobs.append({
            "title": title.strip(), "company": company.strip(), "url": url,
            "status": status, "score": score, "fit": fit,
            "source": source, "location": location,
            "remote": remote, "reason": reason,
        })
        i += 1

    return jobs


def load_pipeline() -> list:
    if not PIPELINE_FILE.exists():
        return []
    return parse_jobs(PIPELINE_FILE.read_text())


def scan_age() -> str:
    if not PIPELINE_FILE.exists():
        return "Never"
    mtime = PIPELINE_FILE.stat().st_mtime
    dt = datetime.fromtimestamp(mtime)
    delta = datetime.now() - dt
    if delta.seconds < 60:
        return "just now"
    if delta.seconds < 3600:
        return f"{delta.seconds // 60}m ago"
    if delta.days == 0:
        return f"{delta.seconds // 3600}h ago"
    return f"{delta.days}d ago"


# ─── Render a single job card ─────────────────────────────────────────────────
def render_job(job: dict):
    if job["fit"] == "yes":
        card_cls, score_cls = "yes", "score-yes"
        score_str = f'<span class="{score_cls}">★ {job["score"]:.1f} / 5 &nbsp;✓</span>'
    elif job["fit"] == "no":
        card_cls, score_cls = "no", "score-no"
        score_str = f'<span class="{score_cls}">{job["score"]:.1f} / 5 &nbsp;✗</span>'
    else:
        card_cls, score_cls = "pend", "score-pend"
        score_str = '<span class="score-pend">⏳ pending</span>'

    remote_badge = '<span class="badge badge-remote">🌍 remote</span>' if job["remote"] else ""
    src_badge = f'<span class="badge badge-source">{job["source"]}</span>' if job["source"] else ""
    reason_html = f'<div style="margin-top:6px;font-size:0.85rem;color:#ccc"><em>{job["reason"]}</em></div>' if job["reason"] else ""

    st.markdown(f"""
<div class="job-card {card_cls}">
  <div class="job-title">
    <a href="{job['url']}" target="_blank" style="color:inherit;text-decoration:none">
      {job['title']} <span style="color:#888;font-weight:400">at {job['company']}</span>
    </a>
  </div>
  <div class="job-meta">
    {src_badge}{remote_badge}
    &nbsp;{job['location']}
    &nbsp;&nbsp;{score_str}
  </div>
  {reason_html}
</div>
""", unsafe_allow_html=True)


# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🔍 Jobscan 🇩🇪")
    st.caption("Germany + Remote · Auto-updated")
    st.divider()

    st.subheader("Controls")

    run_scan = st.button("🔄 Run Scan", use_container_width=True, help="Fetch new jobs from all sources")
    run_eval = st.button("🤖 Evaluate Jobs", use_container_width=True, help="Score pending jobs with AI")

    st.divider()
    st.subheader("Filters")
    all_jobs_raw = load_pipeline()
    sources = sorted({j["source"] for j in all_jobs_raw if j["source"]})
    selected_sources = st.multiselect("Source", sources, default=sources)

    show_remote_only = st.checkbox("Remote only", value=False)
    min_score = st.slider("Min score (evaluated)", 0.0, 5.0, 0.0, 0.5)

    st.divider()
    auto_refresh = st.checkbox("Auto-refresh (30s)", value=False)
    st.caption(f"Pipeline last updated: **{scan_age()}**")

# ─── Run commands ─────────────────────────────────────────────────────────────
if run_scan:
    with st.spinner("Scanning all job sources..."):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scan.py")],
            capture_output=True, text=True, cwd=str(ROOT)
        )
    if result.returncode == 0:
        st.success("Scan complete!")
        st.code(result.stdout[-2000:] if result.stdout else "(no output)")
    else:
        st.error("Scan failed")
        st.code(result.stderr[-2000:])
    st.rerun()

if run_eval:
    with st.spinner("Evaluating with AI (this may take a minute)..."):
        result = subprocess.run(
            [sys.executable, str(ROOT / "eval.py")],
            capture_output=True, text=True, cwd=str(ROOT)
        )
    if result.returncode == 0:
        st.success("Evaluation complete!")
        st.code(result.stdout[-2000:] if result.stdout else "(no output)")
    else:
        st.error("Evaluation failed")
        st.code(result.stderr[-2000:])
    st.rerun()

# ─── Load + filter jobs ───────────────────────────────────────────────────────
jobs = [j for j in all_jobs_raw if (not selected_sources or j["source"] in selected_sources)]
if show_remote_only:
    jobs = [j for j in jobs if j["remote"]]

yes_jobs    = [j for j in jobs if j["fit"] == "yes" and (j["score"] or 0) >= min_score]
no_jobs     = [j for j in jobs if j["fit"] == "no"  and (j["score"] or 0) >= min_score]
pend_jobs   = [j for j in jobs if j["status"] == "pending"]

yes_jobs.sort(key=lambda j: j["score"] or 0, reverse=True)

# ─── Header stats ─────────────────────────────────────────────────────────────
st.title("Job Pipeline")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total", len(all_jobs_raw))
c2.metric("✓ Good Fit", len([j for j in all_jobs_raw if j["fit"] == "yes"]))
c3.metric("⏳ Pending", len([j for j in all_jobs_raw if j["status"] == "pending"]))
c4.metric("✗ No Fit",  len([j for j in all_jobs_raw if j["fit"] == "no"]))

st.divider()

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab_yes, tab_pend, tab_no, tab_all = st.tabs([
    f"✓ Good Fits ({len(yes_jobs)})",
    f"⏳ Pending ({len(pend_jobs)})",
    f"✗ No Fits ({len(no_jobs)})",
    f"All ({len(jobs)})",
])

with tab_yes:
    if yes_jobs:
        for job in yes_jobs:
            render_job(job)
    else:
        st.info("No good fits yet. Run Scan → Evaluate to find matches.")

with tab_pend:
    if pend_jobs:
        st.caption(f"{len(pend_jobs)} jobs waiting to be evaluated. Click **Evaluate Jobs** in the sidebar.")
        for job in pend_jobs:
            render_job(job)
    else:
        st.info("No pending jobs. Run **Scan** to fetch new listings.")

with tab_no:
    if no_jobs:
        no_sorted = sorted(no_jobs, key=lambda j: j["score"] or 0, reverse=True)
        for job in no_sorted:
            render_job(job)
    else:
        st.info("No evaluated no-fit jobs yet.")

with tab_all:
    all_sorted = sorted(jobs, key=lambda j: (j["score"] or -1), reverse=True)
    for job in all_sorted:
        render_job(job)

# ─── Auto-refresh ─────────────────────────────────────────────────────────────
if auto_refresh:
    import time
    time.sleep(30)
    st.rerun()

# ─── Empty state ─────────────────────────────────────────────────────────────
if not all_jobs_raw:
    st.warning(
        "No pipeline.md found or it's empty.\n\n"
        "**Getting started:**\n"
        "1. Make sure `config.yml` exists with your API keys\n"
        "2. Make sure `cv.md` exists with your resume\n"
        "3. Click **🔄 Run Scan** in the sidebar"
    )
