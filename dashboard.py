"""
dashboard.py — Job Search CRM & Career Intelligence Dashboard

Run with Streamlit:
    streamlit run dashboard.py

Primary Sections:
  🎯 Job Matcher & Applications  — Skill gap analysis, live ATS CV optimization, cover letter generator
  📊 Market Intelligence         — Top skills radar, company leaderboard, platform analytics
  🧭 Career Roadmap & Strategy   — Domain playbooks (Data, AI, Software), must-haves, portfolio blueprints
  📬 Application CRM & Email Hub — 7-day follow-up tracker, Gmail IMAP sync, AI email classifier
"""
import os
import sys
import json
import html
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# ─── Path setup ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ─── Load .env FIRST — before any src.* import ───────────────────────────────
# This ensures secrets are available and config.py never crashes at import.
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except ImportError:
    pass  # dotenv not installed yet; env vars must be set manually

# Set placeholder values for optional integrations the dashboard doesn't strictly require —
for _var in ["GOOGLE_SHEET_ID"]:
    if not os.getenv(_var):
        os.environ[_var] = "__not_configured__"

from datetime import datetime, timezone
from urllib.parse import quote

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import re

# ─── Page config (must be first Streamlit call) ───────────────────────────────
st.set_page_config(
    page_title="Job Search CRM Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Hide default Streamlit header */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Skill tags */
    .skill-tag-green {
        display: inline-block;
        background: #d1fae5;
        color: #065f46;
        border: 1px solid #6ee7b7;
        border-radius: 6px;
        padding: 2px 10px;
        margin: 3px;
        font-size: 13px;
        font-weight: 500;
    }
    .skill-tag-red {
        display: inline-block;
        background: #fee2e2;
        color: #991b1b;
        border: 1px solid #fca5a5;
        border-radius: 6px;
        padding: 2px 10px;
        margin: 3px;
        font-size: 13px;
        font-weight: 500;
    }
    .skill-tag-blue {
        display: inline-block;
        background: #dbeafe;
        color: #1e3a8a;
        border: 1px solid #93c5fd;
        border-radius: 6px;
        padding: 2px 10px;
        margin: 3px;
        font-size: 13px;
        font-weight: 500;
    }
    /* Metric card override */
    [data-testid="metric-container"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 12px 16px;
    }
    /* Section headers */
    .section-header {
        font-size: 18px;
        font-weight: 700;
        color: #1e293b;
        border-bottom: 2px solid #e2e8f0;
        padding-bottom: 8px;
        margin: 20px 0 12px 0;
    }
    /* CRM Status Badges */
    .badge-applied {
        background: #e0f2fe;
        color: #0369a1;
        border: 1px solid #7dd3fc;
        border-radius: 6px;
        padding: 3px 10px;
        font-weight: 600;
        font-size: 13px;
        display: inline-block;
    }
    .badge-followup {
        background: #fef3c7;
        color: #b45309;
        border: 1px solid #fcd34d;
        border-radius: 6px;
        padding: 3px 10px;
        font-weight: 600;
        font-size: 13px;
        display: inline-block;
    }
    .badge-interview {
        background: #dcfce7;
        color: #15803d;
        border: 1px solid #86efac;
        border-radius: 6px;
        padding: 3px 10px;
        font-weight: 600;
        font-size: 13px;
        display: inline-block;
    }
    .badge-rejected {
        background: #fee2e2;
        color: #b91c1c;
        border: 1px solid #fca5a5;
        border-radius: 6px;
        padding: 3px 10px;
        font-weight: 600;
        font-size: 13px;
        display: inline-block;
    }
    .badge-assessment {
        background: #f3e8ff;
        color: #7e22ce;
        border: 1px solid #d8b4fe;
        border-radius: 6px;
        padding: 3px 10px;
        font-weight: 600;
        font-size: 13px;
        display: inline-block;
    }
    /* Modern Stateful Segmented Navigation Tabs */
    div[data-testid="stRadio"]:has(div[role="radiogroup"]) {
        margin-bottom: 18px;
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] {
        display: flex !important;
        flex-direction: row !important;
        background: #f1f5f9;
        padding: 6px;
        border-radius: 12px;
        border: 1px solid #cbd5e1;
        gap: 8px;
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] > label {
        flex: 1;
        text-align: center;
        background: transparent;
        padding: 10px 16px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 15px;
        color: #475569;
        cursor: pointer;
        transition: all 0.2s ease-in-out;
        justify-content: center;
        display: flex;
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] > label:hover {
        background: rgba(255, 255, 255, 0.7);
        color: #0f172a;
    }
    div[data-testid="stRadio"] > div[role="radiogroup"] > label[data-checked="true"],
    div[data-testid="stRadio"] > div[role="radiogroup"] > label:has(input:checked) {
        background: #ffffff !important;
        color: #1e40af !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        border: 1px solid #e2e8f0;
    }
    /* Hide native radio circle icon */
    div[data-testid="stRadio"] > div[role="radiogroup"] > label > div:first-child {
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)


# ─── Data loading helpers ─────────────────────────────────────────────────────

from src import database as db

@st.cache_resource
def _init_db_once():
    db.init_db()
    db.ensure_default_profile()
    return True

_init_db_once()


def _load_db_module():
    """Return database module directly."""
    return db


@st.cache_data(ttl=180)
def load_jobs() -> list[dict]:
    return db.get_all_jobs()


@st.cache_data(ttl=180)
def load_stats() -> dict:
    return db.get_stats()


@st.cache_data(ttl=180)
def load_applied_jobs() -> list[dict]:
    return db.get_applied_jobs()


@st.cache_data(ttl=180)
def load_cv() -> dict:
    active_profile = db.get_active_profile()
    if active_profile and active_profile.get("data"):
        return active_profile["data"]
    cv_path = ROOT / "data" / "master_cv.json"
    if cv_path.exists():
        with open(cv_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _clear_candidate_workspace_state():
    """Clear all tailored CV, cover letter, and copilot chat states across jobs."""
    prefixes = ("tailored_cv_", "cv_copilot_messages_", "cl_copilot_messages_", "cv_opt_meta_", "cover_letter_")
    to_delete = [k for k in list(st.session_state.keys()) if k.startswith(prefixes)]
    for k in to_delete:
        st.session_state.pop(k, None)
    st.session_state.pop("tailored_cv_working", None)
    st.session_state.pop("tailored_cv_job_id", None)
    st.session_state.pop("cv_opt_meta", None)
    st.session_state.pop("cv_copilot_messages", None)


@st.cache_data(ttl=300)
def compute_skill_frequencies(descriptions: list[str], total: int, category: str = "All Concrete Technologies") -> list[dict]:
    from src.match_analyzer import skill_frequency_from_db
    return skill_frequency_from_db(descriptions, total, category=category)


@st.cache_data(show_spinner=False)
def get_cached_cv_pdf(cv_data: dict) -> bytes:
    """Generate ATS PDF from CV data and cache bytes to avoid ReportLab rebuild on every rerun."""
    from src.ai_assistant import generate_cv_pdf
    return generate_cv_pdf(cv_data)


@st.cache_data(show_spinner=False)
def get_cached_match(job_title: str, job_description: str, cv_data: dict):
    """Analyze skill match and cache result to avoid re-extracting skills on every minor interaction."""
    from src.match_analyzer import analyze_match
    return analyze_match(job_title=job_title, job_description=job_description, cv=cv_data)


# ─── Sidebar Multi-Profile Management ─────────────────────────────────────────
def render_sidebar_profiles():
    with st.sidebar:
        st.markdown("### 👤 Candidate Profile & CV Management")
        st.caption("Switch or upload multiple CV profiles to use the platform for different candidates.")

        profiles = db.get_profiles()
        active_p = db.get_active_profile()
        active_id = active_p["id"] if active_p else "default_hazal"

        prof_options = [p["id"] for p in profiles]
        if active_id not in prof_options and prof_options:
            active_id = prof_options[0]

        prof_idx = prof_options.index(active_id) if active_id in prof_options else 0

        def _format_prof(pid):
            matching = [p for p in profiles if p["id"] == pid]
            if matching:
                p = matching[0]
                badge = " 🌟" if pid == "default_hazal" else ""
                hl = p.get("headline") or ""
                hl_short = f" — {hl[:22]}..." if len(hl) > 22 else (f" — {hl}" if hl else "")
                return f"{p['name']}{hl_short}{badge}"
            return pid

        selected_pid = st.selectbox(
            "Active Candidate Profile:",
            prof_options,
            index=prof_idx,
            format_func=_format_prof,
            key="sidebar_active_profile_select",
        )

        if selected_pid != active_id:
            db.set_active_profile(selected_pid)
            st.cache_data.clear()
            _clear_candidate_workspace_state()
            st.rerun()

        if active_p:
            cand_skills = active_p.get("data", {}).get("skills", {})
            total_skills_count = sum(len(v) for v in cand_skills.values() if isinstance(v, list)) if isinstance(cand_skills, dict) else 0
            st.info(f"**Active Candidate:** {active_p['name']}\n\n🎓 {active_p.get('headline', '')}\n\n🛠️ {total_skills_count} Saved Skills")

            if active_id != "default_hazal":
                if st.button("🗑️ Delete Profile", type="secondary", use_container_width=True, help="Removes this candidate profile from the system"):
                    db.delete_profile(active_id)
                    db.set_active_profile("default_hazal")
                    st.cache_data.clear()
                    _clear_candidate_workspace_state()
                    st.success("Profile deleted, reverted to default profile.")
                    st.rerun()

        st.divider()

        with st.expander("➕ Upload CV & Create Profile", expanded=False):
            st.caption("Upload a CV in PDF or Word (.docx) format. Gemini AI parses all skills, experience, and education automatically.")
            uploaded_cv = st.file_uploader("Choose CV File:", type=["pdf", "docx"], key="sidebar_cv_file_uploader")

            if uploaded_cv is not None:
                if st.button("🚀 Parse CV with Gemini", type="primary", use_container_width=True, key="btn_parse_cv_upload"):
                    with st.spinner("📄 Reading document and analyzing with Gemini… (10–20s)"):
                        try:
                            from src.cv_parser import extract_text_from_upload, parse_cv_with_gemini
                            file_bytes = uploaded_cv.getvalue()
                            raw_text = extract_text_from_upload(file_bytes, uploaded_cv.name)
                            if not raw_text.strip():
                                st.error("⚠️ No text could be extracted. Please upload a valid text-based PDF or Word document.")
                            else:
                                parsed = parse_cv_with_gemini(raw_text)
                                st.session_state["pending_profile_cv"] = parsed
                                st.success("✅ CV parsed successfully! Review and save below.")
                        except Exception as parse_err:
                            st.error(f"Parsing error: {parse_err}")

            if "pending_profile_cv" in st.session_state:
                pending = st.session_state["pending_profile_cv"]
                p_name = pending.get("personal", {}).get("name", "New Candidate")
                p_edu = pending.get("education", [{}])[0].get("degree", "Data / Software") if pending.get("education") else "Professional"
                default_slug = re.sub(r"[^a-zA-Z0-9_]", "_", p_name.lower().strip()) or "candidate"

                st.markdown("---")
                st.markdown("##### 📋 Profile Preview & Confirmation")
                input_name = st.text_input("Full Name:", value=p_name, key="new_prof_name")
                input_headline = st.text_input("Headline / Title:", value=p_edu, key="new_prof_headline")
                input_slug = st.text_input("Profile Slug (ID):", value=default_slug, key="new_prof_id")

                st.caption(f"💼 Experience: {len(pending.get('experience', []))} | 🔬 Projects: {len(pending.get('projects', []))}")
                skills_preview = []
                for k, v in pending.get("skills", {}).items():
                    if isinstance(v, list):
                        skills_preview.extend(v[:3])
                if skills_preview:
                    st.caption(f"🛠️ Skills: {', '.join(skills_preview[:6])}...")

                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("✅ Save & Activate", type="primary", use_container_width=True, key="btn_save_pending_profile"):
                        pending["personal"]["name"] = input_name
                        db.save_profile(
                            name=input_name.strip(),
                            headline=input_headline.strip(),
                            data=pending,
                            profile_id=input_slug.strip(),
                        )
                        db.set_active_profile(input_slug.strip())
                        del st.session_state["pending_profile_cv"]
                        st.cache_data.clear()
                        _clear_candidate_workspace_state()
                        st.success(f"🎉 Profile '{input_name}' saved and activated!")
                        st.rerun()
                with col_cancel:
                    if st.button("❌ Cancel", use_container_width=True, key="btn_cancel_pending_profile"):
                        del st.session_state["pending_profile_cv"]
                        st.rerun()


# Render sidebar
render_sidebar_profiles()


# ─── Header ──────────────────────────────────────────────────────────────────
col_header_title, col_header_btn = st.columns([4, 1.2])
with col_header_title:
    st.markdown("## 🤖 Job Search CRM — Intelligence Dashboard")
    st.caption("Berlin Working Student & Internship Tracker | Powered by Gemini AI")
with col_header_btn:
    if st.button("🔄 Scan for New Jobs", use_container_width=True, type="secondary"):
        with st.status("🔍 Scanning all platforms for new job listings...", expanded=True) as status_box:
            status_box.write("📡 Connecting to job platforms (LinkedIn, WorkingStudentJobs, Workwise, BSJ, Arbeitnow, HiringCafe)...")
            try:
                import time as _t
                from scripts.run_pipeline import main as run_pipeline

                def on_progress(event_type, msg, data):
                    if event_type == "source":
                        status_box.write(f"• **{data.get('source')}**: {data.get('count', 0)} jobs fetched")
                    elif event_type == "filter":
                        status_box.write(f"🎯 {msg}")
                    elif event_type == "dedup":
                        status_box.write(f"💾 {msg}")

                summary = run_pipeline(progress_callback=on_progress)
                st.cache_data.clear()

                raw_c = summary.get("raw_count", 0) if isinstance(summary, dict) else 0
                passed_c = summary.get("passed_count", 0) if isinstance(summary, dict) else 0
                new_c = summary.get("new_count", 0) if isinstance(summary, dict) else 0
                elapsed_s = summary.get("elapsed", 0) if isinstance(summary, dict) else 0

                if new_c > 0:
                    status_box.update(
                        label=f"🎉 {new_c} new jobs added! ({raw_c} scanned total)",
                        state="complete",
                        expanded=False,
                    )
                    st.success(f"🎉 **{new_c} new jobs** added to your CRM! (Scanned {raw_c} listings in {elapsed_s:.1f}s)")
                else:
                    status_box.update(
                        label=f"✅ Scan complete! ({raw_c} scanned, all matching jobs already tracked)",
                        state="complete",
                        expanded=False,
                    )
                    st.info(f"✨ Scanned **{raw_c} listings**, **{passed_c}** matched your criteria (Berlin/Remote + English). All qualified jobs are already saved in your database.")
                _t.sleep(1.5)
                st.rerun()
            except Exception as e:
                status_box.update(label="❌ An error occurred during the scan", state="error")
                st.error(f"Scan error: {e}")

st.divider()

# ─── Top-level metric row ─────────────────────────────────────────────────────
jobs = load_jobs()
stats = load_stats()

total      = sum(stats.values()) or 0
applied    = stats.get("applied", 0)
interview  = stats.get("interview", 0)
assessment = stats.get("assessment", 0)
rejected   = stats.get("rejected", 0)
saved      = stats.get("saved", 0)
skipped    = stats.get("skipped", 0)
new_count  = stats.get("new", 0)
active_apps = applied + interview + assessment
app_rate   = f"{active_apps/total*100:.0f}%" if total > 0 else "—"

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("📋 Total Jobs", total)
c2.metric("✅ Applied", applied)
c3.metric("🎉 Interview / Test", interview + assessment)
c4.metric("⏳ Saved", saved)
c5.metric("❌ Rejected", rejected)
c6.metric("📈 Application Rate", app_rate)

st.divider()

# ─── Stateful Navigation Tabs ──────────────────────────────────────────────────
NAV_OPTIONS = [
    "🎯 Job Matcher & Applications",
    "📊 Market Intelligence",
    "🧭 Career Roadmap & Strategy",
    "📬 Application CRM & Email Hub",
]

if "main_nav_tab" not in st.session_state:
    st.session_state["main_nav_tab"] = NAV_OPTIONS[0]

if st.session_state["main_nav_tab"] not in NAV_OPTIONS:
    st.session_state["main_nav_tab"] = NAV_OPTIONS[0]

# Ensure widget key is in sync before widget instantiation
if "nav_radio_bar" in st.session_state and st.session_state["nav_radio_bar"] != st.session_state["main_nav_tab"]:
    st.session_state["nav_radio_bar"] = st.session_state["main_nav_tab"]

def _on_nav_change():
    st.session_state["main_nav_tab"] = st.session_state["nav_radio_bar"]

active_tab = st.radio(
    "Main Navigation",
    NAV_OPTIONS,
    index=NAV_OPTIONS.index(st.session_state["main_nav_tab"]),
    horizontal=True,
    label_visibility="collapsed",
    key="nav_radio_bar",
    on_change=_on_nav_change,
)

# ══════════════════════════════════════════════════════════════════════════════
# TAB — MARKET INTELLIGENCE & TECH RADAR
# ══════════════════════════════════════════════════════════════════════════════
if active_tab == "📊 Market Intelligence":
    st.markdown('<div class="section-header">🔥 Top In-Demand Skills & Market Tech Radar</div>',
                unsafe_allow_html=True)
    st.caption("Analyzes real-time job descriptions across Berlin to surface the most in-demand technologies, tools, and methodologies.")

    descriptions = [j.get("description", "") for j in jobs if j.get("description")]

    if descriptions:
        # ── 1. Top Market Trends (KPI Highlight Cards) ────────────────────────
        kpi_prog = compute_skill_frequencies(descriptions, len(jobs), category="💻 Programming & Backend")
        kpi_ai = compute_skill_frequencies(descriptions, len(jobs), category="🤖 AI & Machine Learning")
        kpi_cloud = compute_skill_frequencies(descriptions, len(jobs), category="🗄️ Data Engineering & Cloud")
        kpi_bi = compute_skill_frequencies(descriptions, len(jobs), category="📊 BI & Data Analytics")

        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        with col_k1:
            top_prog = f"{kpi_prog[0]['skill']} ({kpi_prog[0]['pct']}%)" if kpi_prog else "—"
            sub_prog = f"+ {kpi_prog[1]['skill']} ({kpi_prog[1]['pct']}%)" if len(kpi_prog) > 1 else ""
            st.metric("💻 Top Languages", top_prog, sub_prog)
        with col_k2:
            top_ai = f"{kpi_ai[0]['skill']} ({kpi_ai[0]['pct']}%)" if kpi_ai else "—"
            sub_ai = f"+ {kpi_ai[1]['skill']} ({kpi_ai[1]['pct']}%)" if len(kpi_ai) > 1 else ""
            st.metric("🤖 Top AI & ML", top_ai, sub_ai)
        with col_k3:
            top_cloud = f"{kpi_cloud[0]['skill']} ({kpi_cloud[0]['pct']}%)" if kpi_cloud else "—"
            sub_cloud = f"+ {kpi_cloud[1]['skill']} ({kpi_cloud[1]['pct']}%)" if len(kpi_cloud) > 1 else ""
            st.metric("🗄️ Top Cloud & Data", top_cloud, sub_cloud)
        with col_k4:
            top_bi = f"{kpi_bi[0]['skill']} ({kpi_bi[0]['pct']}%)" if kpi_bi else "—"
            sub_bi = f"+ {kpi_bi[1]['skill']} ({kpi_bi[1]['pct']}%)" if len(kpi_bi) > 1 else ""
            st.metric("📊 Top BI & Analytics", top_bi, sub_bi)

        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

        # ── 2. Category Selector Filter ───────────────────────────────────────
        cat_options = [
            "All Concrete Technologies",
            "🤖 AI & Machine Learning",
            "🗄️ Data Engineering & Cloud",
            "💻 Programming & Backend",
            "📊 BI & Data Analytics",
            "📋 Methodologies & Tools",
        ]
        selected_category = st.radio(
            "Technology Filter:",
            cat_options,
            horizontal=True,
            key="market_category_radio",
            label_visibility="collapsed",
        )

        with st.spinner("Categorizing live market requirements…"):
            skill_data = compute_skill_frequencies(descriptions, len(jobs), category=selected_category)

        if skill_data:
            df_skills = pd.DataFrame(skill_data)

            cat_colors = {
                "Programming & Backend": "#2563eb",
                "AI, LLM & Machine Learning": "#7c3aed",
                "Data Engineering & Cloud": "#0d9488",
                "BI, Analytics & Tools": "#d97706",
                "QA & Software Testing": "#059669",
                "IT & Technical Support": "#d97706",
                "Methodologies & Practices": "#64748b",
            }

            if selected_category == "All Concrete Technologies":
                fig_skills = px.bar(
                    df_skills,
                    x="pct",
                    y="skill",
                    orientation="h",
                    text=df_skills["pct"].apply(lambda x: f"{x}%"),
                    color="category",
                    color_discrete_map=cat_colors,
                    labels={"pct": "% of Job Listings", "skill": "Technology / Skill", "category": "Category"},
                    title=f"🏆 Top In-Demand Technical Skills across Scraped Listings ({len(jobs)} Jobs Scanned)",
                )
            else:
                fig_skills = px.bar(
                    df_skills,
                    x="pct",
                    y="skill",
                    orientation="h",
                    text=df_skills["pct"].apply(lambda x: f"{x}%"),
                    color="pct",
                    color_continuous_scale="Blues",
                    labels={"pct": "% of Job Listings", "skill": "Technology / Skill"},
                    title=f"Top Skills in {selected_category} ({len(jobs)} Jobs)",
                )

            fig_skills.update_traces(textposition="outside")
            chart_height = max(420, len(df_skills) * 26 + 100)
            fig_skills.update_layout(
                yaxis={"categoryorder": "total ascending"},
                coloraxis_showscale=False,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                height=chart_height,
                margin=dict(l=20, r=60, t=50, b=20),
                font=dict(size=13),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            fig_skills.update_xaxes(range=[0, max(df_skills["pct"]) * 1.25])
            st.plotly_chart(fig_skills, use_container_width=True)

        else:
            st.info("No skill data available for this category yet.")
    else:
        st.info("📭 No job data yet. Run `python main.py` to fetch your first jobs.")

    # ── Company leaderboard ────────────────────────────────────────────────────
    st.markdown('<div class="section-header">🏆 Top Hiring Companies</div>', unsafe_allow_html=True)

    if jobs:
        from collections import Counter
        company_counts = Counter(j["company"] for j in jobs if j.get("company"))
        
        # Sort deterministically: count descending, then company name ascending
        sorted_companies = sorted(company_counts.items(), key=lambda x: (-x[1], x[0].lower()))
        top_companies = sorted_companies[:10]

        df_companies = pd.DataFrame(top_companies, columns=["Company", "Open Listings"])
        # In Plotly horizontal bar chart, categoryarray must be reversed to place the top row at the top
        ordered_categories = df_companies["Company"].iloc[::-1].tolist()

        fig_co = px.bar(
            df_companies,
            x="Open Listings",
            y="Company",
            orientation="h",
            color="Open Listings",
            color_continuous_scale="Teal",
            text="Open Listings",
        )
        fig_co.update_traces(textposition="outside")
        fig_co.update_layout(
            yaxis={"categoryorder": "array", "categoryarray": ordered_categories},
            coloraxis_showscale=False,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=380,
            margin=dict(l=20, r=40, t=20, b=20),
            font=dict(size=13),
        )
        st.plotly_chart(fig_co, use_container_width=True)
        st.caption(f"ℹ️ **{len(company_counts)}** unique companies are indexed. Displaying the most active employers with open student roles.")

        # Quick company navigation buttons to link with Tab 2
        st.markdown("**🔗 Quick Jump by Company (Open in Job Matcher):**")
        quick_cols = st.columns(min(len(top_companies), 5))
        for idx, (co_name, co_cnt) in enumerate(top_companies[:5]):
            with quick_cols[idx]:
                if st.button(f"🏢 {co_name} ({co_cnt})", key=f"tab1_link_co_{idx}", use_container_width=True):
                    st.session_state["filter_company"] = co_name
                    st.session_state["filter_source"] = "All"
                    st.session_state["main_nav_tab"] = "🎯 Job Matcher & Applications"
                    st.toast(f"🎯 Switched to Job Matcher filtered by '{co_name}'!")
                    st.rerun()

    # ── Source & Platform Intelligence Dashboard ──────────────────────────────
    if jobs:
        st.markdown('<div class="section-header">🌐 Job Sources & Platform Breakdown</div>', unsafe_allow_html=True)
        st.caption("Inspect which platforms jobs are scraped from; click any source or company to filter instantly.")

        SOURCE_DISPLAY_MAP = {
            "greenhouse": ("🏢 Greenhouse ATS", "#00A86B"),
            "personio": ("🎯 Personio ATS", "#3F51B5"),
            "berlinstartupjobs": ("🚀 Berlin Startup Jobs", "#FF6F00"),
            "linkedin": ("🔗 LinkedIn Jobs", "#0077B5"),
            "workwise": ("💼 Workwise.io", "#E91E63"),
            "jobteaser": ("🎓 JobTeaser", "#9C27B0"),
            "arbeitnow": ("🇩🇪 Arbeitnow", "#4CAF50"),
            "workingstudentjobs": ("📚 WorkingStudentJobs", "#FF9800"),
            "hiringcafe": ("☕ HiringCafe", "#795548"),
        }

        from collections import Counter
        source_counts = Counter(j.get("source", "other").lower() for j in jobs)

        source_stats = []
        for src_raw, count in source_counts.most_common():
            disp_name, color = SOURCE_DISPLAY_MAP.get(src_raw, (f"🌐 {src_raw.capitalize()}", "#607D8B"))
            src_companies = Counter(j.get("company", "") for j in jobs if j.get("source", "").lower() == src_raw and j.get("company"))
            top_src_cos = [c for c, _ in src_companies.most_common(4)]
            source_stats.append({
                "source_raw": src_raw,
                "display_name": disp_name,
                "color": color,
                "count": count,
                "pct": round(count / len(jobs) * 100, 1),
                "top_companies": top_src_cos,
                "company_count": len(src_companies),
            })

        col_src_chart, col_src_cards = st.columns([1.1, 1.4])

        with col_src_chart:
            df_src = pd.DataFrame(source_stats)
            fig_src = px.pie(
                df_src,
                values="count",
                names="display_name",
                hole=0.48,
                color="display_name",
                color_discrete_map={row["display_name"]: row["color"] for _, row in df_src.iterrows()},
                title=f"Platform Distribution ({len(jobs)} Jobs)",
            )
            fig_src.update_traces(
                textinfo="percent+value",
                textposition="inside",
                hovertemplate="<b>%{label}</b><br>Listings: %{value} (%{percent})<extra></extra>",
            )
            fig_src.update_layout(
                height=380,
                margin=dict(l=10, r=10, t=40, b=10),
                legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5),
            )
            st.plotly_chart(fig_src, use_container_width=True)

        with col_src_cards:
            st.markdown("**⚡ Quick Source & Company Navigation**")
            st.caption("Click any platform or company button to view its jobs directly:")

            for item in source_stats:
                with st.container():
                    c_info, c_btn = st.columns([2.2, 1.2])
                    with c_info:
                        st.markdown(
                            f"**{item['display_name']}** — <span style='color:{item['color']}; font-weight:bold;'>{item['count']} Jobs</span> "
                            f"<small>({item['pct']}%) • {item['company_count']} Companies</small>",
                            unsafe_allow_html=True
                        )
                        if item["top_companies"]:
                            co_tags = " • ".join(item["top_companies"])
                            st.caption(f"Featured Employers: *{co_tags}*")
                    with c_btn:
                        if st.button(
                            f"👉 View ({item['count']})",
                            key=f"tab1_src_jump_{item['source_raw']}",
                            use_container_width=True,
                            help=f"Open all jobs from {item['display_name']} in Job Matcher"
                        ):
                            st.session_state["filter_source"] = item["display_name"]
                            st.session_state["filter_company"] = "All"
                            st.session_state["main_nav_tab"] = "🎯 Job Matcher & Applications"
                            st.toast(f"🎯 Filtered by '{item['display_name']}' in Job Matcher!")
                            st.rerun()

                    if item["top_companies"]:
                        co_cols = st.columns(len(item["top_companies"]))
                        for c_idx, c_name in enumerate(item["top_companies"]):
                            with co_cols[c_idx]:
                                if st.button(
                                    f"🏢 {c_name}",
                                    key=f"tab1_co_btn_{item['source_raw']}_{c_idx}",
                                    use_container_width=True,
                                    help=f"Open jobs at {c_name}"
                                ):
                                    st.session_state["filter_company"] = c_name
                                    st.session_state["filter_source"] = "All"
                                    st.session_state["main_nav_tab"] = "🎯 Job Matcher & Applications"
                                    st.toast(f"🎯 Selected '{c_name}', switched to Job Matcher!")
                                    st.rerun()
                    st.divider()

    # ── Category breakdown pie ─────────────────────────────────────────────────
    if jobs:
        st.markdown('<div class="section-header">📂 Jobs by Category</div>', unsafe_allow_html=True)
        cats = Counter(j.get("category", "Uncategorized") or "Uncategorized" for j in jobs)
        fig_pie = px.pie(
            values=list(cats.values()),
            names=list(cats.keys()),
            color_discrete_sequence=px.colors.qualitative.Set3,
            hole=0.4,
        )
        fig_pie.update_layout(height=320, margin=dict(l=0, r=0, t=20, b=0))
        st.plotly_chart(fig_pie, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB — JOB MATCHER & APPLICATIONS
# ══════════════════════════════════════════════════════════════════════════════
elif active_tab == "🎯 Job Matcher & Applications":
    from src.match_analyzer import analyze_match
    cv = load_cv()

    def is_recent_job(fetched_at_str: str, posted_at_str: str = "", max_hours: int = 24) -> bool:
        """Check if job was fetched or posted in the last 24 hours."""
        now = datetime.now(timezone.utc)
        for raw in [fetched_at_str, posted_at_str]:
            if not raw:
                continue
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                diff = (now - dt).total_seconds()
                if 0 <= diff <= max_hours * 3600:
                    return True
            except Exception:
                try:
                    date_part = raw[:10]
                    if date_part == now.strftime("%Y-%m-%d"):
                        return True
                except Exception:
                    pass
        return False

    if not jobs:
        st.info("📭 No jobs found yet. Run `python main.py` to scrape your first listings.")
        st.stop()

    if not cv:
        st.warning("⚠️ `data/master_cv.json` not found. Please fill in your CV profile first.")
        st.stop()

    # ── Helper: External Job Importer ──────────────────────────────────────────
    def fetch_and_insert_external_job(url: str, custom_title: str = "", custom_company: str = "", custom_desc: str = "") -> Optional[int]:
        import urllib.request
        import hashlib
        import html
        import re
        from urllib.parse import quote
        from bs4 import BeautifulSoup
        from src.models import Job
        from src.match_analyzer import analyze_match
        from src.database import insert_job, _connection, normalize_company, normalize_title

        url_str = url.strip()
        title = custom_title.strip()
        company = custom_company.strip()
        desc = custom_desc.strip()
        location = "Berlin, Germany"
        source = "manual"
        canonical_url = url_str

        LOGIN_REJECT_TITLES = {
            "sign in", "login", "linkedin login", "log in",
            "security verification", "authwall", "welcome to linkedin",
            "anmelden", "einloggen"
        }

        # ── 1. Full Extraction from URL ──────────────────────────────────────
        if url_str:
            if "linkedin.com" in url_str.lower():
                source = "linkedin"
            elif "personio" in url_str.lower():
                source = "personio"
            elif "greenhouse" in url_str.lower():
                source = "greenhouse"
            elif "join.com" in url_str.lower():
                source = "join.com"
            elif "berlinstartupjobs" in url_str.lower():
                source = "berlinstartupjobs"

            try:
                from src.fetchers.extractor import extract_full_job
                extracted = extract_full_job(url_str)
                if not title and extracted.get("title"):
                    title = extracted["title"]
                if not company and extracted.get("company"):
                    company = extracted["company"]
                if not desc and extracted.get("description"):
                    desc = extracted["description"]
                if extracted.get("location"):
                    location = extracted["location"]
            except Exception as ext_err:
                logger.warning("Full extraction error: %s", ext_err)

        # Reject any leftover login wall keywords
        if title and (title.lower().strip() in LOGIN_REJECT_TITLES or title.lower().strip().startswith("sign in")):
            title = ""
        if desc and "login to linkedin" in desc.lower():
            desc = ""

        # Apply manual user overrides if provided
        if custom_title.strip():
            title = custom_title.strip()
        if custom_company.strip():
            company = custom_company.strip()
        if custom_desc.strip():
            desc = custom_desc.strip()

        title = title or "Imported Position"
        company = company or "Unknown Company"
        desc = desc or f"{title} position ({company})."
        final_job_url = canonical_url or url_str or f"https://www.google.com/search?q={quote(company)}+{quote(title)}"
        job_id = f"ext_{hashlib.md5((final_job_url or title + company).encode()).hexdigest()[:12]}"

        # Calculate match score against CV
        cv_data = load_cv()
        match_res = analyze_match(job_title=title, job_description=desc, cv=cv_data)
        calc_score = match_res.score if match_res else 50

        cat_lower = (title + " " + desc).lower()
        if any(w in cat_lower for w in ["qa", "testing", "tester", "quality assurance", "test automation"]):
            cat = "QA & Testing"
        elif any(w in cat_lower for w in ["tech support", "technical support", "it support", "helpdesk", "application support", "saas support", "tier 1", "tier 2"]):
            cat = "IT & Technical Support"
        elif any(w in cat_lower for w in ["software", "developer", "frontend", "backend", "fullstack", "devops", "cloud"]):
            cat = "Software & IT"
        elif any(w in cat_lower for w in ["data", "ai", "machine learning", "analytics", "business intelligence", "bi"]):
            cat = "Data & AI"
        else:
            cat = "Tech Ops & Business Tech"

        loc_lower = (location + " " + desc).lower()
        is_berlin = 1 if any(kw in loc_lower for kw in ["berlin"]) else 0
        is_remote = 1 if any(kw in loc_lower for kw in ["remote", "home office", "homeoffice", "remote-first"]) else 0

        job_obj = Job(
            job_id=job_id,
            title=title,
            company=company,
            location=location,
            url=final_job_url,
            description=desc,
            source=source,
            category=cat,
            match_score=calc_score,
            is_berlin=bool(is_berlin),
            is_remote=bool(is_remote),
            posted_at=datetime.now(timezone.utc).isoformat()[:10],
        )

        # Check if job already exists by URL, job_id, or title & company (cross-platform deduplication)
        norm_c = normalize_company(job_obj.company)
        norm_t = normalize_title(job_obj.title)
        with _connection() as conn:
            row = conn.execute(
                "SELECT id, title, status FROM jobs WHERE url = ? OR url = ? OR job_id = ?",
                (final_job_url, url_str, job_id)
            ).fetchone()
            if not row and norm_t and norm_c:
                # Check normalized title & company exact match
                row = conn.execute(
                    "SELECT id, title, status FROM jobs WHERE norm_title = ? AND norm_company = ?",
                    (norm_t, norm_c)
                ).fetchone()
                # Check fuzzy company match on same normalized title
                if not row:
                    cand_rows = conn.execute(
                        "SELECT id, norm_company FROM jobs WHERE norm_title = ?",
                        (norm_t,)
                    ).fetchall()
                    for cr in cand_rows:
                        ex_c = cr["norm_company"] or ""
                        if ex_c and (norm_c == ex_c or (len(norm_c) >= 3 and norm_c in ex_c) or (len(ex_c) >= 3 and ex_c in norm_c)):
                            row = cr
                            break

            if row:
                existing_id = row["id"]
                conn.execute(
                    """
                    UPDATE jobs
                    SET title = ?, company = ?, location = ?, description = ?,
                        match_score = ?, category = ?, is_berlin = ?, is_remote = ?,
                        url = ?, norm_title = ?, norm_company = ?
                    WHERE id = ?
                    """,
                    (
                        job_obj.title,
                        job_obj.company,
                        job_obj.location,
                        job_obj.description,
                        job_obj.match_score,
                        job_obj.category,
                        is_berlin,
                        is_remote,
                        job_obj.url,
                        norm_t,
                        norm_c,
                        existing_id,
                    )
                )
                conn.commit()
                return existing_id

        try:
            return insert_job(job_obj)
        except Exception as insert_err:
            logger.warning("Failed to insert job: %s", insert_err)
            return None


    # ── Job selector & Advanced Filters ────────────────────────────────────────
    st.markdown('<div class="section-header">📋 Job Selection & Smart Filters</div>',
                unsafe_allow_html=True)

    # ── Quick External Job Importer (LinkedIn, Personio, Greenhouse, etc.) ─────
    with st.expander("➕ 🔗 Import External Job URL (LinkedIn, Personio, Greenhouse, etc.)", expanded=False):
        st.caption("Paste any job listing URL from LinkedIn or company careers pages; title, company, and description will be extracted automatically:")
        col_url_in, col_url_btn = st.columns([4, 1.3])
        with col_url_in:
            ext_url = st.text_input(
                "Job Listing URL:",
                placeholder="https://www.linkedin.com/jobs/view/... or https://...jobs.personio.de/...",
                key="input_ext_job_url",
            )
        with col_url_btn:
            st.write("")
            st.write("")
            btn_import_url = st.button("🚀 Import & Analyze", type="primary", use_container_width=True, key="btn_import_ext_job")

        manual_override = st.checkbox("📝 Enter details manually if behind login / paywall (Optional)", value=False, key="chk_manual_ext_job")
        if manual_override:
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                ext_custom_title = st.text_input("Position Title:", placeholder="e.g. Working Student Data Analyst", key="input_ext_custom_title")
            with col_m2:
                ext_custom_company = st.text_input("Company Name:", placeholder="e.g. Zalando", key="input_ext_custom_company")
            ext_custom_desc = st.text_area("Job Description / Requirements:", placeholder="Paste requirements here...", height=120, key="input_ext_custom_desc")
        else:
            ext_custom_title = ""
            ext_custom_company = ""
            ext_custom_desc = ""

        if btn_import_url:
            if not ext_url.strip() and not ext_custom_desc.strip():
                st.warning("Please provide a valid URL or paste description text.")
            else:
                with st.spinner("Extracting job details, analyzing match against profile, and saving to CRM..."):
                    try:
                        imported_id = fetch_and_insert_external_job(
                            url=ext_url.strip(),
                            custom_title=ext_custom_title.strip(),
                            custom_company=ext_custom_company.strip(),
                            custom_desc=ext_custom_desc.strip(),
                        )
                        if imported_id:
                            st.session_state["selected_job_id"] = imported_id
                            st.session_state["filter_company"] = "All"
                            st.session_state["filter_source"] = "All"
                            st.session_state["matcher_search_kw"] = ""
                            st.session_state["matcher_sel_company"] = "All"
                            st.session_state["matcher_sel_source"] = "All"
                            st.session_state["matcher_sel_cat"] = "All"
                            st.session_state["matcher_sel_lang"] = "All"
                            st.session_state["matcher_sel_loc"] = "All"
                            st.session_state["matcher_sel_role"] = "All"
                            st.session_state["matcher_sel_status"] = "All"
                            st.session_state["matcher_min_score"] = 0
                            st.session_state["hide_applied"] = False
                            st.cache_data.clear()
                            st.toast("🎉 Job successfully imported and selected!")
                            st.rerun()
                        else:
                            st.error("Could not save job to database.")
                    except Exception as e:
                        st.error(f"Import error: {e}")

    # 1. Company choices & Cross-tab link support
    all_companies = ["All"] + sorted(list({j.get("company", "") for j in jobs if j.get("company")}))
    current_co_session = st.session_state.get("filter_company", "All")
    if current_co_session not in all_companies:
        current_co_session = "All"
        st.session_state["filter_company"] = "All"

    co_idx = all_companies.index(current_co_session)

    # 1b. Source choices & Cross-tab link support
    SOURCE_DISPLAY_MAP = {
        "greenhouse": "🏢 Greenhouse ATS",
        "personio": "🎯 Personio ATS",
        "berlinstartupjobs": "🚀 Berlin Startup Jobs",
        "linkedin": "🔗 LinkedIn Jobs",
        "workwise": "💼 Workwise.io",
        "jobteaser": "🎓 JobTeaser",
        "arbeitnow": "🇩🇪 Arbeitnow",
        "workingstudentjobs": "📚 WorkingStudentJobs",
        "hiringcafe": "☕ HiringCafe",
        "indeed": "🔍 Indeed",
    }
    raw_sources = sorted(list({j.get("source", "").lower() for j in jobs if j.get("source")}))
    source_display_names = ["All"] + [SOURCE_DISPLAY_MAP.get(s, f"🌐 {s.capitalize()}") for s in raw_sources]
    display_to_raw_source = {SOURCE_DISPLAY_MAP.get(s, f"🌐 {s.capitalize()}"): s for s in raw_sources}
    display_to_raw_source["All"] = "All"

    current_src_session = st.session_state.get("filter_source", "All")
    if current_src_session not in source_display_names:
        current_src_session = "All"
        st.session_state["filter_source"] = "All"

    src_idx = source_display_names.index(current_src_session)

    # Active filter banner
    active_filters = []
    if current_src_session != "All":
        active_filters.append(f"🌐 Source: **{current_src_session}**")
    if current_co_session != "All":
        active_filters.append(f"🏢 Company: **{current_co_session}**")

    if active_filters:
        c_banner, c_reset_banner = st.columns([4, 1.2])
        with c_banner:
            st.info("🎯 **Active Filter:** " + " | ".join(active_filters))
        with c_reset_banner:
            if st.button("❌ Clear Filters", key="btn_clear_banner_filter", use_container_width=True):
                st.session_state["filter_source"] = "All"
                st.session_state["filter_company"] = "All"
                st.rerun()

    # 2. Categories
    all_categories = ["All"] + sorted(list({j.get("category", "") for j in jobs if j.get("category")}))

    # ── Quick Toggles: Hide Applied & Show Only New Today ───────────────────
    col_tapp_1, col_tapp_2, col_tapp_3 = st.columns([2.5, 2.5, 1.6])
    with col_tapp_1:
        hide_applied = st.checkbox(
            "🎯 **Only Show Unapplied Jobs**",
            value=st.session_state.get("hide_applied", False),
            key="hide_applied",
            help="Hides jobs you have already marked as applied, keeping your view focused on fresh opportunities.",
        )
    with col_tapp_2:
        only_new_today = st.checkbox(
            "✨ **Only Show Today's New Jobs**",
            value=st.session_state.get("only_new_today", False),
            key="only_new_today",
            help="Shows only jobs fetched in the last 24 hours.",
        )
    with col_tapp_3:
        applied_total = sum(1 for j in jobs if j.get("status") in ("applied", "interview", "assessment"))
        recent_total = sum(1 for j in jobs if is_recent_job(j.get("fetched_at", ""), j.get("posted_at", "")))
        st.caption(f"✨ New Today: **{recent_total}** &nbsp;·&nbsp; ✅ Applied: **{applied_total}**")

    # ── Filter Row 1: Core Search, Company, Source, Category & Sort ───────────
    col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns([1.4, 1.1, 1.1, 1.0, 1.1])
    with col_f1:
        search_kw = st.text_input(
            "🔍 Search Jobs / Keywords:",
            value=st.session_state.get("matcher_search_kw", ""),
            placeholder="e.g. Python, AI, QA, Postman, Zalando...",
            key="matcher_search_kw",
        ).strip().lower()

    with col_f2:
        sel_company = st.selectbox(
            "🏢 Company:",
            all_companies,
            index=co_idx,
            key="matcher_sel_company",
        )
        if sel_company != st.session_state.get("filter_company"):
            st.session_state["filter_company"] = sel_company

    with col_f3:
        sel_source = st.selectbox(
            "🌐 Job Source:",
            source_display_names,
            index=src_idx,
            key="matcher_sel_source",
        )
        if sel_source != st.session_state.get("filter_source"):
            st.session_state["filter_source"] = sel_source

    with col_f4:
        sel_cat = st.selectbox("📂 Category:", all_categories, index=0, key="matcher_sel_cat")

    with col_f5:
        sort_by = st.selectbox(
            "🕒 Sort By:",
            [
                "🕒 Newest First",
                "⏳ Oldest First",
                "⭐ Highest Match Score",
                "📉 Lowest Match Score",
            ],
            index=0,
            key="matcher_sort_by",
        )

    # ── Filter Row 2: Advanced Criteria (Language, Location, Role, Status, Min Score) ──
    with st.expander("🎛️ Advanced Filters (Language, Location, Role Type, Min Score)", expanded=False):
        col_a1, col_a2, col_a3, col_a4 = st.columns([1.2, 1.2, 1.2, 1.3])

        LANG_OPTIONS = [
            "All",
            "Python",
            "SQL",
            "R",
            "TypeScript",
            "JavaScript",
            "C++",
            "C#",
            "Go",
            "Rust",
            "Java",
            "Bash",
            "Flutter / Dart",
        ]
        with col_a1:
            sel_lang = st.selectbox("💻 Programming Language:", LANG_OPTIONS, index=0, key="matcher_sel_lang")

        with col_a2:
            sel_loc = st.selectbox(
                "📍 Location / Mode:",
                [
                    "All",
                    "🏢 Berlin (Onsite/Hybrid)",
                    "🌐 Remote (Germany-wide)",
                    "🔄 Hybrid / Remote Option",
                ],
                index=0,
                key="matcher_sel_loc",
            )

        with col_a3:
            sel_role = st.selectbox(
                "🎓 Position Type:",
                [
                    "All",
                    "💼 Working Student (Werkstudent)",
                    "🔬 Internship (Praktikum / Thesis)",
                ],
                index=0,
                key="matcher_sel_role",
            )

        with col_a4:
            sel_status = st.selectbox(
                "📬 Application Status:",
                [
                    "All",
                    "🆕 Unreviewed (New)",
                    "⏳ Saved",
                    "✅ Applied / In Progress",
                ],
                index=0,
                key="matcher_sel_status",
            )

        col_slider, col_btn_reset = st.columns([3.5, 1])
        with col_slider:
            min_score = st.slider(
                "🎯 Minimum Match Score (%):",
                min_value=0,
                max_value=90,
                value=0,
                step=5,
                key="matcher_min_score",
            )
        with col_btn_reset:
            st.write("")
            st.write("")
            if st.button("🔄 Reset Filters", key="btn_clear_all_filters", use_container_width=True):
                st.session_state["filter_company"] = "All"
                st.session_state["filter_source"] = "All"
                st.session_state["matcher_search_kw"] = ""
                st.session_state["matcher_sel_company"] = "All"
                st.session_state["matcher_sel_source"] = "All"
                st.session_state["matcher_sel_cat"] = "All"
                st.session_state["matcher_sel_lang"] = "All"
                st.session_state["matcher_sel_loc"] = "All"
                st.session_state["matcher_sel_role"] = "All"
                st.session_state["matcher_sel_status"] = "All"
                st.session_state["matcher_min_score"] = 0
                st.session_state["hide_applied"] = False
                st.rerun()

    # ── Apply All Filters Sequentially ─────────────────────────────────────────
    # Baseline: Hazal specifically requires Berlin (onsite/hybrid) OR Germany-wide Remote only
    filtered_jobs_list = [
        j for j in jobs
        if j.get("is_berlin")
        or j.get("is_remote")
        or "berlin" in (j.get("location") or "").lower()
        or "remote" in (j.get("location") or "").lower()
    ]

    # 1. Company filter
    if sel_company != "All":
        filtered_jobs_list = [j for j in filtered_jobs_list if j.get("company") == sel_company]

    # 1b. Source filter
    if sel_source != "All":
        raw_s = display_to_raw_source.get(sel_source, sel_source.lower())
        filtered_jobs_list = [j for j in filtered_jobs_list if j.get("source", "").lower() == raw_s]

    # 2. Category filter
    if sel_cat != "All":
        filtered_jobs_list = [j for j in filtered_jobs_list if j.get("category") == sel_cat]

    # 3. Free text search
    if search_kw:
        filtered_jobs_list = [
            j for j in filtered_jobs_list
            if search_kw in j.get("title", "").lower()
            or search_kw in j.get("company", "").lower()
            or search_kw in (j.get("description", "") or "").lower()
        ]

    # 4. Programming language filter
    if sel_lang != "All":
        lang_regex_map = {
            "Python": r"\bpython\b",
            "SQL": r"\bsql\b",
            "R": r"\b(r\s+studio|r-project|r\s+language|r\s+programming|\br\b(?!\s*&\s*d))\b",
            "TypeScript": r"\b(typescript|ts)\b",
            "JavaScript": r"\b(javascript|js)\b",
            "C++": r"\bc\+\+\b",
            "C#": r"\bc#\b",
            "Go": r"\b(go|golang)\b",
            "Rust": r"\brust\b",
            "Java": r"\bjava\b",
            "Bash": r"\b(bash|shell)\b",
            "Flutter / Dart": r"\b(flutter|dart)\b",
        }
        pat_str = lang_regex_map.get(sel_lang, rf"\b{re.escape(sel_lang.lower())}\b")
        pat = re.compile(pat_str, re.IGNORECASE)
        filtered_jobs_list = [
            j for j in filtered_jobs_list
            if pat.search(f"{j.get('title', '')} {j.get('description', '')}")
        ]

    # 5. Location / Work mode filter
    if sel_loc == "🏢 Berlin (Onsite/Hybrid)":
        filtered_jobs_list = [
            j for j in filtered_jobs_list
            if j.get("is_berlin") or "berlin" in j.get("location", "").lower()
        ]
    elif sel_loc == "🌐 Remote (Germany-wide)":
        filtered_jobs_list = [
            j for j in filtered_jobs_list
            if j.get("is_remote") or "remote" in j.get("location", "").lower()
        ]
    elif sel_loc == "🔄 Hybrid / Remote Option":
        filtered_jobs_list = [
            j for j in filtered_jobs_list
            if j.get("is_remote") or any(kw in (f"{j.get('location', '')} {j.get('description', '')}").lower() for kw in ["hybrid", "remote", "home office", "homeoffice"])
        ]

    # 6. Role type filter
    if sel_role == "💼 Working Student (Werkstudent)":
        filtered_jobs_list = [
            j for j in filtered_jobs_list
            if any(kw in f"{j.get('title', '')} {j.get('description', '')}".lower() for kw in ["working student", "werkstudent", "student assistant", "werkstudentin", "werkstudent:in"])
        ]
    elif sel_role == "🔬 Internship (Praktikum / Thesis)":
        filtered_jobs_list = [
            j for j in filtered_jobs_list
            if any(kw in f"{j.get('title', '')} {j.get('description', '')}".lower() for kw in ["intern", "internship", "praktik", "praktikant", "praktikum", "thesis", "master thesis"])
        ]

    # 7. Status filter
    if sel_status == "🆕 Unreviewed (New)":
        filtered_jobs_list = [j for j in filtered_jobs_list if j.get("status", "new") == "new"]
    elif sel_status == "⏳ Saved":
        filtered_jobs_list = [j for j in filtered_jobs_list if j.get("status") == "saved"]
    elif sel_status == "✅ Applied / In Progress":
        filtered_jobs_list = [j for j in filtered_jobs_list if j.get("status") in ("applied", "interview", "assessment")]

    # 7b. Quick Toggle: Hide Applied Jobs
    if hide_applied and sel_status != "✅ Applied / In Progress":
        filtered_jobs_list = [j for j in filtered_jobs_list if j.get("status") not in ("applied", "interview", "assessment")]

    # 7c. Quick Toggle: Show Only New Jobs Today (< 24 hours)
    if only_new_today:
        filtered_jobs_list = [j for j in filtered_jobs_list if is_recent_job(j.get("fetched_at", ""), j.get("posted_at", ""))]

    # 8. Minimum Match Score filter
    if min_score > 0:
        filtered_jobs_list = [j for j in filtered_jobs_list if j.get("match_score", 0) >= min_score]

    # ── Apply Sorting ──────────────────────────────────────────────────────────
    if sort_by == "🕒 Newest First":
        filtered_jobs_list.sort(key=lambda j: (j.get("posted_at") or j.get("fetched_at") or "", j.get("id", 0)), reverse=True)
    elif sort_by == "⏳ Oldest First":
        filtered_jobs_list.sort(key=lambda j: (j.get("posted_at") or j.get("fetched_at") or "", j.get("id", 0)), reverse=False)
    elif sort_by == "⭐ Highest Match Score":
        filtered_jobs_list.sort(key=lambda j: j.get("match_score", 0), reverse=True)
    elif sort_by == "📉 Lowest Match Score":
        filtered_jobs_list.sort(key=lambda j: j.get("match_score", 0), reverse=False)

    # ── Active Filter Summary & Counter ───────────────────────────────────────
    active_filters = []
    if only_new_today:
        active_filters.append("✨ **New Today**")
    if hide_applied:
        active_filters.append("🎯 **Applied Jobs Hidden**")
    if sel_company != "All":
        active_filters.append(f"🏢 **Company:** {sel_company}")
    if sel_cat != "All":
        active_filters.append(f"📂 **Category:** {sel_cat}")
    if sel_lang != "All":
        active_filters.append(f"💻 **Language:** {sel_lang}")
    if sel_loc != "All":
        active_filters.append(f"📍 **Location:** {sel_loc}")
    if sel_role != "All":
        active_filters.append(f"🎓 **Type:** {sel_role}")
    if sel_status != "All":
        active_filters.append(f"📬 **Status:** {sel_status}")
    if min_score > 0:
        active_filters.append(f"🎯 **Min Score:** {min_score}%+")
    if search_kw:
        active_filters.append(f"🔍 **Keyword:** \"{search_kw}\"")

    if active_filters:
        badges_str = " &nbsp;|&nbsp; ".join(active_filters)
        st.markdown(f"<div style='background-color: #f1f5f9; border-radius: 6px; padding: 6px 12px; font-size: 13px; margin-bottom: 12px; color: #334155;'><b>Active Filters:</b> {badges_str} &nbsp;&nbsp; <b>({len(filtered_jobs_list)} / {len(jobs)} jobs)</b></div>", unsafe_allow_html=True)
    else:
        st.markdown(f"🎯 **Showing {len(filtered_jobs_list)} matching jobs** (Select any job to review in depth):")

    if not filtered_jobs_list:
        st.warning("⚠️ No jobs match your filter criteria. Try clearing or expanding your filters.")
        if st.button("🔄 Reset All Filters", key="btn_no_results_reset"):
            st.session_state["filter_company"] = "All"
            st.session_state["matcher_search_kw"] = ""
            st.session_state["matcher_sel_company"] = "All"
            st.session_state["matcher_sel_cat"] = "All"
            st.session_state["matcher_sel_lang"] = "All"
            st.session_state["matcher_sel_loc"] = "All"
            st.session_state["matcher_sel_role"] = "All"
            st.session_state["matcher_sel_status"] = "All"
            st.session_state["matcher_min_score"] = 0
            st.session_state["hide_applied"] = False
            st.rerun()
        st.stop()

    # ── Master-Detail Layout: Left = Job List, Right = Selected Job Deep Dive ──
    if "selected_job_id" not in st.session_state or not any(j["id"] == st.session_state.selected_job_id for j in filtered_jobs_list):
        st.session_state.selected_job_id = filtered_jobs_list[0]["id"]

    selected_job = next((j for j in filtered_jobs_list if j["id"] == st.session_state.selected_job_id), filtered_jobs_list[0])

    col_job_list, col_job_detail = st.columns([1.15, 1.85], gap="medium")

    # ── Left Column: Scrollable Job Card List ──────────────────────────────────
    with col_job_list:
        PAGE_SIZE = 15
        total_jobs_cnt = len(filtered_jobs_list)
        total_pages = max(1, (total_jobs_cnt + PAGE_SIZE - 1) // PAGE_SIZE)

        if "job_page_num" not in st.session_state:
            st.session_state["job_page_num"] = 1

        # Keep current page valid
        if st.session_state["job_page_num"] > total_pages:
            st.session_state["job_page_num"] = total_pages
        if st.session_state["job_page_num"] < 1:
            st.session_state["job_page_num"] = 1

        curr_page = st.session_state["job_page_num"]
        start_idx = (curr_page - 1) * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, total_jobs_cnt)
        page_jobs = filtered_jobs_list[start_idx:end_idx]

        col_hdr_l, col_hdr_r = st.columns([1.5, 1])
        with col_hdr_l:
            st.markdown(f"##### 📋 Job Listings ({total_jobs_cnt})")
        with col_hdr_r:
            st.caption(f"Page {curr_page} of {total_pages}")

        with st.container(height=720):
            for j in page_jobs:
                is_sel = (j["id"] == selected_job["id"])
                status = (j.get("status") or "new").lower()
                is_applied = status in ("applied", "interview", "assessment")
                is_saved = (status == "saved")
                score = j.get("match_score", 0)
                badge_bg = "#10b981" if score >= 70 else ("#3b82f6" if score >= 50 else "#f59e0b")
                date_str = j.get("posted_at") or (j.get("fetched_at", "")[:10]) or "New"
                applied_date_str = j.get("applied_at") or ""

                if is_sel:
                    border_style = "2px solid #2563eb"
                    border_left = "6px solid #10b981" if is_applied else ("6px solid #f59e0b" if is_saved else "6px solid #2563eb")
                    bg_color = "#f0fdf4" if is_applied else "#eff6ff"
                elif is_applied:
                    border_style = "1px solid #86efac"
                    border_left = "6px solid #10b981"
                    bg_color = "#f0fdf4"
                elif is_saved:
                    border_style = "1px solid #fde68a"
                    border_left = "6px solid #f59e0b"
                    bg_color = "#fffbeb"
                else:
                    border_style = "1px solid #e2e8f0"
                    border_left = "1px solid #e2e8f0"
                    bg_color = "#ffffff"

                # Badges & Status Meta
                is_recent = is_recent_job(j.get("fetched_at", ""), j.get("posted_at", ""))
                recent_badge = '<span style="background: linear-gradient(135deg, #f97316 0%, #ea580c 100%); color: white; padding: 2px 7px; border-radius: 6px; font-weight: 700; font-size: 10px; white-space: nowrap; box-shadow: 0 1px 3px rgba(234,88,12,0.3); display: inline-flex; align-items: center; gap: 3px;">🔥 NEW</span>' if is_recent else ''

                if is_applied:
                    status_badge = '<span style="background-color: #10b981; color: white; padding: 2px 8px; border-radius: 6px; font-weight: 700; font-size: 11px; white-space: nowrap; box-shadow: 0 1px 2px rgba(16,185,129,0.25);">✅ APPLIED</span>'
                    date_info = f'✅ Applied: <b>{applied_date_str or date_str}</b> &nbsp;·&nbsp; 🏷️ {j.get("category", "Tech")}'
                    status_color = "#166534"
                elif is_saved:
                    status_badge = '<span style="background-color: #f59e0b; color: white; padding: 2px 7px; border-radius: 6px; font-weight: 700; font-size: 11px; white-space: nowrap;">⏳ Saved</span>'
                    date_info = f'⏳ Saved &nbsp;·&nbsp; 🏷️ {j.get("category", "Tech")} &nbsp;·&nbsp; 📅 {date_str}'
                    status_color = "#b45309"
                else:
                    status_badge = ''
                    date_prefix = '✨ Added Today' if is_recent else f'📅 {date_str}'
                    date_info = f'🏷️ {j.get("category", "Tech")} &nbsp;·&nbsp; {date_prefix}'
                    status_color = "#ea580c" if is_recent else "#64748b"

                clean_title = html.escape(str(j.get("title", "")))
                clean_company = html.escape(str(j.get("company", "")))
                raw_loc = str(j.get("location", "Berlin"))
                is_rem = bool(j.get("is_remote")) or "remote" in raw_loc.lower()
                is_ber = bool(j.get("is_berlin")) or "berlin" in raw_loc.lower()

                if is_ber and is_rem:
                    loc_display = "🏢 Berlin (Hybrid / Remote)"
                elif is_ber:
                    loc_display = "🏢 Berlin"
                elif is_rem:
                    loc_display = "🌐 Remote (Germany-wide)"
                else:
                    loc_display = f"📍 {html.escape(raw_loc)}"

                card_html = (
                    f'<div style="border: {border_style}; border-left: {border_left}; background-color: {bg_color}; border-radius: 8px; padding: 10px 12px; margin-bottom: 4px;">'
                    f'<div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">'
                    f'<span style="font-weight: 700; font-size: 13px; color: #0f172a; line-height: 1.3;">{clean_title}</span>'
                    f'<div style="display: flex; align-items: center; gap: 5px; flex-shrink: 0;">'
                    f'{recent_badge}'
                    f'{status_badge}'
                    f'<span style="background-color: {badge_bg}; color: white; padding: 2px 7px; border-radius: 6px; font-weight: 700; font-size: 11px; white-space: nowrap;">%{score}</span>'
                    f'</div>'
                    f'</div>'
                    f'<div style="font-size: 12px; color: #475569; margin-top: 4px;">🏢 <b>{clean_company}</b> &nbsp;·&nbsp; {loc_display}</div>'
                    f'<div style="font-size: 11px; color: {status_color}; margin-top: 4px; font-weight: {"600" if (is_applied or is_recent) else "400"};">{date_info}</div>'
                    f'</div>'
                )
                st.markdown(card_html, unsafe_allow_html=True)

                col_btn_pick, col_btn_del = st.columns([5, 1.4])
                with col_btn_pick:
                    if st.button("👉 Selected" if is_sel else "🔍 Review Job", key=f"btn_pick_{j['id']}", use_container_width=True, disabled=is_sel):
                        st.session_state.selected_job_id = j["id"]
                        st.rerun()
                with col_btn_del:
                    if st.button("🗑️ Delete", key=f"btn_card_del_{j['id']}", help="Permanently delete this job from CRM", use_container_width=True):
                        db.delete_job(j["id"])
                        if st.session_state.get("selected_job_id") == j["id"]:
                            st.session_state.selected_job_id = None
                        st.cache_data.clear()
                        st.toast(f"🗑️ Deleted {j.get('company', 'job')} from database!")
                        st.rerun()

                st.markdown("<div style='margin-bottom: 8px;'></div>", unsafe_allow_html=True)

        if total_pages > 1:
            col_prev, col_pg_info, col_next = st.columns([1, 1.2, 1])
            with col_prev:
                if st.button("◀ Previous", disabled=(curr_page <= 1), use_container_width=True, key="btn_prev_job_page"):
                    st.session_state["job_page_num"] = max(1, curr_page - 1)
                    st.rerun()
            with col_pg_info:
                st.markdown(f"<div style='text-align:center; padding-top:6px; font-size:12px; font-weight:600; color:#475569;'>{start_idx + 1}–{end_idx} of {total_jobs_cnt}</div>", unsafe_allow_html=True)
            with col_next:
                if st.button("Next ▶", disabled=(curr_page >= total_pages), use_container_width=True, key="btn_next_job_page"):
                    st.session_state["job_page_num"] = min(total_pages, curr_page + 1)
                    st.rerun()

    # ── Right Column: Selected Job Details & AI Engine ────────────────────────
    with col_job_detail:
        sel_is_recent = is_recent_job(selected_job.get("fetched_at", ""), selected_job.get("posted_at", ""))
        recent_chip_html = ' &nbsp;·&nbsp; <span style="background: linear-gradient(135deg, #f97316 0%, #ea580c 100%); color: white; padding: 2px 7px; border-radius: 6px; font-weight: 700; font-size: 11px;">🔥 Added Today</span>' if sel_is_recent else ''
        sel_raw_loc = str(selected_job.get("location", "Berlin"))
        sel_is_rem = bool(selected_job.get("is_remote")) or "remote" in sel_raw_loc.lower()
        sel_is_ber = bool(selected_job.get("is_berlin")) or "berlin" in sel_raw_loc.lower()
        if sel_is_ber and sel_is_rem:
            loc_detail_display = "🏢 Berlin (Hybrid / Remote)"
        elif sel_is_ber:
            loc_detail_display = "🏢 Berlin"
        elif sel_is_rem:
            loc_detail_display = "🌐 Remote (Germany-wide)"
        else:
            loc_detail_display = f"📍 {html.escape(sel_raw_loc)}"

        st.markdown(f"### {selected_job['title']}")
        st.markdown(f"<div style='font-size: 13px; color: #475569; margin-bottom: 6px;'>🏢 <b>{html.escape(str(selected_job['company']))}</b> &nbsp;·&nbsp; {loc_detail_display} &nbsp;·&nbsp; 🏷️ {html.escape(str(selected_job.get('category', 'Tech')))}{recent_chip_html}</div>", unsafe_allow_html=True)
        st.markdown(f"[🔗 View Original Listing ({selected_job.get('source', 'Web')})]({selected_job.get('url', '#')})")

        # Status Actions & Banner
        app_status = (selected_job.get("status") or "new").lower()
        if app_status in ("applied", "interview", "assessment"):
            app_date = selected_job.get("applied_at") or selected_job.get("fetched_at", "")[:10]
            st.success(f"✅ **Applied to this position!** &nbsp;·&nbsp; 📅 Applied Date: **{app_date}** &nbsp;·&nbsp; Status: **{app_status.capitalize()}**")
            col_s1, col_s2, col_s3 = st.columns([1.2, 1, 0.8])
            with col_s1:
                if st.button("↩️ Revert to New", key=f"btn_undo_{selected_job['id']}", use_container_width=True, help="Resets status back to 'New'"):
                    db.update_status(selected_job["id"], "new")
                    st.cache_data.clear()
                    st.rerun()
            with col_s2:
                if st.button("⏳ Move to Saved", key=f"btn_sav_{selected_job['id']}", use_container_width=True):
                    db.update_status(selected_job["id"], "saved")
                    st.cache_data.clear()
                    st.rerun()
            with col_s3:
                if st.button("🗑️ Delete", key=f"btn_del_applied_{selected_job['id']}", use_container_width=True, help="Permanently delete from database"):
                    db.delete_job(selected_job["id"])
                    st.session_state.selected_job_id = None
                    st.cache_data.clear()
                    st.toast("🗑️ Job deleted from database!")
                    st.rerun()
        else:
            st.markdown("**Quick Status Update & Actions:**")
            col_s1, col_s2, col_s3, col_s4 = st.columns([1, 1, 1, 1])
            with col_s1:
                if st.button("✅ Mark Applied", key=f"btn_app_{selected_job['id']}", type="primary", use_container_width=True):
                    db.update_status(selected_job["id"], "applied")
                    st.cache_data.clear()
                    st.rerun()
            with col_s2:
                if st.button("⏳ Save", key=f"btn_sav_{selected_job['id']}", use_container_width=True):
                    db.update_status(selected_job["id"], "saved")
                    st.cache_data.clear()
                    st.rerun()
            with col_s3:
                if st.button("❌ Skip", key=f"btn_skp_{selected_job['id']}", use_container_width=True):
                    db.update_status(selected_job["id"], "skipped")
                    st.cache_data.clear()
                    st.rerun()
            with col_s4:
                if st.button("🗑️ Delete", key=f"btn_del_unapplied_{selected_job['id']}", use_container_width=True, help="Permanently delete from database"):
                    db.delete_job(selected_job["id"])
                    st.session_state.selected_job_id = None
                    st.cache_data.clear()
                    st.toast("🗑️ Job deleted from database!")
                    st.rerun()

        # Job details expander
        job_desc = selected_job.get("description", "")
        with st.expander(f"📄 View Job Description ({len(job_desc):,} characters)", expanded=False):
            col_d_info, col_d_btn = st.columns([2.2, 1.2])
            with col_d_info:
                if len(job_desc) < 350:
                    st.warning("⚠️ This listing may be short or a preview snippet. Click the button to refetch the full description.")
                else:
                    st.caption(f"Description Length: **{len(job_desc):,}** characters")
            with col_d_btn:
                if selected_job.get("url") and st.button("🌐 Refetch Full Text from Web", key=f"btn_refetch_{selected_job['id']}", help="Visits the listing URL to extract the complete job posting."):
                    with st.spinner("Extracting complete description from source URL..."):
                        from src.fetchers.extractor import extract_full_job
                        ext_res = extract_full_job(selected_job["url"])
                        if ext_res.get("description") and len(ext_res["description"]) > len(job_desc):
                            with _connection() as conn:
                                conn.execute(
                                    "UPDATE jobs SET description = ?, title = COALESCE(NULLIF(?, ''), title), company = COALESCE(NULLIF(?, ''), company) WHERE id = ?",
                                    (ext_res["description"], ext_res.get("title", ""), ext_res.get("company", ""), selected_job["id"])
                                )
                            st.cache_data.clear()
                            st.success(f"🎉 Full description extracted! ({len(ext_res['description']):,} characters)")
                            st.rerun()
                        else:
                            st.info("No longer text found or page is behind security wall.")

            if job_desc:
                st.text_area("Job Description", job_desc, height=280, disabled=True)

        st.markdown('<div class="section-header">⚡ Skill Gap & Profile Match Analysis</div>', unsafe_allow_html=True)

        result = get_cached_match(
            job_title=selected_job.get("title", ""),
            job_description=selected_job.get("description", ""),
            cv_data=cv,
        )

        # Score gauge
        col_gauge, col_details = st.columns([1, 1.8])

        with col_gauge:
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=result.score,
                domain={"x": [0, 1], "y": [0, 1]},
                title={"text": "Initial Match Score", "font": {"size": 15}},
                number={"suffix": "%", "font": {"size": 32}},
                gauge={
                    "axis": {"range": [0, 100], "tickwidth": 1},
                    "bar": {"color": "#3b82f6"},
                    "bgcolor": "white",
                    "borderwidth": 2,
                    "bordercolor": "#e2e8f0",
                    "steps": [
                        {"range": [0, 40],  "color": "#fee2e2"},
                        {"range": [40, 70], "color": "#fef3c7"},
                        {"range": [70, 100],"color": "#d1fae5"},
                    ],
                    "threshold": {
                        "line": {"color": "#1d4ed8", "width": 4},
                        "thickness": 0.75,
                        "value": result.score,
                    },
                },
            ))
            fig_gauge.update_layout(
                height=230,
                margin=dict(l=15, r=15, t=35, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_gauge, use_container_width=True)

        with col_details:
            st.markdown(f"**{len(result.all_job_keywords)}** keywords detected in listing")
            st.markdown(f"✅ **{len(result.found_skills)}** present in CV &nbsp;·&nbsp; "
                        f"❌ **{len(result.missing_skills)}** missing / not highlighted")
            st.markdown("")

            # Found skills — green tags
            if result.found_skills:
                st.markdown("✅ **Strengths in CV:**")
                tags_html = " ".join(
                    f'<span class="skill-tag-green">{s.title()}</span>'
                    for s in result.found_skills
                )
                st.markdown(tags_html, unsafe_allow_html=True)

            st.markdown("")

            # Missing skills — red tags
            if result.missing_skills:
                st.markdown("❌ **Missing Skills Requested:**")
                tags_html = " ".join(
                    f'<span class="skill-tag-red">{s.title()}</span>'
                    for s in result.missing_skills
                )
                st.markdown(tags_html, unsafe_allow_html=True)
            else:
                st.success("🎉 No critical skill gaps detected — strong match!")

        # ── Gemini Deep Job & Skill Gap Analysis ───────────────────────────────────
        analysis_key = f"deep_analysis_{selected_job['id']}"
        col_deep1, col_deep2 = st.columns([1.5, 2.5])
        with col_deep1:
            run_deep = st.button("🧠 Gemini Deep Job Analysis", key=f"btn_{analysis_key}", help="Semantically analyzes the job listing and your CV with Gemini; reports role focus, strategic fit, and skill gaps.")

        if run_deep or (analysis_key in st.session_state):
            if run_deep or analysis_key not in st.session_state:
                with st.spinner("🤖 Gemini is deeply analyzing the job listing and your CV..."):
                    from src.ai_assistant import analyze_job_with_gemini
                    deep_res = analyze_job_with_gemini(
                        job_title=selected_job.get("title", ""),
                        job_company=selected_job.get("company", ""),
                        job_description=selected_job.get("description", ""),
                        cv=cv,
                    )
                    st.session_state[analysis_key] = deep_res
            else:
                deep_res = st.session_state[analysis_key]

            if deep_res:
                with st.container(border=True):
                    st.markdown(f"**🎯 Role Focus:** {deep_res.get('role_summary', '')}")
                    if deep_res.get("strategic_advice"):
                        st.info(f"💡 **Application Strategy:** {deep_res['strategic_advice']}")

                    col_str, col_mis = st.columns(2)
                    with col_str:
                        st.markdown("✅ **Key Strengths in CV:**")
                        for st_item in deep_res.get("key_strengths", []):
                            st.markdown(f"- {st_item}")
                    with col_mis:
                        st.markdown("⚠️ **Areas to Highlight / Gaps:**")
                        for ms_item in deep_res.get("missing_areas", []):
                            st.markdown(f"- {ms_item}")

                    if deep_res.get("required_skills"):
                        with st.expander("📋 True Role Requirements & Skill Breakdown", expanded=False):
                            for r_item in deep_res["required_skills"]:
                                icon = "✅" if r_item.get("status") == "matched" else "⚠️"
                                st.markdown(f"{icon} **{r_item.get('skill', '')}**: {r_item.get('explanation', '')}")

        # ── AI Optimization Engine ─────────────────────────────────────────────────
        st.markdown('<div class="section-header">🚀 Gemini AI Optimization Engine</div>',
                    unsafe_allow_html=True)

        col_pkg, col_btn1, col_btn2, col_btn3 = st.columns([2.0, 1.4, 1.4, 1.2])

        # ── Button 0: Full Package (Parallel CV + Cover Letter) ───────────────────
        with col_pkg:
            package_clicked = st.button(
                "⚡ Full Application Package (CV + Cover Letter)",
                use_container_width=True,
                type="primary",
                help="Runs CV tailoring and Cover Letter generation concurrently in the background for 2x faster preparation (~15–20s).",
            )

        # ── Button 1: Optimize CV ─────────────────────────────────────────────────
        with col_btn1:
            optimize_clicked = st.button(
                "🚀 Tailor CV Only",
                use_container_width=True,
                help="Gemini seamlessly weaves missing skills into relevant past experience and boosts ATS score",
            )

        # ── Button 2: Generate Cover Letter ──────────────────────────────────────
        with col_btn2:
            cover_clicked = st.button(
                "📝 Cover Letter Only",
                use_container_width=True,
                help="Gemini generates a tailored, role-specific cover letter based on your CV and the job description",
            )

        # ── Button 3: Download Base CV ───────────────────────────────────────────
        with col_btn3:
            try:
                base_pdf_bytes = get_cached_cv_pdf(cv)
                candidate_name = cv.get("personal", {}).get("name", "Candidate")
                safe_cand = "".join(c for c in candidate_name if c.isalnum() or c in " _-").strip().replace(" ", "_") or "CV"
                st.download_button(
                    label="📄 Base CV",
                    data=base_pdf_bytes,
                    file_name=f"{safe_cand}_Base_CV.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    help="Downloads the active candidate profile's base CV in ATS-compatible PDF format",
                )
            except Exception:
                pass

        # ── Full Package (Parallel Execution) ───────────────────────────────────
        if package_clicked:
            if not os.getenv("GEMINI_API_KEY"):
                st.error("❌ GEMINI_API_KEY not configured. Please check your .env file.")
            else:
                with st.spinner("⚡ Gemini is preparing your application package… (~3–5s)"):
                    try:
                        from concurrent.futures import ThreadPoolExecutor
                        from src.models import Job as JobModel
                        from src.match_analyzer import analyze_match
                        from src.ai_assistant import (
                            optimize_cv_for_job,
                            build_tailored_cv_data,
                            generate_cover_letter,
                        )

                        job_obj = JobModel(
                            job_id=str(selected_job.get("id", "dash")),
                            source=selected_job.get("source", "dashboard"),
                            title=selected_job.get("title", ""),
                            company=selected_job.get("company", ""),
                            location=selected_job.get("location", ""),
                            url=selected_job.get("url", ""),
                            description=selected_job.get("description", ""),
                        )

                        # Parallel execution: optimize CV and generate Cover Letter concurrently
                        with ThreadPoolExecutor(max_workers=2) as executor:
                            future_cv = executor.submit(
                                optimize_cv_for_job,
                                job_title=selected_job.get("title", ""),
                                job_company=selected_job.get("company", ""),
                                job_description=selected_job.get("description", ""),
                                found_skills=result.found_skills,
                                missing_skills=result.missing_skills,
                                cv=cv,
                                current_score=result.score,
                            )
                            future_cl = executor.submit(
                                generate_cover_letter,
                                job_obj,
                            )
                            opt = future_cv.result()
                            cl_text = future_cl.result()

                        # 1. Save Cover Letter into session state
                        st.session_state[f"cover_letter_{selected_job.get('id')}"] = cl_text

                        # 2. Build tailored full CV & store into working session state
                        tailored_cv = build_tailored_cv_data(opt, cv, company=selected_job.get("company", ""))
                        st.session_state["tailored_cv_working"] = tailored_cv
                        st.session_state["tailored_cv_job_id"] = str(selected_job.get("id"))

                        tailored_match = analyze_match(
                            job_title=selected_job.get("title", ""),
                            job_description=selected_job.get("description", ""),
                            cv=tailored_cv,
                        )
                        raw_est = opt.get("estimated_new_score", result.score)
                        final_new_score = max(result.score, tailored_match.score, raw_est)
                        if result.score >= 100:
                            final_new_score = 100
                        else:
                            final_new_score = min(100, max(result.score, final_new_score))

                        st.session_state["cv_opt_meta"] = {
                            "original_score": result.score,
                            "estimated_new_score": final_new_score,
                            "optimization_notes": opt.get("optimization_notes", ""),
                            "added_technologies": opt.get("added_technologies", []),
                            "key_changes": opt.get("key_changes", []),
                        }

                        if result.score >= 100:
                            score_msg = (
                                f"Your current CV was already at a **{result.score}% (Flawless Match)** level for this role! "
                                f"Bullet points and achievement metrics were tailored specifically to this opening while preserving 100% ATS alignment ✨\n\n"
                            )
                        elif final_new_score > result.score:
                            score_msg = (
                                f"Estimated ATS match score boosted from **{result.score}% → {final_new_score}%** 🚀\n\n"
                            )
                        else:
                            score_msg = (
                                f"CV optimized with role-specific keywords and impact metrics (ATS Score: **{final_new_score}%**) ✨\n\n"
                            )

                        feedback_details = []
                        if opt.get("added_technologies"):
                            techs_str = ", ".join(f"`{t}`" for t in opt.get("added_technologies", []))
                            feedback_details.append(f"🎯 **Added / Highlighted Technologies:** {techs_str}")
                        if opt.get("key_changes"):
                            changes_str = "\n".join(f"  • {c}" for c in opt.get("key_changes", []))
                            feedback_details.append(f"💡 **Key Improvements Made:**\n{changes_str}")
                        elif opt.get("optimization_notes"):
                            feedback_details.append(f"💡 **Optimization Summary:** {opt.get('optimization_notes')}")

                        feedback_copilot_txt = ("\n\n" + "\n\n".join(feedback_details)) if feedback_details else ""
                        job_id_key = str(selected_job.get("id"))

                        # 1. Store tailored CV and Cover Letter with job-specific keys
                        st.session_state[f"tailored_cv_{job_id_key}"] = tailored_cv
                        st.session_state[f"cv_opt_meta_{job_id_key}"] = st.session_state["cv_opt_meta"]
                        st.session_state[f"cover_letter_{job_id_key}"] = cl_text

                        # 2. Store job-specific chat histories
                        st.session_state[f"cv_copilot_messages_{job_id_key}"] = [
                            {
                                "role": "assistant",
                                "content": (
                                    f"🎯 Successfully tailored your CV for **{selected_job.get('company', '')}** ({selected_job.get('title', '')})!\n\n"
                                    f"{score_msg}"
                                    f"{feedback_copilot_txt}\n\n"
                                    f"• Review real-time changes in the live preview on the left, or brainstorm and request custom revisions in this chat."
                                ),
                            }
                        ]

                        st.session_state[f"cl_copilot_messages_{job_id_key}"] = [
                            {
                                "role": "assistant",
                                "content": (
                                    f"✍️ Generated a tailored Cover Letter for **{selected_job.get('company', '')}** ({selected_job.get('title', '')})!\n\n"
                                    f"• Read your letter in the preview card on the left and download it as PDF or Word (.docx).\n"
                                    f"• Adjust the tone (*'more confident'*, *'concise'*), expand specific paragraphs, or highlight key projects in this copilot chat."
                                ),
                            }
                        ]

                        st.rerun()

                    except Exception as exc:
                        err_str = str(exc)
                        if "429" in err_str or "quota" in err_str.lower():
                            st.warning(
                                "⏳ **Google Gemini API Rate Limit (429):** "
                                "Request limit temporarily reached on the free tier. "
                                "Please wait approximately **30–40 seconds** and try again."
                            )
                        else:
                            st.error(f"⚠️ Application package generation failed: {exc}")

        # ── Optimize CV Result & Interactive Refiner ─────────────────────────────
        if optimize_clicked:
            if not os.getenv("GEMINI_API_KEY"):
                st.error("❌ GEMINI_API_KEY not configured. Please check your .env file.")
            else:
                with st.spinner("🧠 Gemini is tailoring CV bullet points… (~3–5s)"):
                    try:
                        from src.match_analyzer import analyze_match
                        from src.ai_assistant import (
                            optimize_cv_for_job,
                            build_tailored_cv_data,
                        )

                        opt = optimize_cv_for_job(
                            job_title=selected_job.get("title", ""),
                            job_company=selected_job.get("company", ""),
                            job_description=selected_job.get("description", ""),
                            found_skills=result.found_skills,
                            missing_skills=result.missing_skills,
                            cv=cv,
                            current_score=result.score,
                        )

                        job_id_key = str(selected_job.get("id"))
                        tailored_cv = build_tailored_cv_data(opt, cv, company=selected_job.get("company", ""))
                        st.session_state["tailored_cv_working"] = tailored_cv
                        st.session_state["tailored_cv_job_id"] = job_id_key
                        st.session_state[f"tailored_cv_{job_id_key}"] = tailored_cv

                        tailored_match = analyze_match(
                            job_title=selected_job.get("title", ""),
                            job_description=selected_job.get("description", ""),
                            cv=tailored_cv,
                        )
                        raw_est = opt.get("estimated_new_score", result.score)
                        final_new_score = max(result.score, tailored_match.score, raw_est)
                        if result.score >= 100:
                            final_new_score = 100
                        else:
                            final_new_score = min(100, max(result.score, final_new_score))

                        opt_meta = {
                            "original_score": result.score,
                            "estimated_new_score": final_new_score,
                            "optimization_notes": opt.get("optimization_notes", ""),
                            "added_technologies": opt.get("added_technologies", []),
                            "key_changes": opt.get("key_changes", []),
                        }
                        st.session_state["cv_opt_meta"] = opt_meta
                        st.session_state[f"cv_opt_meta_{job_id_key}"] = opt_meta

                        if result.score >= 100:
                            score_msg = (
                                f"Your current CV was already at a **{result.score}% (Flawless Match)** level for this role! "
                                f"Bullet points and achievement metrics were tailored specifically to this opening while preserving 100% ATS alignment ✨\n\n"
                            )
                        elif final_new_score > result.score:
                            score_msg = (
                                f"Estimated ATS match score boosted from **{result.score}% → {final_new_score}%** 🚀\n\n"
                            )
                        else:
                            score_msg = (
                                f"CV optimized with role-specific keywords and impact metrics (ATS Score: **{final_new_score}%**) ✨\n\n"
                            )

                        feedback_details = []
                        if opt.get("added_technologies"):
                            techs_str = ", ".join(f"`{t}`" for t in opt.get("added_technologies", []))
                            feedback_details.append(f"🎯 **Added / Highlighted Technologies:** {techs_str}")
                        if opt.get("key_changes"):
                            changes_str = "\n".join(f"  • {c}" for c in opt.get("key_changes", []))
                            feedback_details.append(f"💡 **Key Improvements Made:**\n{changes_str}")
                        elif opt.get("optimization_notes"):
                            feedback_details.append(f"💡 **Optimization Summary:** {opt.get('optimization_notes')}")

                        feedback_copilot_txt = ("\n\n" + "\n\n".join(feedback_details)) if feedback_details else ""

                        st.session_state[f"cv_copilot_messages_{job_id_key}"] = [
                            {
                                "role": "assistant",
                                "content": (
                                    f"🎯 Successfully tailored your CV for **{selected_job.get('company', '')}** ({selected_job.get('title', '')})!\n\n"
                                    f"{score_msg}"
                                    f"{feedback_copilot_txt}\n\n"
                                    f"• You can edit bullet points directly in the left panels or give direct refinement instructions in this chat."
                                ),
                            }
                        ]
                        st.rerun()

                    except json.JSONDecodeError as exc:
                        st.error(f"⚠️ Gemini returned an unexpected format: {exc}. Please try again.")
                    except Exception as exc:
                        err_str = str(exc)
                        if "429" in err_str or "quota" in err_str.lower():
                            st.warning(
                                "⏳ **Google Gemini API Rate Limit (429):** "
                                "Request limit temporarily reached on the free tier. "
                                "Please wait approximately **30–40 seconds** and try again."
                            )
                        else:
                            st.error(f"⚠️ Optimization failed: {exc}")

        # ── Cover Letter Generation ───────────────────────────────────────────────
        if cover_clicked:
            if not os.getenv("GEMINI_API_KEY"):
                st.error("❌ GEMINI_API_KEY not configured. Please check your .env file.")
            else:
                with st.spinner("✍️ Gemini is crafting your tailored cover letter… (~10–15s)"):
                    try:
                        from src.models import Job as JobModel
                        from src.ai_assistant import generate_cover_letter

                        job_obj = JobModel(
                            job_id=str(selected_job.get("id", "dash")),
                            source=selected_job.get("source", "dashboard"),
                            title=selected_job.get("title", ""),
                            company=selected_job.get("company", ""),
                            location=selected_job.get("location", ""),
                            url=selected_job.get("url", ""),
                            description=selected_job.get("description", ""),
                        )

                        job_id_key = str(selected_job.get("id"))
                        cover_letter = generate_cover_letter(job_obj)
                        st.session_state[f"cover_letter_{job_id_key}"] = cover_letter
                        st.session_state[f"cl_copilot_messages_{job_id_key}"] = [
                            {
                                "role": "assistant",
                                "content": (
                                    f"✍️ Generated a tailored Cover Letter for **{selected_job.get('company', '')}** ({selected_job.get('title', '')})!\n\n"
                                    f"• Read your letter in the live preview panel on the left, or download as PDF / Word.\n"
                                    f"• Brainstorm tone and content adjustments with me, or request instant paragraph revisions."
                                ),
                            }
                        ]
                        st.rerun()

                    except Exception as exc:
                        err_str = str(exc)
                        if "429" in err_str or "quota" in err_str.lower():
                            st.warning(
                                "⏳ **Google Gemini API Rate Limit (429):** "
                                "Request limit temporarily reached on the free tier. "
                                "Please wait approximately **30–40 seconds** and try again."
                            )
                        else:
                            st.error(f"⚠️ Cover letter generation failed: {exc}")

    # ── Dual Split-Screen Workspace (CV Copilot & Cover Letter Copilot) ───────
    cur_jid = str(selected_job.get("id"))
    has_cv_state = bool(st.session_state.get(f"tailored_cv_{cur_jid}") or (st.session_state.get("tailored_cv_working") and st.session_state.get("tailored_cv_job_id") == cur_jid))
    has_cl_state = bool(st.session_state.get(f"cover_letter_{cur_jid}"))

    if has_cv_state or has_cl_state:
        st.markdown("---")
        st.markdown("### 💼 Role-Specific Application Workspace (Split-Screen Copilot)")
        tab_ats_cv, tab_cover_letter = st.tabs([
            "📄 1. ATS CV & CV Copilot",
            "✍️ 2. Cover Letter & Copilot",
        ])

        # ─────────────────────────────────────────────────────────────────────
        # TAB 1: ATS CV & CV COPILOT (SPLIT-SCREEN)
        # ─────────────────────────────────────────────────────────────────────
        with tab_ats_cv:
            if not has_cv_state:
                st.info(f"ℹ️ No tailored CV generated yet for **{selected_job.get('company')}**. Click **'⚡ Full Application Package'** or **'🚀 Tailor CV Only'** above to generate one in seconds.")
            else:
                tailored_cv = st.session_state.get(f"tailored_cv_{cur_jid}")
                if not tailored_cv and st.session_state.get("tailored_cv_job_id") == cur_jid:
                    tailored_cv = st.session_state.get("tailored_cv_working")

                opt_meta = st.session_state.get(f"cv_opt_meta_{cur_jid}")
                if not opt_meta and st.session_state.get("tailored_cv_job_id") == cur_jid:
                    opt_meta = st.session_state.get("cv_opt_meta", {})
                if not opt_meta:
                    opt_meta = {}

                if not tailored_cv:
                    st.info(f"ℹ️ No tailored CV found for **{selected_job.get('company')}**.")
                    st.stop()

                orig_score = opt_meta.get("original_score", result.score)
                new_score = opt_meta.get("estimated_new_score", result.score)
                delta = new_score - orig_score

                from src.ai_assistant import generate_cv_pdf, generate_cv_docx
                pdf_bytes = get_cached_cv_pdf(tailored_cv)
                docx_bytes = generate_cv_docx(tailored_cv)

                candidate_name = tailored_cv.get("personal", {}).get("name", "Candidate")
                safe_candidate = "".join(c for c in candidate_name if c.isalnum() or c in " _-").strip().replace(" ", "_") or "Candidate"
                raw_co = selected_job.get("company", "job")
                safe_co = "".join(c for c in raw_co if c.isalnum() or c in " _-").strip().replace(" ", "_") or "job"

                col_cv_doc, col_cv_copilot = st.columns([1.1, 1.0])

                # LEFT: Live Document Preview & Section Editors
                with col_cv_doc:
                    st.markdown("#### 📄 Live CV Preview & Section Editor")
                    
                    # Metrics Row
                    col_m1, col_m2, col_m3 = st.columns([1, 1, 1.5])
                    with col_m1:
                        st.metric("Original Score", f"{orig_score}%")
                    with col_m2:
                        if delta > 0:
                            st.metric("Optimized Score", f"{new_score}%", delta=f"+{delta}%")
                        elif orig_score >= 100:
                            st.metric("Optimized Score", f"{new_score}%", delta="Flawless 🎯")
                        else:
                            st.metric("Optimized Score", f"{new_score}%", delta="Retained ✨")
                    with col_m3:
                        st.write("")
                        st.download_button(
                            label="📥 Download CV (.pdf)",
                            data=pdf_bytes,
                            file_name=f"{safe_candidate}_CV_{safe_co}.pdf",
                            mime="application/pdf",
                            type="primary",
                            key=f"btn_dl_cv_pdf_tab_{cur_jid}",
                            use_container_width=True,
                        )

                    # Highlighted Technologies Badge
                    added_techs = opt_meta.get("added_technologies", [])
                    if added_techs:
                        badges_html = " ".join([
                            f'<span style="background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.35); padding: 2px 8px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; display: inline-block; margin: 2px;">+ {html.escape(str(t))}</span>'
                            for t in added_techs
                        ])
                        st.markdown(f"<div style='margin-bottom:8px;'><b>🎯 Highlighted / Strengthened Technologies:</b><br>{badges_html}</div>", unsafe_allow_html=True)

                    # Editable summary
                    with st.expander("📝 Professional Summary", expanded=False):
                        current_summary = tailored_cv.get("summary", "")
                        edited_summary = st.text_area(
                            "Summary Text:",
                            value=current_summary,
                            height=85,
                            key=f"tab_working_summary_{cur_jid}",
                        )
                        if edited_summary != current_summary:
                            tailored_cv["summary"] = edited_summary
                            st.session_state[f"tailored_cv_{cur_jid}"] = tailored_cv

                    # Technical Skills
                    if tailored_cv.get("skills"):
                        with st.expander("🛠️ Technical Skills", expanded=False):
                            cat_labels = {
                                "programming_languages": "Languages & Frameworks",
                                "generative_ai_and_llms": "AI, LLMs & Agents",
                                "backend_and_systems": "Backend & Systems",
                                "core_competencies": "Core Competencies",
                                "tools": "Tools & Cloud Platforms",
                            }
                            skills_dict = tailored_cv.get("skills", {})
                            for cat_key, items in list(skills_dict.items()):
                                if not isinstance(items, list):
                                    continue
                                label = cat_labels.get(cat_key, cat_key.replace("_", " ").title())
                                current_str = ", ".join(items)
                                edited_str = st.text_input(
                                    f"{label}:",
                                    value=current_str,
                                    key=f"tab_skill_in_{cur_jid}_{cat_key}",
                                )
                                if edited_str != current_str:
                                    tailored_cv["skills"][cat_key] = [s.strip() for s in edited_str.split(",") if s.strip()]
                                    st.session_state[f"tailored_cv_{cur_jid}"] = tailored_cv

                    # Experience
                    if tailored_cv.get("experience"):
                        with st.expander("💼 Experience Bullet Points", expanded=False):
                            job_ctx = f"Job: {selected_job.get('title')} at {selected_job.get('company')}."
                            for exp_idx, exp in enumerate(tailored_cv.get("experience", [])):
                                st.markdown(f"**💼 {exp.get('role', '')} — {exp.get('company', '')}**")
                                new_bullets = list(exp.get("bullets", []))
                                for b_idx, bullet in enumerate(new_bullets):
                                    edited_bullet = st.text_area(
                                        f"Exp {exp_idx}_{b_idx}",
                                        value=bullet,
                                        height=65,
                                        key=f"tab_exp_in_{cur_jid}_{exp_idx}_{b_idx}",
                                        label_visibility="collapsed",
                                    )
                                    if edited_bullet != bullet:
                                        new_bullets[b_idx] = edited_bullet
                                        tailored_cv["experience"][exp_idx]["bullets"] = new_bullets
                                        st.session_state[f"tailored_cv_{cur_jid}"] = tailored_cv

                    # Projects
                    if tailored_cv.get("projects"):
                        with st.expander("🔬 Academic & Personal Projects", expanded=False):
                            for p_idx, proj in enumerate(tailored_cv.get("projects", [])):
                                st.markdown(f"**🔬 {proj.get('name', '')}**")
                                new_p_bullets = list(proj.get("bullets", []))
                                for b_idx, bullet in enumerate(new_p_bullets):
                                    edited_bullet = st.text_area(
                                        f"Proj {p_idx}_{b_idx}",
                                        value=bullet,
                                        height=65,
                                        key=f"tab_proj_in_{cur_jid}_{p_idx}_{b_idx}",
                                        label_visibility="collapsed",
                                    )
                                    if edited_bullet != bullet:
                                        new_p_bullets[b_idx] = edited_bullet
                                        tailored_cv["projects"][p_idx]["bullets"] = new_p_bullets
                                        st.session_state[f"tailored_cv_{cur_jid}"] = tailored_cv

                # RIGHT: Dedicated CV Copilot (Brainstorming & Live Chat)
                with col_cv_copilot:
                    cv_chat_key = f"cv_copilot_messages_{cur_jid}"
                    cv_chat_history = st.session_state.get(cv_chat_key, [])

                    col_cv_hdr, col_cv_btn = st.columns([3, 1.2])
                    with col_cv_hdr:
                        st.markdown("#### 💬 CV Copilot — Interactive Assistant")
                    with col_cv_btn:
                        if st.button("🧹 Reset", key=f"btn_reset_cv_chat_{cur_jid}", help="Clear Copilot chat history for this job"):
                            st.session_state[cv_chat_key] = []
                            st.toast("🧹 CV Copilot chat history reset!")
                            st.rerun()
                    st.caption(f"Tailored CV assistant for **{selected_job.get('company')}**. Ask questions, consult on strategy, or request revisions directly.")

                    # Quick Suggestion Chips
                    cq1, cq2, cq3 = st.columns(3)
                    with cq1:
                        if st.button("🎯 Highlight Core Skills", key=f"btn_chip_cv1_{cur_jid}", use_container_width=True, help="Emphasize critical technologies requested in the listing"):
                            cv_chat_history.append({"role": "user", "content": "Emphasize the most critical technologies requested by this job listing across my CV bullet points."})
                            with st.spinner("🤖 Copilot is optimizing CV skills..."):
                                from src.ai_assistant import chat_refine_cv
                                updated_cv, explanation = chat_refine_cv(
                                    current_cv=tailored_cv,
                                    user_prompt="Emphasize the most critical technologies requested by this job listing across my CV bullet points.",
                                    chat_history=cv_chat_history[:-1],
                                    job_title=selected_job.get("title", ""),
                                    company=selected_job.get("company", ""),
                                    description=selected_job.get("description", ""),
                                )
                                st.session_state[f"tailored_cv_{cur_jid}"] = updated_cv
                                cv_chat_history.append({"role": "assistant", "content": explanation})
                                st.session_state[cv_chat_key] = cv_chat_history
                                st.rerun()
                    with cq2:
                        if st.button("💼 Polish Experience Metrics", key=f"btn_chip_cv2_{cur_jid}", use_container_width=True, help="Add measurable impact metrics to experience bullet points"):
                            cv_chat_history.append({"role": "user", "content": "Make my internship bullet points more measurable, technically detailed, and impact-oriented."})
                            with st.spinner("🤖 Copilot is strengthening experience bullets..."):
                                from src.ai_assistant import chat_refine_cv
                                updated_cv, explanation = chat_refine_cv(
                                    current_cv=tailored_cv,
                                    user_prompt="Make my internship bullet points more measurable, technically detailed, and impact-oriented.",
                                    chat_history=cv_chat_history[:-1],
                                    job_title=selected_job.get("title", ""),
                                    company=selected_job.get("company", ""),
                                    description=selected_job.get("description", ""),
                                )
                                st.session_state[f"tailored_cv_{cur_jid}"] = updated_cv
                                cv_chat_history.append({"role": "assistant", "content": explanation})
                                st.session_state[cv_chat_key] = cv_chat_history
                                st.rerun()
                    with cq3:
                        if st.button("🚀 Align Projects with Role", key=f"btn_chip_cv3_{cur_jid}", use_container_width=True, help="Re-align projects and spotlight the most relevant work for this role"):
                            cv_chat_history.append({"role": "user", "content": "Reframe my projects to match this job's core technical requirements and spotlight the most relevant project."})
                            with st.spinner("🤖 Copilot is aligning projects with the role..."):
                                from src.ai_assistant import chat_refine_cv
                                updated_cv, explanation = chat_refine_cv(
                                    current_cv=tailored_cv,
                                    user_prompt="Reframe my projects to match this job's core technical requirements and spotlight the most relevant project.",
                                    chat_history=cv_chat_history[:-1],
                                    job_title=selected_job.get("title", ""),
                                    company=selected_job.get("company", ""),
                                    description=selected_job.get("description", ""),
                                )
                                st.session_state[f"tailored_cv_{cur_jid}"] = updated_cv
                                cv_chat_history.append({"role": "assistant", "content": explanation})
                                st.session_state[cv_chat_key] = cv_chat_history
                                st.rerun()

                    # Scrollable Chat Container (isolated per job)
                    with st.container(height=420):
                        if not cv_chat_history:
                            st.info("💡 **CV Copilot ready!** Ask questions (*'Did you include Go?', 'Which tools are critical?'*), brainstorm strategy, or request direct edits (*'Emphasize Docker experience'*).")
                        for msg in cv_chat_history:
                            with st.chat_message(msg["role"]):
                                st.markdown(msg["content"])

                    if copilot_prompt_cv := st.chat_input("Ask about your CV or request revisions...", key=f"chat_in_cv_{cur_jid}"):
                        cv_chat_history.append({"role": "user", "content": copilot_prompt_cv})
                        st.session_state[cv_chat_key] = cv_chat_history

                        with st.spinner("🤖 Copilot is responding / updating your CV…"):
                            try:
                                from src.ai_assistant import chat_refine_cv
                                updated_cv, explanation = chat_refine_cv(
                                    current_cv=tailored_cv,
                                    user_prompt=copilot_prompt_cv,
                                    chat_history=cv_chat_history[:-1],
                                    job_title=selected_job.get("title", ""),
                                    company=selected_job.get("company", ""),
                                    description=selected_job.get("description", ""),
                                )
                                st.session_state[f"tailored_cv_{cur_jid}"] = updated_cv
                                cv_chat_history.append({"role": "assistant", "content": explanation})
                                st.session_state[cv_chat_key] = cv_chat_history
                                st.rerun()
                            except Exception as chat_err:
                                st.error(f"⚠️ Copilot error: {chat_err}")

        # ─────────────────────────────────────────────────────────────────────
        # TAB 2: COVER LETTER & COPILOT (SPLIT-SCREEN)
        # ─────────────────────────────────────────────────────────────────────
        with tab_cover_letter:
            current_cl = st.session_state.get(f"cover_letter_{cur_jid}")
            if not current_cl:
                st.info(f"ℹ️ No cover letter generated yet for **{selected_job.get('company')}**.")
                if st.button("✍️ Generate Tailored Cover Letter for This Job", type="primary", key=f"btn_create_cl_inline_{cur_jid}"):
                    with st.spinner("✍️ Gemini is crafting your tailored cover letter…"):
                        try:
                            from src.models import Job as JobModel
                            from src.ai_assistant import generate_cover_letter
                            job_obj = JobModel(
                                job_id=str(selected_job.get("id", "dash")),
                                source=selected_job.get("source", "dashboard"),
                                title=selected_job.get("title", ""),
                                company=selected_job.get("company", ""),
                                location=selected_job.get("location", ""),
                                url=selected_job.get("url", ""),
                                description=selected_job.get("description", ""),
                            )
                            cl_text = generate_cover_letter(job_obj)
                            st.session_state[f"cover_letter_{cur_jid}"] = cl_text
                            st.session_state[f"cl_copilot_messages_{cur_jid}"] = [
                                {
                                    "role": "assistant",
                                    "content": (
                                        f"✍️ Generated a tailored Cover Letter for **{selected_job.get('company', '')}** ({selected_job.get('title', '')})!\n\n"
                                        f"• Review your letter in the live preview card on the left, or export as PDF / Word.\n"
                                        f"• Brainstorm tone and content adjustments, or request instant revisions in this copilot chat."
                                    ),
                                }
                            ]
                            st.rerun()
                        except Exception as cl_err:
                            st.error(f"Cover letter generation failed: {cl_err}")
            else:
                from src.ai_assistant import (
                    generate_cover_letter_pdf,
                    generate_cover_letter_docx,
                    chat_refine_cover_letter,
                )

                raw_co = selected_job.get("company", "job")
                safe_co = "".join(c for c in raw_co if c.isalnum() or c in " _-").strip().replace(" ", "_") or "job"
                job_title_str = selected_job.get("title", "")

                cl_pdf_bytes = generate_cover_letter_pdf(
                    text=current_cl,
                    job_title=job_title_str,
                    company=raw_co,
                    cv=cv,
                )
                cl_docx_bytes = generate_cover_letter_docx(
                    text=current_cl,
                    job_title=job_title_str,
                    company=raw_co,
                    cv=cv,
                )

                col_cl_doc, col_cl_copilot = st.columns([1.1, 1.0])

                # LEFT: Live Document Preview Card & Export Buttons
                with col_cl_doc:
                    st.markdown("#### 📄 Live Cover Letter Preview")

                    # Export buttons row
                    cdl1, cdl2, cdl3 = st.columns([1.5, 1.2, 1.1])
                    with cdl1:
                        st.download_button(
                            label="📥 Download PDF (.pdf)",
                            data=cl_pdf_bytes,
                            file_name=f"CoverLetter_{safe_co}.pdf",
                            mime="application/pdf",
                            type="primary",
                            key=f"btn_dl_cl_pdf_tab_{cur_jid}",
                            use_container_width=True,
                        )
                    with cdl2:
                        st.download_button(
                            label="📄 Download Word (.docx)",
                            data=cl_docx_bytes,
                            file_name=f"CoverLetter_{safe_co}.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"btn_dl_cl_docx_tab_{cur_jid}",
                            use_container_width=True,
                        )
                    with cdl3:
                        st.download_button(
                            label="📝 Download Text (.txt)",
                            data=current_cl.encode("utf-8"),
                            file_name=f"CoverLetter_{safe_co}.txt",
                            mime="text/plain",
                            key=f"btn_dl_cl_txt_tab_{cur_jid}",
                            use_container_width=True,
                        )

                    # Styled Live Document Preview Card
                    st.markdown(
                        f"""
                        <div style="background:#ffffff; border:1px solid #cbd5e1; border-radius:10px; padding:22px 26px; box-shadow:0 2px 6px rgba(0,0,0,0.04); font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif; color:#1e293b; line-height:1.65; max-height:480px; overflow-y:auto; margin-bottom:12px;">
                            <div style="border-bottom:1px solid #e2e8f0; padding-bottom:10px; margin-bottom:14px;">
                                <div style="font-size:1.1rem; font-weight:700; color:#0f172a;">🏢 {html.escape(selected_job.get('company', ''))}</div>
                                <div style="font-size:0.88rem; color:#64748b; font-weight:500;">📌 {html.escape(selected_job.get('title', ''))}</div>
                            </div>
                            <div style="white-space:pre-wrap; font-size:0.92rem; color:#334155;">{html.escape(current_cl)}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    # Manual inline editor expander
                    with st.expander("✏️ Direct Text Editor (Manual Mode)", expanded=False):
                        edited_cl = st.text_area(
                            "Cover Letter Text:",
                            value=current_cl,
                            height=280,
                            key=f"tab_cl_text_area_{cur_jid}",
                            label_visibility="collapsed",
                        )
                        if edited_cl != current_cl:
                            st.session_state[f"cover_letter_{cur_jid}"] = edited_cl
                            st.rerun()

                # RIGHT: Dedicated Cover Letter Copilot (Brainstorming & Live Chat)
                with col_cl_copilot:
                    cl_chat_key = f"cl_copilot_messages_{cur_jid}"
                    cl_chat_history = st.session_state.get(cl_chat_key, [])

                    col_cl_hdr, col_cl_btn = st.columns([3, 1.2])
                    with col_cl_hdr:
                        st.markdown("#### 💬 Cover Letter Copilot")
                    with col_cl_btn:
                        if st.button("🧹 Reset", key=f"btn_reset_cl_chat_{cur_jid}", help="Clear cover letter chat history for this job"):
                            st.session_state[cl_chat_key] = []
                            st.toast("🧹 Cover Letter Copilot chat history reset!")
                            st.rerun()
                    st.caption(f"Adjust tone, expand specific paragraphs, or consult strategy for {selected_job.get('company')}.")

                    # Quick Suggestion Chips
                    cq_cl1, cq_cl2, cq_cl3 = st.columns(3)
                    with cq_cl1:
                        if st.button("🎯 Emphasize Job Requirements", key=f"btn_chip_cl1_{cur_jid}", use_container_width=True, help="Emphasize specific tools and responsibilities requested by the company"):
                            cl_chat_history.append({"role": "user", "content": "Emphasize the company's core technical requirements and key responsibilities more prominently in paragraph 2."})
                            with st.spinner("🤖 Copilot is refining the letter..."):
                                up_cl, exp_cl = chat_refine_cover_letter(
                                    current_cover_letter=current_cl,
                                    user_prompt="Emphasize the company's core technical requirements and key responsibilities more prominently in paragraph 2.",
                                    chat_history=cl_chat_history[:-1],
                                    job_title=selected_job.get("title", ""),
                                    company=selected_job.get("company", ""),
                                    description=selected_job.get("description", ""),
                                    cv=cv,
                                )
                                st.session_state[f"cover_letter_{cur_jid}"] = up_cl
                                cl_chat_history.append({"role": "assistant", "content": exp_cl})
                                st.session_state[cl_chat_key] = cl_chat_history
                                st.rerun()
                    with cq_cl2:
                        if st.button("🌟 Confident & Dynamic Tone", key=f"btn_chip_cl2_{cur_jid}", use_container_width=True, help="Make the tone more confident, dynamic, and compelling"):
                            cl_chat_history.append({"role": "user", "content": "Adapt the cover letter's tone to be more confident, proactive, and professionally compelling."})
                            with st.spinner("🤖 Copilot is polishing tone..."):
                                up_cl, exp_cl = chat_refine_cover_letter(
                                    current_cover_letter=current_cl,
                                    user_prompt="Adapt the cover letter's tone to be more confident, proactive, and professionally compelling.",
                                    chat_history=cl_chat_history[:-1],
                                    job_title=selected_job.get("title", ""),
                                    company=selected_job.get("company", ""),
                                    description=selected_job.get("description", ""),
                                    cv=cv,
                                )
                                st.session_state[f"cover_letter_{cur_jid}"] = up_cl
                                cl_chat_history.append({"role": "assistant", "content": exp_cl})
                                st.session_state[cl_chat_key] = cl_chat_history
                                st.rerun()
                    with cq_cl3:
                        if st.button("🔬 Connect Hands-on Projects", key=f"btn_chip_cl3_{cur_jid}", use_container_width=True, help="Build concrete connections with internship experience and technical projects"):
                            cl_chat_history.append({"role": "user", "content": "Draw concrete connections between my software internship and technical projects and the position's core responsibilities."})
                            with st.spinner("🤖 Copilot is linking projects with the role..."):
                                up_cl, exp_cl = chat_refine_cover_letter(
                                    current_cover_letter=current_cl,
                                    user_prompt="Draw concrete connections between my software internship and technical projects and the position's core responsibilities.",
                                    chat_history=cl_chat_history[:-1],
                                    job_title=selected_job.get("title", ""),
                                    company=selected_job.get("company", ""),
                                    description=selected_job.get("description", ""),
                                    cv=cv,
                                )
                                st.session_state[f"cover_letter_{cur_jid}"] = up_cl
                                cl_chat_history.append({"role": "assistant", "content": exp_cl})
                                st.session_state[cl_chat_key] = cl_chat_history
                                st.rerun()

                    # Scrollable Chat Container (isolated per job)
                    with st.container(height=420):
                        if not cl_chat_history:
                            st.info(f"💡 **Cover Letter Copilot ready!** Adjust tone, expand paragraphs, or brainstorm tailored strategy for {selected_job.get('company')}.")
                        for msg in cl_chat_history:
                            with st.chat_message(msg["role"]):
                                st.markdown(msg["content"])

                    if copilot_prompt_cl := st.chat_input("Ask about your cover letter or request revisions...", key=f"chat_in_cl_{cur_jid}"):
                        cl_chat_history.append({"role": "user", "content": copilot_prompt_cl})
                        st.session_state[cl_chat_key] = cl_chat_history

                        with st.spinner("🤖 Copilot is responding / updating your cover letter…"):
                            try:
                                up_cl, exp_cl = chat_refine_cover_letter(
                                    current_cover_letter=current_cl,
                                    user_prompt=copilot_prompt_cl,
                                    chat_history=cl_chat_history[:-1],
                                    job_title=selected_job.get("title", ""),
                                    company=selected_job.get("company", ""),
                                    description=selected_job.get("description", ""),
                                    cv=cv,
                                )
                                st.session_state[f"cover_letter_{cur_jid}"] = up_cl
                                cl_chat_history.append({"role": "assistant", "content": exp_cl})
                                st.session_state[cl_chat_key] = cl_chat_history
                                st.rerun()
                            except Exception as chat_err:
                                st.error(f"⚠️ Copilot error: {chat_err}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — CAREER ROADMAP & BENCHMARKS
# ══════════════════════════════════════════════════════════════════════════════
elif active_tab == "🧭 Career Roadmap & Strategy":
    st.markdown('<div class="section-header">🧭 Berlin & Germany Working Student Career Roadmap & Benchmarks</div>', unsafe_allow_html=True)
    st.caption("Strategic career roadmaps, technical screening criteria, and interview benchmarks based on active Werkstudent and internship openings across Germany's tech ecosystem.")

    st.info(
        "💡 **Industry Reality & Strategy:** English-speaking tech companies in Germany (especially Berlin startups and scale-ups) "
        "value **production-ready practical tooling and problem-solving velocity** far more than theoretical coursework for Working Student roles. "
        "Follow the tracks below to master core benchmarks, stand-out skills, and interview-winning portfolio blueprints."
    )

    tab_data, tab_ai, tab_tips = st.tabs([
        "📊 1. Data Analytics & BI Track",
        "🤖 2. AI & LLM / ML Engineering Track",
        "🇩🇪 3. German Hiring & Interview Tactics",
    ])

    # ──────────────────────────────────────────────────────────────────────────
    # SUB-TAB 1: Data Analytics & BI Track
    # ──────────────────────────────────────────────────────────────────────────
    with tab_data:
        st.subheader("📊 Data Analytics & Business Intelligence Career Standards")
        
        d_c1, d_c2, d_c3, d_c4 = st.columns(4)
        d_c1.metric("🎯 Target Roles", "Data / BI Working Student")
        d_c2.metric("💰 Hourly Wage Range", "€14 – €18 / hr")
        d_c3.metric("⏳ Weekly Hours", "16 – 20 Hours (Semester)")
        d_c4.metric("🏢 Work Model", "Hybrid (Berlin) / Remote")

        st.markdown("---")
        st.markdown("### 🎯 1. Non-Negotiable Core Benchmarks (Must-Haves)")
        st.caption("These 4 core competencies are strictly required to pass technical screening in the Berlin market:")

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.markdown(
                """
                <div style="background-color: #f8fafc; border-left: 4px solid #3b82f6; padding: 14px; border-radius: 8px; margin-bottom: 12px;">
                    <strong style="color: #1e3a8a; font-size: 15px;">1. Advanced SQL (Live Coding Test Standard)</strong>
                    <ul style="margin-top: 6px; font-size: 13.5px; color: #334155;">
                        <li><strong>Window Functions:</strong> <code>ROW_NUMBER()</code>, <code>RANK()</code>, <code>DENSE_RANK()</code>, <code>LEAD()</code>, <code>LAG()</code></li>
                        <li><strong>Query Architecture:</strong> CTEs (<code>WITH</code> clauses), Subqueries, Complex Joins (Self-Join, Anti-Join)</li>
                        <li><strong>Data Aggregation:</strong> Conditional aggregation (<code>CASE WHEN</code>), Grouping Sets, Rollup</li>
                        <li><em>Interview Expectation:</em> Write LeetCode Medium level SQL queries in 20 minutes during live technical rounds.</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                """
                <div style="background-color: #f8fafc; border-left: 4px solid #10b981; padding: 14px; border-radius: 8px; margin-bottom: 12px;">
                    <strong style="color: #065f46; font-size: 15px;">2. Python Data Manipulation & Data Cleaning</strong>
                    <ul style="margin-top: 6px; font-size: 13.5px; color: #334155;">
                        <li><strong>Pandas Mastery:</strong> <code>merge()</code>, <code>groupby()</code>, <code>pivot_table()</code>, <code>melt()</code></li>
                        <li><strong>Data Hygiene:</strong> Handling missing values (<code>dropna</code>, <code>fillna</code>), type casting, regex text sanitization</li>
                        <li><strong>Time Series:</strong> Datetime parsing, resampling, rolling window metrics</li>
                        <li><em>Interview Expectation:</em> Clean a messy CSV/JSON dataset and produce summary KPI metrics in 15 minutes.</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_m2:
            st.markdown(
                """
                <div style="background-color: #f8fafc; border-left: 4px solid #f59e0b; padding: 14px; border-radius: 8px; margin-bottom: 12px;">
                    <strong style="color: #92400e; font-size: 15px;">3. BI Modeling & Dashboarding (Power BI / Tableau)</strong>
                    <ul style="margin-top: 6px; font-size: 13.5px; color: #334155;">
                        <li><strong>Data Modeling:</strong> Star Schema (Fact and Dimension tables), 1-to-Many relationship design</li>
                        <li><strong>Calculation Logic:</strong> DAX in Power BI (<code>CALCULATE</code>, <code>FILTER</code>, <code>ALL</code>) or Tableau LOD expressions</li>
                        <li><strong>UX & Visualization:</strong> User-friendly interactive slicers, drill-through pages, clear visual hierarchy</li>
                        <li><em>Interview Expectation:</em> Design a clean executive dashboard for C-level or Product managers.</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                """
                <div style="background-color: #f8fafc; border-left: 4px solid #8b5cf6; padding: 14px; border-radius: 8px; margin-bottom: 12px;">
                    <strong style="color: #5b21b6; font-size: 15px;">4. Business Acumen & Metric Literacy</strong>
                    <ul style="margin-top: 6px; font-size: 13.5px; color: #334155;">
                        <li><strong>SaaS & E-Commerce Metrics:</strong> Churn Rate, Retention Cohorts, LTV, CAC, MRR/ARR</li>
                        <li><strong>Funnel Analysis:</strong> Conversion drop-offs, user journey optimization</li>
                        <li><strong>A/B Testing Basics:</strong> Hypothesis framing, p-value interpretation, statistical significance</li>
                        <li><em>Interview Expectation:</em> Explain 'why customer retention dropped' using structured, data-driven breakdowns.</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("### 🚀 2. Differentiating 'Game-Changer' Skills")
        st.caption("85% of applicants cover the basics; these modern tools set you apart in candidate ranking:")
        
        g_c1, g_c2, g_c3 = st.columns(3)
        with g_c1:
            st.markdown("**🛠️ Modern Data Stack (MDS)**")
            st.write("• **dbt (data build tool):** Modular, version-controlled, testable SQL transformations.")
            st.write("• **Snowflake / BigQuery:** Cloud warehouse querying cost efficiency and partitioning awareness.")
        with g_c2:
            st.markdown("**🔄 Automation & Ingestion**")
            st.write("• **API Integrations:** Ingesting REST APIs using Python requests / httpx.")
            st.write("• **Scheduled Pipelines:** Automated daily data refreshes via GitHub Actions or Cron.")
        with g_c3:
            st.markdown("**📈 Advanced Experimentation**")
            st.write("• **A/B Test Design:** Sample size calculations and Type I/II error management.")
            st.write("• **Cohort Heatmaps:** Period-based heatmaps measuring long-term user retention.")

        st.markdown("---")
        st.markdown("### 🏆 3. Interview-Winning Portfolio Project Blueprint")
        st.caption("End-to-end architecture that gets hiring managers to schedule an interview immediately:")

        with st.expander("📌 Project Blueprint: 'E-Commerce Customer Lifecycle & Cohort Retention Engine'", expanded=True):
            st.markdown("""
```
[ Kaggle / Open Dataset ] ──> [ Python Script (Cleaning & Feature Engineering) ]
                                            │
                                            ▼
                               [ SQLite / PostgreSQL Database ]
                                            │
                       ┌────────────────────┴───────────────────┐
                       ▼                                        ▼
             [ dbt / SQL Models ]                     [ Power BI / Streamlit App ]
        (RFM Scoring, Cohort Matrix)               (Executive Dashboard & Live Report)
```
            """)
            st.markdown("""
**Core Deliverables to Include:**
1. **Dataset:** 100,000+ transaction rows of realistic e-commerce / SaaS event data.
2. **SQL Models:** 
   - RFM (Recency, Frequency, Monetary) segmentation classifying customers into *Champions*, *At Risk*, and *Lost*.
   - Monthly cohort analysis calculating retention curves by acquisition month.
3. **Interactive Visual Dashboard:** Power BI (.pbix file + PDF screenshots) or a live Streamlit web application.
4. **GitHub README:** Beyond code: include an *"Executive Summary: 3 Key Business Insights & Marketing Actions"* section.
            """)

        st.markdown("### 📅 4. 4-Week Rapid Action Roadmap")
        w1, w2, w3, w4 = st.columns(4)
        with w1:
            st.info("**Week 1: Live SQL Coding**\n\n• LeetCode 50 SQL Study Plan\n• Window Functions & CTE drills\n• StrataScratch medium challenges")
        with w2:
            st.info("**Week 2: Python Data Hygiene**\n\n• Clean real-world raw datasets\n• Exploratory Data Analysis notebook\n• Metric calculation scripting")
        with w3:
            st.info("**Week 3: Star Schema & BI Dashboard**\n\n• Fact/Dimension modeling\n• 3-page interactive Power BI / Streamlit panel\n• Drill-down and executive filters")
        with w4:
            st.info("**Week 4: GitHub & Applications**\n\n• Professional README + architecture diagram\n• 3 impact-driven bullets on CV\n• Target 15 applications")

    # ──────────────────────────────────────────────────────────────────────────
    # SUB-TAB 2: AI & LLM / ML Engineering Track
    # ──────────────────────────────────────────────────────────────────────────
    with tab_ai:
        st.subheader("🤖 AI, LLM & Machine Learning Career Standards")
        
        ai_c1, ai_c2, ai_c3, ai_c4 = st.columns(4)
        ai_c1.metric("🎯 Target Roles", "AI / LLM Working Student")
        ai_c2.metric("💰 Hourly Wage Range", "€15 – €20 / hr")
        ai_c3.metric("⏳ Weekly Hours", "16 – 20 Hours (Semester)")
        ai_c4.metric("🏢 Work Model", "Hybrid (Berlin Tech) / Remote")

        st.markdown("---")
        st.markdown("### 🎯 1. Non-Negotiable Core Benchmarks (Must-Haves)")
        st.caption("Production-focused foundations expected by Berlin AI startups and scale-ups:")

        col_ai1, col_ai2 = st.columns(2)
        with col_ai1:
            st.markdown(
                """
                <div style="background-color: #f8fafc; border-left: 4px solid #6366f1; padding: 14px; border-radius: 8px; margin-bottom: 12px;">
                    <strong style="color: #3730a3; font-size: 15px;">1. Modern & Object-Oriented Python (OOP & Async)</strong>
                    <ul style="margin-top: 6px; font-size: 13.5px; color: #334155;">
                        <li><strong>Clean Code & Types:</strong> Type Hinting (<code>typing</code>), Pydantic v2 data validation</li>
                        <li><strong>OOP Architecture:</strong> Class inheritance, dataclasses, modular project structure</li>
                        <li><strong>Asynchronous Programming:</strong> Parallel external API calls using <code>async / await</code></li>
                        <li><em>Interview Expectation:</em> Write modular, testable, type-safe Python code rather than single spaghetti scripts.</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                """
                <div style="background-color: #f8fafc; border-left: 4px solid #0ea5e9; padding: 14px; border-radius: 8px; margin-bottom: 12px;">
                    <strong style="color: #0369a1; font-size: 15px;">2. LLM API Integrations & Prompt Engineering</strong>
                    <ul style="margin-top: 6px; font-size: 13.5px; color: #334155;">
                        <li><strong>API Clients:</strong> Google Gemini SDK, OpenAI API, Anthropic SDK</li>
                        <li><strong>Structured Output:</strong> Guaranteed JSON schemas and Pydantic validation</li>
                        <li><strong>Function Calling / Tool Use:</strong> Enabling models to trigger external Python functions and REST APIs</li>
                        <li><em>Interview Expectation:</em> Implement robust prompt constraints and schema enforcement preventing hallucinations.</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with col_ai2:
            st.markdown(
                """
                <div style="background-color: #f8fafc; border-left: 4px solid #ec4899; padding: 14px; border-radius: 8px; margin-bottom: 12px;">
                    <strong style="color: #9d174d; font-size: 15px;">3. RAG Architecture & Vector Databases</strong>
                    <ul style="margin-top: 6px; font-size: 13.5px; color: #334155;">
                        <li><strong>Chunking Strategies:</strong> RecursiveCharacterTextSplitter, semantic splitting, token limits</li>
                        <li><strong>Embedding Models:</strong> SBERT, text-embedding-3, HuggingFace embeddings</li>
                        <li><strong>Vector Stores:</strong> <code>ChromaDB</code>, <code>FAISS</code>, <code>Qdrant</code>; Cosine & Dot product similarity search</li>
                        <li><em>Interview Expectation:</em> Build a production RAG system indexing enterprise docs (PDF/Word) with cited sources.</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                """
                <div style="background-color: #f8fafc; border-left: 4px solid #14b8a6; padding: 14px; border-radius: 8px; margin-bottom: 12px;">
                    <strong style="color: #0f766e; font-size: 15px;">4. Backend Services & API Development (FastAPI)</strong>
                    <ul style="margin-top: 6px; font-size: 13.5px; color: #334155;">
                        <li><strong>FastAPI Foundations:</strong> Async endpoints (<code>async def</code>), Dependency Injection</li>
                        <li><strong>Streaming Responses:</strong> Server-Sent Events (SSE) for streaming real-time LLM token streams</li>
                        <li><strong>Error Handling:</strong> HTTP status codes, rate limiters, custom exception handlers</li>
                        <li><em>Interview Expectation:</em> Expose AI models to frontends or microservices via clean, documented REST APIs.</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("### 🚀 2. Differentiating 'Game-Changer' Skills")
        st.caption("Advanced capabilities that set you apart in AI Working Student interviews:")

        ai_g1, ai_g2, ai_g3 = st.columns(3)
        with ai_g1:
            st.markdown("**🤖 AI Agents & Workflows**")
            st.write("• **ReAct Loops:** Structured reasoning, tool execution, and observation cycles.")
            st.write("• **LangGraph / CrewAI:** Multi-step, stateful autonomous workflow orchestration.")
        with ai_g2:
            st.markdown("**🐳 Docker & Containerization**")
            st.write("• **Dockerfile:** Optimized multi-stage images isolating Python dependencies.")
            st.write("• **Live Deployment:** Cloud demo hosted on Hugging Face Spaces, Render, or GCP Cloud Run.")
        with ai_g3:
            st.markdown("**⚖️ Evaluation & Guardrails (RAG Triad)**")
            st.write("• **Ragas / TruLens:** Context Relevance, Faithfulness, and Answer Relevance metrics.")
            st.write("• **Guardrails:** Defenses against prompt injection and sensitive data leakage.")

        st.markdown("---")
        st.markdown("### 🏆 3. Interview-Winning Portfolio Project Blueprint")
        st.caption("Reference project architecture to showcase on your GitHub for AI roles:")

        with st.expander("📌 Project Blueprint: 'Production-Ready Enterprise Multimodal RAG & AI Agent'", expanded=True):
            st.markdown("""
```
[ PDF / Documents ] ──> [ Semantic Chunking & Embedding ] ──> [ ChromaDB / Qdrant ]
                                                                      │
                                                               (Vector Search)
                                                                      │
[ User Prompt ] ──> [ FastAPI Backend (Async) ] ────────────────────> │
                                │                                     │
                        (LLM Orchestration)                           ▼
                                │                              [ Relevant Context ]
                                ▼                                     │
                   [ Tool Calling & Web Search ]                      ▼
                                │                              [ Gemini / Claude ]
                                └─────────────────────────────────────┤
                                                                      ▼
                                                      [ Streaming Streamlit / Chainlit UI ]
                                                        (Cited References & Answer)
```
            """)
            st.markdown("""
**Core Deliverables to Include:**
1. **Document Ingestion Pipeline:** Clean parsers extracting text, headers, and tables from PDFs.
2. **Hybrid Search:** Vector similarity combined with keyword-based retrieval (BM25).
3. **Tool Calling Capabilities:** Model triggers external APIs (e.g. currency conversion, web search, database querying).
4. **FastAPI & Async Service:** Production REST API layer serving the application.
5. **Docker & Live Deployment:** One-command startup via `docker compose up` or hosted demo on Hugging Face Spaces.
            """)

        st.markdown("### 📅 4. 4-Week Rapid Action Roadmap")
        ai_w1, ai_w2, ai_w3, ai_w4 = st.columns(4)
        with ai_w1:
            st.info("**Week 1: APIs & Structured Output**\n\n• Gemini / OpenAI SDK practice\n• Pydantic Structured Output schemas\n• Tool Calling & Function Binding")
        with ai_w2:
            st.info("**Week 2: RAG & Vector Stores**\n\n• Chunking & semantic search\n• ChromaDB / Qdrant indexing\n• Top-K retrieval & re-ranking")
        with ai_w3:
            st.info("**Week 3: FastAPI & Streaming UI**\n\n• Async FastAPI REST endpoint\n• Server-Sent Events streaming\n• Streamlit or Chainlit interface")
        with ai_w4:
            st.info("**Week 4: Docker, Testing & Showcase**\n\n• Multi-stage Dockerfile\n• RAG Triad evaluation tests\n• GitHub README, demo GIF & live URL")

    # ──────────────────────────────────────────────────────────────────────────
    # SUB-TAB 3: German Hiring & Interview Tactics
    # ──────────────────────────────────────────────────────────────────────────
    with tab_tips:
        st.subheader("🇩🇪 German & Berlin Tech Market Hiring Dynamics")
        st.caption("Legal status, contract specifics, and interview frameworks for international Working Students in Germany:")

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.markdown("#### 📜 1. Werkstudent Legal Status & Advantages")
            st.markdown("""
- **20-Hour Rule (20-Stunden-Regel):** You can work up to 20 hours/week during semester time (*Vorlesungszeit*). During semester breaks (*Vorlesungsfreie Zeit*), you are legally allowed to work full-time (up to 40 hours/week).
- **Major Employer Advantage:** Employers are exempt from paying healthcare and unemployment contributions for Werkstudenten (only pension contribution is deducted). Consequently, German companies strongly prefer hiring Working Students over expensive juniors.
- **University Enrollment Certificate (Immatrikulationsbescheinigung):** An active enrollment certificate at any state-recognized German university is sufficient (e.g. Steinbeis University Berlin).
            """)

            st.markdown("#### 💬 2. The STAR Framework in English Interviews")
            st.markdown("""
Tech companies in Berlin evaluate technical and behavioral interview responses using the **STAR methodology**:
- **S (Situation):** What was the business context or problem? (Keep it concise and clear).
- **T (Task):** What was your specific responsibility and assignment in that situation?
- **A (Action):** What concrete technical steps did you take? (e.g. *"Optimized Pandas queries, designed modular CTEs"*).
- **R (Result):** What was the measurable impact? (e.g. *"Query execution time decreased by 40%, saved 3 engineering hours weekly"*).
            """)

        with col_t2:
            st.markdown("#### 🧪 3. Cracking the Take-Home Case Study")
            st.markdown("""
Berlin companies frequently issue a 24-48 hour practical take-home assignment in stage 2 or 3. Hiring managers look for:
1. **Zero-Friction Executability:** The project runs cleanly with a single command (`python main.py` or `docker compose up`).
2. **README Quality:** Clear architecture overview, design assumptions, setup commands, and technical trade-offs.
3. **Code Hygiene:** Type annotations on functions, clean naming conventions, and modular separation of concerns.
4. **Executive Insights:** Present analytical findings as 3-4 bullet business recommendations that a Product Manager can act on immediately.
            """)

            st.markdown("#### ⚡ 4. Application Speed & ATS Alignment")
            st.markdown("""
- **First 48-Hour Rule:** Applications submitted within the first 48 hours of posting have a 70% higher review rate. Never miss new notifications.
- **ATS Keywords:** Seamlessly align CV bullet points with concrete technologies (*dbt, PostgreSQL, FastAPI, RAG*). Use the **Job Matcher & Applications** tab to tailor your CV in seconds.
            """)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — APPLICATION CRM & EMAIL HUB
# ══════════════════════════════════════════════════════════════════════════════
elif active_tab == "📬 Application CRM & Email Hub":
    st.markdown('<div class="section-header">📬 Application CRM & Email Hub (Follow-up Tracker)</div>', unsafe_allow_html=True)
    st.caption("Manage application statuses, generate automated follow-up emails after 7 days, and track recruitment emails from your Gmail inbox with AI.")

    applied_jobs = load_applied_jobs()

    # Pre-calculate elapsed days for each applied job
    from datetime import timedelta
    today_date = datetime.now(timezone.utc).date()
    for aj in applied_jobs:
        raw_app_date = (aj.get("applied_at") or aj.get("created_at") or "")[:10]
        try:
            d_parsed = datetime.strptime(raw_app_date, "%Y-%m-%d").date()
            aj["_days_elapsed"] = (today_date - d_parsed).days
            aj["_display_date"] = raw_app_date
        except Exception:
            aj["_days_elapsed"] = 0
            aj["_display_date"] = raw_app_date or "Not specified"

    fu_needed = [j for j in applied_jobs if j.get("status") == "applied" and j.get("_days_elapsed", 0) >= 7]
    pending_apps = [j for j in applied_jobs if j.get("status") == "applied" and j.get("_days_elapsed", 0) < 7]
    interview_apps = [j for j in applied_jobs if j.get("status") == "interview"]
    assessment_apps = [j for j in applied_jobs if j.get("status") == "assessment"]
    rejected_apps = [j for j in applied_jobs if j.get("status") == "rejected"]

    # Sub-tabs
    crm_tab1, crm_tab2 = st.tabs([
        f"🗓️ Application Pipeline ({len(applied_jobs)})",
        "📧 Gmail Sync & Smart Classifier",
    ])

    # ──────────────────────────────────────────────────────────────────────────
    # SUB-TAB 1: Application Pipeline & Follow-Up Calendar
    # ──────────────────────────────────────────────────────────────────────────
    with crm_tab1:
        crm_c1, crm_c2, crm_c3, crm_c4 = st.columns(4)
        crm_c1.metric("🔔 Follow-Up Due", len(fu_needed), help="Applications submitted 7 or more days ago without response")
        crm_c2.metric("⏳ Awaiting Response", len(pending_apps))
        crm_c3.metric("🎉 Interview / Assessment", len(interview_apps) + len(assessment_apps))
        crm_c4.metric("📁 Total Tracked", len(applied_jobs))

        st.write("")

        if not applied_jobs:
            st.info(
                "💡 **No tracked applications yet.**\n\n"
                "1. Go to the **'🎯 Job Matcher & Applications'** tab.\n"
                "2. Click the **'✅ Applied'** button under any listing you submitted.\n"
                "3. The job will appear here automatically and start its 7-day follow-up countdown!"
            )
            # Quick demo helper to test the feature
            if st.button("🧪 Add Sample Application (To Test Feature)", key="btn_add_demo_app"):
                all_unapplied = [j for j in jobs if j.get("status") not in ("applied", "interview", "assessment", "rejected")]
                if all_unapplied:
                    demo_target = all_unapplied[0]
                    # Set applied date to 8 days ago
                    eight_days_ago = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()[:10]
                    db.update_status(demo_target["id"], "applied", applied_date=eight_days_ago)
                    st.cache_data.clear()
                    st.success(f"Application for '{demo_target['company']} - {demo_target['title']}' added (marked as 8 days ago)!")
                    st.rerun()
        else:
            filter_choice = st.radio(
                "Filter Applications:",
                [
                    f"All ({len(applied_jobs)})",
                    f"🔔 Follow-up Due (≥7 Days) ({len(fu_needed)})",
                    f"⏳ Awaiting Response ({len(pending_apps)})",
                    f"🎉 Interviews & Tests ({len(interview_apps) + len(assessment_apps)})",
                    f"❌ Rejected ({len(rejected_apps)})",
                ],
                horizontal=True,
            )

            if "Follow-up" in filter_choice:
                displayed_jobs = fu_needed
            elif "Awaiting Response" in filter_choice:
                displayed_jobs = pending_apps
            elif "Interviews & Tests" in filter_choice:
                displayed_jobs = interview_apps + assessment_apps
            elif "Rejected" in filter_choice:
                displayed_jobs = rejected_apps
            else:
                displayed_jobs = applied_jobs

            if not displayed_jobs:
                st.info("No applications found matching this filter.")

            for job in displayed_jobs:
                job_id = job["id"]
                days = job.get("_days_elapsed", 0)
                status = job.get("status", "applied")

                with st.container():
                    st.markdown("---")
                    col_info, col_actions = st.columns([3, 2])

                    with col_info:
                        # Status badge display
                        if status == "interview":
                            badge_html = '<span class="badge-interview">🎉 INTERVIEW STAGE</span>'
                        elif status == "assessment":
                            badge_html = '<span class="badge-assessment">💻 CODING / ASSESSMENT</span>'
                        elif status == "rejected":
                            badge_html = '<span class="badge-rejected">❌ REJECTED</span>'
                        elif days >= 7:
                            badge_html = f'<span class="badge-followup">🔔 FOLLOW-UP DUE (Day {days})</span>'
                        else:
                            badge_html = f'<span class="badge-applied">⏳ Day {days} — Awaiting Response</span>'

                        st.markdown(f"### {job.get('company')} — {job.get('title')} &nbsp; {badge_html}", unsafe_allow_html=True)
                        st.caption(f"📅 **Applied Date:** {job.get('_display_date')} &nbsp;|&nbsp; 📍 {job.get('location', 'Berlin')} &nbsp;|&nbsp; [🔗 View Listing]({job.get('url', '#')})")

                        if job.get("email_notes"):
                            st.info(f"📨 **Latest Email Update:** {job['email_notes']}")

                    with col_actions:
                        st.markdown("**Update Status:**")
                        status_options = ["applied", "interview", "assessment", "rejected", "saved"]
                        status_labels = {
                            "applied": "✅ Applied (Awaiting Response)",
                            "interview": "🎉 Interview Invitation",
                            "assessment": "💻 Coding Test / Assessment",
                            "rejected": "❌ Not Selected / Rejected",
                            "saved": "⏳ Saved for Later",
                        }
                        current_idx = status_options.index(status) if status in status_options else 0
                        new_status_val = st.selectbox(
                            "Select Status",
                            options=status_options,
                            format_func=lambda x: status_labels.get(x, x),
                            index=current_idx,
                            key=f"crm_stat_sel_{job_id}",
                            label_visibility="collapsed",
                        )
                        if new_status_val != status:
                            db.update_status(job_id, new_status_val)
                            st.cache_data.clear()
                            st.toast(f"{job.get('company')} status updated: {status_labels.get(new_status_val)}")
                            st.rerun()

                        col_crm_fu, col_crm_del = st.columns([3, 1.2])
                        with col_crm_fu:
                            # Follow up action button
                            btn_label = "✉️ Generate Follow-Up Email (Gemini)" if days >= 7 else "✉️ Generate Follow-Up Email"
                            btn_type = "primary" if days >= 7 else "secondary"
                            if st.button(btn_label, key=f"crm_fu_btn_{job_id}", type=btn_type, use_container_width=True):
                                with st.spinner("✍️ Gemini is writing your follow-up email..."):
                                    try:
                                        from src.ai_assistant import generate_follow_up_email
                                        fu_text = generate_follow_up_email(
                                            job_title=job.get("title", ""),
                                            job_company=job.get("company", ""),
                                            applied_date=job.get("_display_date", ""),
                                            job_description=job.get("description", ""),
                                            cv=cv if "cv" in locals() else None,
                                        )
                                        st.session_state[f"fu_draft_{job_id}"] = fu_text
                                    except Exception as exc:
                                        st.error(f"Follow-up generation failed: {exc}")
                        with col_crm_del:
                            if st.button("🗑️ Delete Application", key=f"crm_del_{job_id}", use_container_width=True, help="Permanently delete this application from the database"):
                                db.delete_job(job_id)
                                st.cache_data.clear()
                                st.toast(f"🗑️ {job.get('company')} application deleted!")
                                st.rerun()

                    # If draft exists in session state, show editor and actions
                    if f"fu_draft_{job_id}" in st.session_state:
                        st.markdown("##### ✉️ Generated Follow-Up Email Draft")
                        fu_edited = st.text_area(
                            label=f"Follow-Up Draft #{job_id}",
                            value=st.session_state[f"fu_draft_{job_id}"],
                            height=220,
                            key=f"fu_txt_{job_id}",
                            label_visibility="collapsed",
                        )

                        # Extract subject line if present
                        _cand_name = cv.get("personal", {}).get("name", "Candidate") if "cv" in locals() and cv else "Candidate"
                        subject_line = f"Follow-up: Application for {job.get('title', '')} - {_cand_name}"
                        body_to_send = fu_edited
                        for line in fu_edited.split("\n"):
                            if line.lower().startswith("subject:"):
                                subject_line = line.split(":", 1)[1].strip()
                                body_to_send = fu_edited.replace(line, "").strip()
                                break

                        col_fu_dl, col_fu_mail = st.columns(2)
                        with col_fu_dl:
                            st.download_button(
                                label="📥 Download Email Draft (.txt)",
                                data=fu_edited,
                                file_name=f"FollowUp_{job.get('company','company')}.txt",
                                mime="text/plain",
                                key=f"dl_fu_{job_id}",
                                use_container_width=True,
                            )
                        with col_fu_mail:
                            mailto_url = f"mailto:?subject={quote(subject_line)}&body={quote(body_to_send)}"
                            st.markdown(
                                f'<a href="{mailto_url}" target="_blank" style="display:inline-block; width:100%; text-align:center; background:#2563eb; color:white; padding:8px 16px; border-radius:8px; text-decoration:none; font-weight:600;">🚀 Open in Email Client (Mailto)</a>',
                                unsafe_allow_html=True,
                            )

    # ──────────────────────────────────────────────────────────────────────────
    # SUB-TAB 2: Gmail Sync & Email Intelligence
    # ──────────────────────────────────────────────────────────────────────────
    with crm_tab2:
        st.markdown("#### 📨 Gmail Inbox Synchronization")
        st.caption("Automatically scan your Gmail inbox to detect application confirmations, interview invites, and rejections with AI.")

        def _save_gmail_creds(u: str, p: str):
            env_file = Path(__file__).resolve().parent / ".env"
            u_clean = u.strip()
            p_clean = p.strip().replace(" ", "")
            os.environ["GMAIL_USER"] = u_clean
            os.environ["GMAIL_APP_PASSWORD"] = p_clean

            lines = []
            if env_file.exists():
                with open(env_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()

            u_found = False
            p_found = False
            new_lines = []
            for l in lines:
                if l.strip().startswith("GMAIL_USER="):
                    new_lines.append(f"GMAIL_USER={u_clean}\n")
                    u_found = True
                elif l.strip().startswith("GMAIL_APP_PASSWORD="):
                    new_lines.append(f"GMAIL_APP_PASSWORD={p_clean}\n")
                    p_found = True
                else:
                    new_lines.append(l)

            if not u_found:
                new_lines.append(f"GMAIL_USER={u_clean}\n")
            if not p_found:
                new_lines.append(f"GMAIL_APP_PASSWORD={p_clean}\n")

            with open(env_file, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

        def _disconnect_gmail():
            env_file = Path(__file__).resolve().parent / ".env"
            os.environ.pop("GMAIL_USER", None)
            os.environ.pop("GMAIL_APP_PASSWORD", None)
            if env_file.exists():
                with open(env_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                new_lines = [l for l in lines if not (l.strip().startswith("GMAIL_USER=") or l.strip().startswith("GMAIL_APP_PASSWORD="))]
                with open(env_file, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)

        gmail_user = os.getenv("GMAIL_USER")
        gmail_pass = os.getenv("GMAIL_APP_PASSWORD")

        col_g1, col_g2 = st.columns([3, 2])

        with col_g1:
            if gmail_user and gmail_pass:
                st.success(f"✅ **Gmail Integration Active:** `{gmail_user}`")
                
                c_scan_col, c_disc_col = st.columns([3, 1])
                with c_disc_col:
                    if st.button("🔌 Disconnect", key="btn_disconnect_gmail", help="Clear Gmail credentials"):
                        _disconnect_gmail()
                        st.session_state.pop("last_gmail_scan_results", None)
                        st.session_state.pop("last_gmail_scan_stats", None)
                        st.rerun()

                # Date Filter Selector
                date_filter_mode = st.radio(
                    "📅 **Date Range Filter:**",
                    options=["Last 14 Days", "Last 7 Days", "Last 30 Days", "Last 90 Days", "All Time", "Custom Date Range"],
                    horizontal=True,
                    key="radio_email_date_filter",
                )

                param_days_back = 14
                param_start_date = None
                param_end_date = None

                if date_filter_mode == "Last 7 Days":
                    param_days_back = 7
                elif date_filter_mode == "Last 14 Days":
                    param_days_back = 14
                elif date_filter_mode == "Last 30 Days":
                    param_days_back = 30
                elif date_filter_mode == "Last 90 Days":
                    param_days_back = 90
                elif date_filter_mode == "All Time":
                    param_days_back = None
                elif date_filter_mode == "Custom Date Range":
                    param_days_back = None
                    c_d1, c_d2 = st.columns(2)
                    with c_d1:
                        param_start_date = st.date_input("Start Date:", value=datetime.now().date() - timedelta(days=30))
                    with c_d2:
                        param_end_date = st.date_input("End Date:", value=datetime.now().date())

                scan_max_emails = st.slider("Maximum emails to scan:", min_value=20, max_value=300, value=100, step=20)

                if st.button("📬 Sync & Analyze Inbox Now", type="primary", use_container_width=True):
                    with st.spinner("Scanning Gmail inbox and classifying recruitment emails with Gemini..."):
                        try:
                            from src.email_tracker import sync_gmail
                            res = sync_gmail(
                                days_back=param_days_back,
                                start_date=param_start_date,
                                end_date=param_end_date,
                                max_emails=scan_max_emails,
                            )
                            st.session_state["last_gmail_scan_stats"] = res
                            st.session_state["last_gmail_scan_results"] = res.get("updates", [])
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Error occurred: {exc}")
            else:
                st.warning("⚠️ **Gmail Automatic Sync Not Configured Yet**")
                st.markdown("Connect your account in 1 minute to automatically scan recruitment, interview, and rejection emails directly from Gmail:")
                
                with st.form("form_gmail_connect"):
                    in_u = st.text_input("Your Gmail Address:", placeholder="yourname@gmail.com")
                    in_p = st.text_input("16-Digit Google App Password:", type="password", placeholder="xxxx xxxx xxxx xxxx")
                    btn_save_cred = st.form_submit_button("💾 Save & Connect to Gmail", type="primary", use_container_width=True)
                    if btn_save_cred:
                        if not in_u.strip() or not in_p.strip():
                            st.error("Please enter both email and password fields.")
                        else:
                            _save_gmail_creds(in_u, in_p)
                            st.toast("✅ Gmail credentials saved successfully!")
                            st.rerun()

        with col_g2:
            st.info(
                "💡 **Privacy & Security:**\n\n"
                "- Emails are scanned strictly on your local machine via IMAP SSL.\n"
                "- Only emails containing application and career keywords are processed.\n"
                "- Personal emails are never stored or logged."
            )
            with st.expander("📌 How to Generate a 16-Digit App Password (1 Minute)", expanded=False):
                st.markdown("""
                1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
                2. Enter **JobTracker** as app name and click **Create**.
                3. Copy the 16-digit password and paste it into the box on the left.
                *(Note: 2-Step Verification must be enabled on your Google account)*
                """)

        # ── Categorized Email Results ──────────────────────────────────────────
        updates = st.session_state.get("last_gmail_scan_results", [])
        stats = st.session_state.get("last_gmail_scan_stats", None)

        if stats:
            st.write("")
            if not stats.get("success"):
                st.error(f"❌ Gmail scan error: {stats.get('error')}")
            elif not updates:
                st.info(f"ℹ️ Scanned {stats.get('processed', 0)} emails. No new application updates, interview invites, or rejections detected with current filter.")
            else:
                st.success(f"✨ **Scan Complete!** Processed {stats.get('processed', 0)} emails, categorized **{len(updates)}** recruitment emails.")

        if updates:
            metrics = stats.get("metrics", {}) if stats else {}
            insights = stats.get("insights", "") if stats else ""

            interviews = [u for u in updates if u.get("category") == "INTERVIEW"]
            assessments = [u for u in updates if u.get("category") == "ASSESSMENT"]
            rejections = [u for u in updates if u.get("category") == "REJECTED"]
            received = [u for u in updates if u.get("category") == "RECEIVED"]

            st.markdown("#### 📊 Application Funnel & Metrics")
            km1, km2, km3, km4, km5 = st.columns(5)
            km1.metric("🏢 Unique Companies", metrics.get("unique_companies_count", len(set(u.get("company") for u in updates))))
            km2.metric("🎉 Interviews", len(interviews), delta=f"{metrics.get('interview_rate_percent', 0.0)}%" if metrics else None)
            km3.metric("💻 Tests / Assessments", len(assessments))
            km4.metric("❌ Rejections", len(rejections), delta=f"-{metrics.get('rejection_rate_percent', 0.0)}%" if metrics else None, delta_color="inverse")
            km5.metric("📈 Response Rate", f"{metrics.get('response_rate_percent', 0.0)}%" if metrics else "—")

            if insights:
                with st.expander("✨ 💡 Gemini Career Scorecard & Strategy Insights", expanded=True):
                    st.markdown(insights)

            st.markdown("#### 📬 Detected Application Emails")

            def _render_card(u, badge_bg, badge_fg, badge_text):
                ns = u.get("next_step", "")
                has_ns = ns and ns.lower() not in ("none", "n/a", "yok", "yoktur", "no action needed")
                st.markdown(
                    f"""
                    <div style="background:#ffffff; border:1px solid #e2e8f0; border-left:5px solid {badge_fg}; padding:14px 16px; border-radius:8px; margin-bottom:12px; box-shadow:0 1px 3px rgba(0,0,0,0.04);">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                            <span style="font-size:16px; font-weight:700; color:#0f172a;">🏢 {u.get('company')} {('— ' + u.get('position')) if u.get('position') else ''}</span>
                            <span style="background:{badge_bg}; color:{badge_fg}; font-size:12px; font-weight:700; padding:3px 10px; border-radius:12px;">{badge_text}</span>
                        </div>
                        <div style="font-size:13px; color:#64748b; margin-bottom:8px;">
                            <b>Subject:</b> {u.get('subject')}<br>
                            <b>From:</b> {u.get('sender')} &nbsp;|&nbsp; <b>Date:</b> {u.get('date')}
                        </div>
                        <div style="background:#f8fafc; border-radius:6px; padding:10px 12px; font-size:14px; color:#1e293b; margin-bottom:8px; border-left:3px solid #cbd5e1;">
                            💡 <b>Summary:</b> {u.get('summary')}
                        </div>
                        {f'<div style="color:#b91c1c; font-weight:600; font-size:13.5px; margin-bottom:6px;">⚡ <b>Next Action:</b> {ns}</div>' if has_ns else ''}
                        <div style="font-size:13px; margin-top:6px;">
                            {('<span style="color:#15803d; font-weight:600;">✅ Application automatically updated in database (' + str(u.get('matched_company')) + ')</span>') if u.get('db_updated') else (('<span style="color:#2563eb;">ℹ️ CRM Listing: ' + str(u.get('matched_company')) + '</span>') if u.get('matched_job') else '<span style="color:#94a3b8;">ℹ️ No matching application found in CRM database yet.</span>')}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            t_int, t_ass, t_rej, t_rec, t_all = st.tabs([
                f"🎉 Interviews ({len(interviews)})",
                f"💻 Assessments ({len(assessments)})",
                f"❌ Rejections ({len(rejections)})",
                f"📩 Confirmations ({len(received)})",
                f"📋 All Emails ({len(updates)})",
            ])

            with t_int:
                if not interviews:
                    st.info("No emails found in this category.")
                for item in interviews:
                    _render_card(item, "#dcfce7", "#15803d", "INTERVIEW INVITE")

            with t_ass:
                if not assessments:
                    st.info("No emails found in this category.")
                for item in assessments:
                    _render_card(item, "#f3e8ff", "#7e22ce", "ASSESSMENT TEST")

            with t_rej:
                if not rejections:
                    st.info("No emails found in this category.")
                for item in rejections:
                    _render_card(item, "#fee2e2", "#b91c1c", "REJECTION NOTICE")

            with t_rec:
                if not received:
                    st.info("No emails found in this category.")
                for item in received:
                    _render_card(item, "#e0f2fe", "#0369a1", "APPLICATION RECEIVED")

            with t_all:
                st.markdown(f"**Listing {len(updates)} total emails:**")
                for item in updates:
                    cat = item.get("category", "")
                    badge_colors = {
                        "INTERVIEW": ("#dcfce7", "#15803d", "INTERVIEW"),
                        "ASSESSMENT": ("#f3e8ff", "#7e22ce", "ASSESSMENT"),
                        "REJECTED": ("#fee2e2", "#b91c1c", "REJECTED"),
                        "RECEIVED": ("#e0f2fe", "#0369a1", "RECEIVED"),
                    }.get(cat, ("#f1f5f9", "#475569", cat))
                    _render_card(item, badge_colors[0], badge_colors[1], badge_colors[2])

            rep_text = f"# 📬 Email Application Intelligence Report\n\n{insights}\n\n## 📋 Application List\n\n" + "\n".join([f"- **{u.get('date')}** | **{u.get('company')}** ({u.get('position', '')}) | `{u.get('category')}` | {u.get('summary')}" for u in updates])
            st.download_button(
                "📥 Download Analysis Report (.md)",
                data=rep_text,
                file_name=f"email_application_report_{datetime.now().strftime('%Y%m%d')}.md",
                mime="text/markdown",
                use_container_width=True,
            )

        st.divider()

        # ── Interactive Email Simulator / Manual Classifier ───────────────────
        st.markdown("#### 🧪 Email Simulator & Manual Classifier")
        st.caption("Paste any interview invitation or rejection email; Gemini classifies it instantly and updates matching company statuses in your database.")

        # Preset test templates
        col_t1, col_t2, col_t3 = st.columns(3)
        if "sim_sender" not in st.session_state:
            st.session_state["sim_sender"] = "recruiting@bain.com"
        if "sim_subject" not in st.session_state:
            st.session_state["sim_subject"] = "Invitation: First Round Interview - Working Student Data Analytics - Alex Taylor"
        if "sim_body" not in st.session_state:
            st.session_state["sim_body"] = "Dear Alex,\n\nThank you for applying to the Working Student Data Analytics role at Bain & Company. We were very impressed with your background in AI and Data Analytics. We would like to invite you to a 45-minute technical interview next week.\n\nPlease use the link below to select a time slot that works best for you:\nhttps://calendly.com/bain-tech-interview/alex\n\nBest regards,\nBain Talent Acquisition Team"

        with col_t1:
            if st.button("🎉 Example: Interview Invite (Bain)", use_container_width=True):
                st.session_state["sim_sender"] = "recruiting@bain.com"
                st.session_state["sim_subject"] = "Invitation: First Round Interview - Working Student Data Analytics - Alex Taylor"
                st.session_state["sim_body"] = "Dear Alex,\n\nThank you for applying to the Working Student Data Analytics role at Bain & Company. We were very impressed with your background in AI and Data Analytics. We would like to invite you to a 45-minute technical interview next week.\n\nPlease use the link below to select a time slot that works best for you:\nhttps://calendly.com/bain-tech-interview/alex\n\nBest regards,\nBain Talent Acquisition Team"
                st.rerun()

        with col_t2:
            if st.button("❌ Example: Polite Rejection (Personio)", use_container_width=True):
                st.session_state["sim_sender"] = "no-reply@personio.de"
                st.session_state["sim_subject"] = "Update regarding your application for Junior Data Analyst at Personio"
                st.session_state["sim_body"] = "Dear Alex,\n\nThank you very much for your interest in Personio and for taking the time to apply for the Junior Data Analyst position.\n\nWe received many applications from talented candidates, making our decision difficult. Unfortunately, we have decided not to move forward with your application for this role at this time.\n\nWe wish you all the best in your career search.\n\nSincerely,\nPersonio People Team"
                st.rerun()

        with col_t3:
            if st.button("💻 Example: Coding Test (Delivery Hero)", use_container_width=True):
                st.session_state["sim_sender"] = "talent@deliveryhero.com"
                st.session_state["sim_subject"] = "Next Step: Technical Assessment for Software Working Student"
                st.session_state["sim_body"] = "Hi Alex,\n\nThanks for applying to Delivery Hero! As the next step in our process, please complete the following 60-minute HackerRank coding challenge within the next 5 days:\nhttps://hackerrank.com/test/delivery-hero-assessment\n\nGood luck!\nDelivery Hero Engineering Recruitment"
                st.rerun()

        with st.form("email_simulator_form"):
            in_sender = st.text_input("Sender (From / Company):", value=st.session_state.get("sim_sender", ""))
            in_subject = st.text_input("Email Subject:", value=st.session_state.get("sim_subject", ""))
            in_body = st.text_area("Email Body:", value=st.session_state.get("sim_body", ""), height=150)
            btn_analyze = st.form_submit_button("🧠 Classify Email & Update Status with Gemini", type="primary", use_container_width=True)

        if btn_analyze:
            if not in_body.strip():
                st.warning("Please enter an email body to analyze.")
            elif not os.getenv("GEMINI_API_KEY"):
                st.error("GEMINI_API_KEY not configured.")
            else:
                with st.spinner("🤖 Gemini is analyzing email, extracting entities, and checking database matches..."):
                    try:
                        from src.email_tracker import classify_email_with_gemini
                        res_sim = classify_email_with_gemini(
                            sender=in_sender,
                            subject=in_subject,
                            date_str=datetime.now(timezone.utc).isoformat()[:16],
                            body=in_body,
                        )

                        category = res_sim.get("category", "UNRELATED")
                        company = res_sim.get("company", "")
                        summary = res_sim.get("summary", "")
                        next_step = res_sim.get("next_step", "")

                        cat_colors = {
                            "INTERVIEW": ("#dcfce7", "#15803d", "🎉 INTERVIEW INVITATION"),
                            "ASSESSMENT": ("#f3e8ff", "#7e22ce", "💻 CODING / TECHNICAL ASSESSMENT"),
                            "REJECTED": ("#fee2e2", "#b91c1c", "❌ REJECTION NOTICE"),
                            "RECEIVED": ("#e0f2fe", "#0369a1", "📩 APPLICATION CONFIRMATION"),
                            "UNRELATED": ("#f1f5f9", "#475569", "⚪ NOT APPLICATION RELATED"),
                        }
                        bg, fg, title_cat = cat_colors.get(category, ("#f1f5f9", "#475569", category))

                        st.markdown(
                            f"""
                            <div style="background:{bg}; color:{fg}; padding:14px; border-radius:10px; margin-top:10px;">
                                <h4 style="margin:0 0 6px 0;">{title_cat}</h4>
                                <b>Detected Company:</b> {company or 'Unknown'} &nbsp;|&nbsp; <b>Position:</b> {res_sim.get('position') or 'Not specified'}<br>
                                <b>Summary:</b> {summary}<br>
                                <b>Next Action:</b> {next_step or 'None'}
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                        # Match with DB
                        if company:
                            matched_job = db.find_job_by_company(company)
                            status_map = {
                                "INTERVIEW": "interview",
                                "REJECTED": "rejected",
                                "ASSESSMENT": "assessment",
                            }
                            new_st = status_map.get(category)
                            if matched_job and new_st:
                                note = f"[{category}] {summary} ({datetime.now(timezone.utc).isoformat()[:10]})"
                                db.update_job_from_email(matched_job["id"], new_st, note)
                                st.cache_data.clear()
                                st.success(f"🎯 **Match Found!** Application status for **{matched_job['company']} - {matched_job['title']}** was automatically updated to **'{new_st.upper()}'**!")
                            elif matched_job:
                                st.info(f"ℹ️ Found **{matched_job['company']}** in database, but category ({category}) requires no status change.")
                            else:
                                st.info(f"ℹ️ No active application record found for '{company}' in database yet. Add the listing to your CRM to track it.")

                    except Exception as exc:
                        st.error(f"Analysis error: {exc}")
