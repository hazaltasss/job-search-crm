"""
dashboard.py — Job Search CRM Intelligence Dashboard

Streamlit ile çalışır:
    streamlit run dashboard.py

İki ana sekme:
  📊 Market Intelligence  — Top skills bar chart, hiring company leaderboard
  🎯 Job Matcher & AI     — Skill gap analizi, CV optimizasyonu, cover letter
"""
import os
import sys
import json
from pathlib import Path

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

# Set placeholder values for vars the dashboard doesn't actually need —
# they will be validated properly when Telegram/Sheets functions are called.
for _var in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GOOGLE_SHEET_ID"]:
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
    initial_sidebar_state="expanded",
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
</style>
""", unsafe_allow_html=True)


# ─── Data loading helpers ─────────────────────────────────────────────────────

import importlib
from src import database as db
importlib.reload(db)
db.init_db()
db.ensure_default_profile()


def _load_db_module():
    """Return database module directly."""
    return db


@st.cache_data(ttl=5)
def load_jobs() -> list[dict]:
    return db.get_all_jobs()


@st.cache_data(ttl=5)
def load_stats() -> dict:
    return db.get_stats()


@st.cache_data(ttl=5)
def load_applied_jobs() -> list[dict]:
    return db.get_applied_jobs()


@st.cache_data(ttl=5)
def load_cv() -> dict:
    active_profile = db.get_active_profile()
    if active_profile and active_profile.get("data"):
        return active_profile["data"]
    cv_path = ROOT / "data" / "master_cv.json"
    if cv_path.exists():
        with open(cv_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


@st.cache_data(ttl=300)
def compute_skill_frequencies(descriptions: list[str], total: int) -> list[dict]:
    from src.match_analyzer import skill_frequency_from_db
    return skill_frequency_from_db(descriptions, total)


# ─── Sidebar Multi-Profile Management ─────────────────────────────────────────
def render_sidebar_profiles():
    with st.sidebar:
        st.markdown("### 👤 Aday Profili & CV Yönetimi")
        st.caption("Farklı CV'ler yükleyerek sistemi başka adaylar için de kullanabilirsiniz.")

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
            "Aktif Aday Profili:",
            prof_options,
            index=prof_idx,
            format_func=_format_prof,
            key="sidebar_active_profile_select",
        )

        if selected_pid != active_id:
            db.set_active_profile(selected_pid)
            st.cache_data.clear()
            st.session_state.pop("tailored_cv_working", None)
            st.session_state.pop("tailored_cv_job_id", None)
            st.session_state.pop("cv_opt_meta", None)
            st.session_state.pop("cv_copilot_messages", None)
            st.rerun()

        if active_p:
            cand_skills = active_p.get("data", {}).get("skills", {})
            total_skills_count = sum(len(v) for v in cand_skills.values() if isinstance(v, list)) if isinstance(cand_skills, dict) else 0
            st.info(f"**Aktif Aday:** {active_p['name']}\n\n🎓 {active_p.get('headline', '')}\n\n🛠️ {total_skills_count} Kayıtlı Beceri")

            if active_id != "default_hazal":
                if st.button("🗑️ Bu Profili Sil", type="secondary", use_container_width=True, help="Bu adayın profilini sistemden kaldırır"):
                    db.delete_profile(active_id)
                    db.set_active_profile("default_hazal")
                    st.cache_data.clear()
                    st.session_state.pop("tailored_cv_working", None)
                    st.session_state.pop("tailored_cv_job_id", None)
                    st.session_state.pop("cv_opt_meta", None)
                    st.session_state.pop("cv_copilot_messages", None)
                    st.success("Profil silindi, varsayılan profile dönüldü.")
                    st.rerun()

        st.divider()

        with st.expander("➕ Yeni CV Yükle & Profil Oluştur", expanded=False):
            st.caption("PDF veya Word (.docx) formatındaki CV'nizi yükleyin. Gemini AI tüm bilgileri, becerileri ve deneyimleri otomatik ayrıştırıp sisteme ekler.")
            uploaded_cv = st.file_uploader("CV Dosyası Seç:", type=["pdf", "docx"], key="sidebar_cv_file_uploader")

            if uploaded_cv is not None:
                if st.button("🚀 CV'yi Gemini ile Ayrıştır", type="primary", use_container_width=True, key="btn_parse_cv_upload"):
                    with st.spinner("📄 CV metni okunuyor ve Gemini analiz ediyor… (10–20 sn)"):
                        try:
                            from src.cv_parser import extract_text_from_upload, parse_cv_with_gemini
                            file_bytes = uploaded_cv.getvalue()
                            raw_text = extract_text_from_upload(file_bytes, uploaded_cv.name)
                            if not raw_text.strip():
                                st.error("⚠️ Dosyadan metin okunamadı. Lütfen metin içeren bir PDF/Word dosyası yükleyin.")
                            else:
                                parsed = parse_cv_with_gemini(raw_text)
                                st.session_state["pending_profile_cv"] = parsed
                                st.success("✅ CV başarıyla analiz edildi! Bilgileri kontrol edip kaydedebilirsiniz.")
                        except Exception as parse_err:
                            st.error(f"Ayrıştırma hatası: {parse_err}")

            if "pending_profile_cv" in st.session_state:
                pending = st.session_state["pending_profile_cv"]
                p_name = pending.get("personal", {}).get("name", "Yeni Aday")
                p_edu = pending.get("education", [{}])[0].get("degree", "Data / Software") if pending.get("education") else "Professional"
                default_slug = re.sub(r"[^a-zA-Z0-9_]", "_", p_name.lower().strip()) or "candidate"

                st.markdown("---")
                st.markdown("##### 📋 Profil Önizleme & Onay")
                input_name = st.text_input("Ad Soyad:", value=p_name, key="new_prof_name")
                input_headline = st.text_input("Başlık / Ünvan:", value=p_edu, key="new_prof_headline")
                input_slug = st.text_input("Profil Kimliği (ID):", value=default_slug, key="new_prof_id")

                st.caption(f"💼 Deneyim: {len(pending.get('experience', []))} | 🔬 Proje: {len(pending.get('projects', []))}")
                skills_preview = []
                for k, v in pending.get("skills", {}).items():
                    if isinstance(v, list):
                        skills_preview.extend(v[:3])
                if skills_preview:
                    st.caption(f"🛠️ Beceriler: {', '.join(skills_preview[:6])}...")

                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("✅ Kaydet & Aktif Et", type="primary", use_container_width=True, key="btn_save_pending_profile"):
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
                        st.session_state.pop("tailored_cv_working", None)
                        st.session_state.pop("tailored_cv_job_id", None)
                        st.session_state.pop("cv_opt_meta", None)
                        st.session_state.pop("cv_copilot_messages", None)
                        st.success(f"🎉 {input_name} profili kaydedildi ve aktif hale getirildi!")
                        st.rerun()
                with col_cancel:
                    if st.button("❌ İptal", use_container_width=True, key="btn_cancel_pending_profile"):
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
    st.write("")
    if st.button("🔄 Yeni İlanları Tara", use_container_width=True, type="secondary"):
        with st.spinner("İlan siteleri taranıyor ve filtreleniyor..."):
            try:
                from scripts.run_pipeline import main as run_pipeline
                run_pipeline()
                st.cache_data.clear()
                st.success("Tarama tamamlandı! İlanlar güncellendi.")
                st.rerun()
            except Exception as e:
                st.error(f"Tarama hatası: {e}")

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
c1.metric("📋 Toplam İlan", total)
c2.metric("✅ Başvurulan", applied)
c3.metric("🎉 Mülakat / Test", interview + assessment)
c4.metric("⏳ Kaydedilen", saved)
c5.metric("❌ Reddedilen", rejected)
c6.metric("📈 Başvuru Oranı", app_rate)

st.divider()

# ─── Tabs ─────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "📊 Market Intelligence",
    "🎯 Job Matcher & AI Optimizer",
    "📬 Başvuru Takip & E-posta Hub",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — MARKET INTELLIGENCE
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown('<div class="section-header">🔥 Top In-Demand Skills — Berlin Tech Market</div>',
                unsafe_allow_html=True)
    st.caption("Analyzes all scraped job descriptions to surface what the market is actually asking for.")

    descriptions = [j.get("description", "") for j in jobs if j.get("description")]

    if descriptions:
        with st.spinner("Analyzing job descriptions…"):
            skill_data = compute_skill_frequencies(descriptions, len(jobs))

        if skill_data:
            df_skills = pd.DataFrame(skill_data)

            # Plotly horizontal bar chart
            fig_skills = px.bar(
                df_skills,
                x="pct",
                y="skill",
                orientation="h",
                text=df_skills["pct"].apply(lambda x: f"{x}%"),
                color="pct",
                color_continuous_scale="Blues",
                labels={"pct": "% of Job Listings", "skill": "Skill / Technology"},
                title=f"Top {len(df_skills)} In-Demand Skills Across {len(jobs)} Job Listings",
            )
            fig_skills.update_traces(textposition="outside")
            fig_skills.update_layout(
                yaxis={"categoryorder": "total ascending"},
                coloraxis_showscale=False,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                height=520,
                margin=dict(l=20, r=60, t=50, b=20),
                font=dict(size=13),
            )
            fig_skills.update_xaxes(range=[0, max(df_skills["pct"]) * 1.2])
            st.plotly_chart(fig_skills, use_container_width=True)

        else:
            st.info("Not enough data yet. Run the scraper to populate job descriptions.")
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
        st.caption(f"ℹ️ Veritabanında **{len(company_counts)}** farklı şirket kayıtlıdır. Birden fazla pozisyon açan veya en aktif firmalar listelenmektedir.")

        # Quick company navigation buttons to link with Tab 2
        st.markdown("**🔗 Şirkete Göre Hızlı İncele (Job Matcher'da Aç):**")
        quick_cols = st.columns(min(len(top_companies), 5))
        for idx, (co_name, co_cnt) in enumerate(top_companies[:5]):
            with quick_cols[idx]:
                if st.button(f"🏢 {co_name} ({co_cnt})", key=f"tab1_link_co_{idx}", use_container_width=True):
                    st.session_state["filter_company"] = co_name
                    st.toast(f"🎯 '{co_name}' filtresi seçildi! Yukarıdan 'Job Matcher & AI Optimizer' sekmesine geçebilirsiniz.")
                    st.rerun()

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
# TAB 2 — JOB MATCHER & AI OPTIMIZER
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    cv = load_cv()

    if not jobs:
        st.info("📭 No jobs found yet. Run `python main.py` to scrape your first listings.")
        st.stop()

    if not cv:
        st.warning("⚠️ `data/master_cv.json` not found. Please fill in your CV profile first.")
        st.stop()

    # ── Job selector & Advanced Filters ────────────────────────────────────────
    st.markdown('<div class="section-header">📋 İlan Seçimi & Akıllı Filtreler</div>',
                unsafe_allow_html=True)

    # 1. Company choices & Cross-tab link support
    all_companies = ["Tümü"] + sorted(list({j.get("company", "") for j in jobs if j.get("company")}))
    current_co_session = st.session_state.get("filter_company", "Tümü")
    if current_co_session not in all_companies:
        current_co_session = "Tümü"
        st.session_state["filter_company"] = "Tümü"

    co_idx = all_companies.index(current_co_session)

    # 2. Categories
    all_categories = ["Tümü"] + sorted(list({j.get("category", "") for j in jobs if j.get("category")}))

    # ── Filter Row 1: Core Search, Company, Category & Sort ───────────────────
    col_f1, col_f2, col_f3, col_f4 = st.columns([1.5, 1.2, 1.1, 1.2])
    with col_f1:
        search_kw = st.text_input(
            "🔍 İlan / Anahtar Kelime Ara:",
            value=st.session_state.get("matcher_search_kw", ""),
            placeholder="örn. Python, AI, Computer Vision, SAP, Bain...",
            key="matcher_search_kw",
        ).strip().lower()

    with col_f2:
        sel_company = st.selectbox(
            "🏢 Şirket:",
            all_companies,
            index=co_idx,
            key="matcher_sel_company",
        )
        if sel_company != st.session_state.get("filter_company"):
            st.session_state["filter_company"] = sel_company

    with col_f3:
        sel_cat = st.selectbox("📂 Kategori:", all_categories, index=0, key="matcher_sel_cat")

    with col_f4:
        sort_by = st.selectbox(
            "🕒 Sıralama Ölçütü:",
            [
                "🕒 En Yeni İlanlar",
                "⏳ En Eski İlanlar",
                "⭐ En Yüksek Uyum Skoru",
                "📉 En Düşük Uyum Skoru",
            ],
            index=0,
            key="matcher_sort_by",
        )

    # ── Filter Row 2: Advanced Criteria (Language, Location, Role, Status, Min Score) ──
    with st.expander("🎛️ Gelişmiş Filtreler (Programlama Dili, Lokasyon, Pozisyon Türü, Min. Skor)", expanded=False):
        col_a1, col_a2, col_a3, col_a4 = st.columns([1.2, 1.2, 1.2, 1.3])

        LANG_OPTIONS = [
            "Tümü",
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
            sel_lang = st.selectbox("💻 Programlama Dili:", LANG_OPTIONS, index=0, key="matcher_sel_lang")

        with col_a2:
            sel_loc = st.selectbox(
                "📍 Lokasyon / Model:",
                [
                    "Tümü",
                    "🏢 Berlin (Onsite/Hybrid)",
                    "🌐 Remote (Germany-wide)",
                    "🔄 Hibrit / Remote İmkanı",
                ],
                index=0,
                key="matcher_sel_loc",
            )

        with col_a3:
            sel_role = st.selectbox(
                "🎓 Pozisyon Türü:",
                [
                    "Tümü",
                    "💼 Working Student (Werkstudent)",
                    "🔬 Internship (Praktikum / Thesis)",
                ],
                index=0,
                key="matcher_sel_role",
            )

        with col_a4:
            sel_status = st.selectbox(
                "📬 Başvuru Durumu:",
                [
                    "Tümü",
                    "🆕 Henüz İncelenmedi (New)",
                    "⏳ Kaydedilenler (Saved)",
                    "✅ Başvurulanlar (Applied/Interview)",
                ],
                index=0,
                key="matcher_sel_status",
            )

        col_slider, col_btn_reset = st.columns([3.5, 1])
        with col_slider:
            min_score = st.slider(
                "🎯 Minimum CV Uyum Skoru (%):",
                min_value=0,
                max_value=90,
                value=0,
                step=5,
                key="matcher_min_score",
            )
        with col_btn_reset:
            st.write("")
            st.write("")
            if st.button("🔄 Filtreleri Sıfırla", key="btn_clear_all_filters", use_container_width=True):
                st.session_state["filter_company"] = "Tümü"
                st.session_state["matcher_search_kw"] = ""
                st.session_state["matcher_sel_company"] = "Tümü"
                st.session_state["matcher_sel_cat"] = "Tümü"
                st.session_state["matcher_sel_lang"] = "Tümü"
                st.session_state["matcher_sel_loc"] = "Tümü"
                st.session_state["matcher_sel_role"] = "Tümü"
                st.session_state["matcher_sel_status"] = "Tümü"
                st.session_state["matcher_min_score"] = 0
                st.rerun()

    # ── Apply All Filters Sequentially ─────────────────────────────────────────
    filtered_jobs_list = list(jobs)

    # 1. Company filter
    if sel_company != "Tümü":
        filtered_jobs_list = [j for j in filtered_jobs_list if j.get("company") == sel_company]

    # 2. Category filter
    if sel_cat != "Tümü":
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
    if sel_lang != "Tümü":
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
    elif sel_loc == "🔄 Hibrit / Remote İmkanı":
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
    if sel_status == "🆕 Henüz İncelenmedi (New)":
        filtered_jobs_list = [j for j in filtered_jobs_list if j.get("status", "new") == "new"]
    elif sel_status == "⏳ Kaydedilenler (Saved)":
        filtered_jobs_list = [j for j in filtered_jobs_list if j.get("status") == "saved"]
    elif sel_status == "✅ Başvurulanlar (Applied/Interview)":
        filtered_jobs_list = [j for j in filtered_jobs_list if j.get("status") in ("applied", "interview", "assessment")]

    # 8. Minimum Match Score filter
    if min_score > 0:
        filtered_jobs_list = [j for j in filtered_jobs_list if j.get("match_score", 0) >= min_score]

    # ── Apply Sorting ──────────────────────────────────────────────────────────
    if sort_by == "🕒 En Yeni İlanlar":
        filtered_jobs_list.sort(key=lambda j: (j.get("posted_at") or j.get("fetched_at") or "", j.get("id", 0)), reverse=True)
    elif sort_by == "⏳ En Eski İlanlar":
        filtered_jobs_list.sort(key=lambda j: (j.get("posted_at") or j.get("fetched_at") or "", j.get("id", 0)), reverse=False)
    elif sort_by == "⭐ En Yüksek Uyum Skoru":
        filtered_jobs_list.sort(key=lambda j: j.get("match_score", 0), reverse=True)
    elif sort_by == "📉 En Düşük Uyum Skoru":
        filtered_jobs_list.sort(key=lambda j: j.get("match_score", 0), reverse=False)

    # ── Active Filter Summary & Counter ───────────────────────────────────────
    active_filters = []
    if sel_company != "Tümü":
        active_filters.append(f"🏢 **Şirket:** {sel_company}")
    if sel_cat != "Tümü":
        active_filters.append(f"📂 **Kategori:** {sel_cat}")
    if sel_lang != "Tümü":
        active_filters.append(f"💻 **Dil:** {sel_lang}")
    if sel_loc != "Tümü":
        active_filters.append(f"📍 **Lokasyon:** {sel_loc}")
    if sel_role != "Tümü":
        active_filters.append(f"🎓 **Tür:** {sel_role}")
    if sel_status != "Tümü":
        active_filters.append(f"📬 **Durum:** {sel_status}")
    if min_score > 0:
        active_filters.append(f"🎯 **Min Skor:** %{min_score}+")
    if search_kw:
        active_filters.append(f"🔍 **Kelime:** \"{search_kw}\"")

    if active_filters:
        badges_str = " &nbsp;|&nbsp; ".join(active_filters)
        st.markdown(f"<div style='background-color: #f1f5f9; border-radius: 6px; padding: 6px 12px; font-size: 13px; margin-bottom: 12px; color: #334155;'><b>Aktif Filtreler:</b> {badges_str} &nbsp;&nbsp; <b>({len(filtered_jobs_list)} / {len(jobs)} ilan)</b></div>", unsafe_allow_html=True)
    else:
        st.markdown(f"🎯 **Toplam {len(filtered_jobs_list)} uygun ilan listeleniyor** (İncelemek istediğin ilanı aşağıdan seçebilirsin):")

    if not filtered_jobs_list:
        st.warning("⚠️ Seçilen filtre kriterlerine uygun ilan bulunamadı. Filtreleri genişletmeyi veya temizlemeyi deneyebilirsiniz.")
        if st.button("🔄 Tüm Filtreleri Temizle", key="btn_no_results_reset"):
            st.session_state["filter_company"] = "Tümü"
            st.session_state["matcher_search_kw"] = ""
            st.session_state["matcher_sel_company"] = "Tümü"
            st.session_state["matcher_sel_cat"] = "Tümü"
            st.session_state["matcher_sel_lang"] = "Tümü"
            st.session_state["matcher_sel_loc"] = "Tümü"
            st.session_state["matcher_sel_role"] = "Tümü"
            st.session_state["matcher_sel_status"] = "Tümü"
            st.session_state["matcher_min_score"] = 0
            st.rerun()
        st.stop()

    # ── Master-Detail Layout: Left = Job List, Right = Selected Job Deep Dive ──
    if "selected_job_id" not in st.session_state or not any(j["id"] == st.session_state.selected_job_id for j in filtered_jobs_list):
        st.session_state.selected_job_id = filtered_jobs_list[0]["id"]

    selected_job = next((j for j in filtered_jobs_list if j["id"] == st.session_state.selected_job_id), filtered_jobs_list[0])

    col_job_list, col_job_detail = st.columns([1.15, 1.85], gap="medium")

    # ── Left Column: Scrollable Job Card List ──────────────────────────────────
    with col_job_list:
        st.markdown(f"##### 📋 Tüm İlanlar ({len(filtered_jobs_list)})")
        with st.container(height=780):
            for j in filtered_jobs_list:
                is_sel = (j["id"] == selected_job["id"])
                border_color = "#2563eb" if is_sel else "#e2e8f0"
                bg_color = "#eff6ff" if is_sel else "#ffffff"
                score = j.get("match_score", 0)
                badge_bg = "#10b981" if score >= 70 else ("#3b82f6" if score >= 50 else "#f59e0b")
                date_str = j.get("posted_at") or (j.get("fetched_at", "")[:10]) or "Yeni"
                
                st.markdown(f"""
                <div style="border: 2px solid {border_color}; background-color: {bg_color}; border-radius: 8px; padding: 10px 12px; margin-bottom: 4px;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
                        <span style="font-weight: 700; font-size: 13px; color: #0f172a; line-height: 1.3;">{j['title']}</span>
                        <span style="background-color: {badge_bg}; color: white; padding: 2px 7px; border-radius: 6px; font-weight: 700; font-size: 11px; white-space: nowrap;">%{score}</span>
                    </div>
                    <div style="font-size: 12px; color: #475569; margin-top: 4px;">🏢 <b>{j['company']}</b> &nbsp;·&nbsp; 📍 {j.get('location', 'Berlin')}</div>
                    <div style="font-size: 11px; color: #64748b; margin-top: 3px;">🏷️ {j.get('category', 'Tech')} &nbsp;·&nbsp; 📅 {date_str} &nbsp;·&nbsp; <b>{j.get('status', 'new').capitalize()}</b></div>
                </div>
                """, unsafe_allow_html=True)

                if st.button("👉 Seçili" if is_sel else "🔍 Bu İlanı İncele", key=f"btn_pick_{j['id']}", use_container_width=True, disabled=is_sel):
                    st.session_state.selected_job_id = j["id"]
                    st.rerun()

                st.markdown("<div style='margin-bottom: 8px;'></div>", unsafe_allow_html=True)

    # ── Right Column: Selected Job Details & AI Engine ────────────────────────
    with col_job_detail:
        st.markdown(f"### {selected_job['title']}")
        st.caption(f"🏢 **{selected_job['company']}** &nbsp;·&nbsp; 📍 {selected_job.get('location', 'Berlin')} &nbsp;·&nbsp; 🏷️ {selected_job.get('category', 'Tech')}")
        st.markdown(f"[🔗 İlan Sayfasına Git ({selected_job.get('source', 'Web')})]({selected_job.get('url', '#')})")

        # Status Actions
        st.markdown("**Hızlı Durum Güncelle:**")
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            if st.button("✅ Başvurdum", key=f"btn_app_{selected_job['id']}", use_container_width=True):
                db.update_status(selected_job["id"], "applied")
                st.cache_data.clear()
                st.rerun()
        with col_s2:
            if st.button("⏳ Kaydet", key=f"btn_sav_{selected_job['id']}", use_container_width=True):
                db.update_status(selected_job["id"], "saved")
                st.cache_data.clear()
                st.rerun()
        with col_s3:
            if st.button("❌ Atla", key=f"btn_skp_{selected_job['id']}", use_container_width=True):
                db.update_status(selected_job["id"], "skipped")
                st.cache_data.clear()
                st.rerun()

        # Job details expander
        with st.expander("📄 İlan Açıklamasını Görüntüle", expanded=False):
            if selected_job.get("description"):
                st.text_area("İlan Metni", selected_job["description"][:3000], height=220, disabled=True)

        st.markdown('<div class="section-header">⚡ Skill Gap & Eşleşme Analizi</div>', unsafe_allow_html=True)

        from src.match_analyzer import analyze_match

        with st.spinner("Analyzing match…"):
            result = analyze_match(
                job_title=selected_job.get("title", ""),
                job_description=selected_job.get("description", ""),
                cv=cv,
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
            st.markdown(f"**{len(result.all_job_keywords)}** anahtar kelime tespit edildi")
            st.markdown(f"✅ **{len(result.found_skills)}** CV'nde mevcut &nbsp;·&nbsp; "
                        f"❌ **{len(result.missing_skills)}** eksik / öne çıkmayan")
            st.markdown("")

            # Found skills — green tags
            if result.found_skills:
                st.markdown("✅ **CV'ndeki Güçlü Yönler:**")
                tags_html = " ".join(
                    f'<span class="skill-tag-green">{s.title()}</span>'
                    for s in result.found_skills
                )
                st.markdown(tags_html, unsafe_allow_html=True)

            st.markdown("")

            # Missing skills — red tags
            if result.missing_skills:
                st.markdown("❌ **İlanın İstediği Eksik Beceriler:**")
                tags_html = " ".join(
                    f'<span class="skill-tag-red">{s.title()}</span>'
                    for s in result.missing_skills
                )
                st.markdown(tags_html, unsafe_allow_html=True)
            else:
                st.success("🎉 Kritik bir beceri eksiği yok — güçlü eşleşme!")

        # ── AI Optimization Engine ─────────────────────────────────────────────────
        st.markdown('<div class="section-header">🚀 Gemini AI Optimizasyon Motoru</div>',
                    unsafe_allow_html=True)

        col_btn1, col_btn2, col_btn3 = st.columns([1.8, 1.8, 1.4])

        # ── Button 1: Optimize CV ─────────────────────────────────────────────────
        with col_btn1:
            optimize_clicked = st.button(
                "🚀 CV'yi Bu İlana Göre Optimize Et",
                use_container_width=True,
                type="primary",
                help="Gemini eksik becerileri geçmiş projelerine dürüstçe entegre eder ve ATS skorunu artırır",
            )

        # ── Button 2: Generate Cover Letter ──────────────────────────────────────
        with col_btn2:
            cover_clicked = st.button(
                "📝 Özel Ön Yazı (Cover Letter) Üret",
                use_container_width=True,
                help="Gemini bu ilana ve CV'ne özel profesyonel bir ön yazı hazırlar",
            )

        # ── Button 3: Download Base CV ───────────────────────────────────────────
        with col_btn3:
            try:
                from src.ai_assistant import generate_cv_pdf
                base_pdf_bytes = generate_cv_pdf(cv)
                candidate_name = cv.get("personal", {}).get("name", "Hazal_Tas")
                safe_cand = "".join(c for c in candidate_name if c.isalnum() or c in " _-").strip().replace(" ", "_") or "CV"
                st.download_button(
                    label="📄 Base CV İndir (.pdf)",
                    data=base_pdf_bytes,
                    file_name=f"{safe_cand}_Base_CV.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    help="Aktif profilin orijinal CV'sini ATS uyumlu PDF formatında indirir",
                )
            except Exception:
                pass

        # ── Optimize CV Result & Interactive Refiner ─────────────────────────────
        if optimize_clicked:
            if not os.getenv("GEMINI_API_KEY"):
                st.error("❌ GEMINI_API_KEY ayarlanmamış. .env dosyanızı kontrol edin.")
            else:
                with st.spinner("🧠 Gemini CV maddelerini optimize ediyor… (15–25 saniye)"):
                    try:
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
                        )

                        # Build tailored full CV & store into working session state
                        tailored_cv = build_tailored_cv_data(opt, cv, company=selected_job.get("company", ""))
                        st.session_state["tailored_cv_working"] = tailored_cv
                        st.session_state["tailored_cv_job_id"] = str(selected_job.get("id"))
                        st.session_state["cv_opt_meta"] = {
                            "original_score": result.score,
                            "estimated_new_score": opt.get("estimated_new_score", result.score),
                            "optimization_notes": opt.get("optimization_notes", ""),
                        }
                        st.session_state["cv_copilot_messages"] = [
                            {
                                "role": "assistant",
                                "content": (
                                    f"🎯 **{selected_job.get('company', '')}** ({selected_job.get('title', '')}) "
                                    f"pozisyonu için CV'nizi başarıyla optimize ettim!\n\n"
                                    f"Tahmini ATS skorunuz **%{result.score} → %{opt.get('estimated_new_score', result.score)}** seviyesine yükseltildi.\n\n"
                                    f"• İstediğiniz maddeyi aşağıdaki kutulardan doğrudan düzenleyebilirsiniz.\n"
                                    f"• ⚡ **Teknik**, ✂️ **Kısalt** veya 🔁 **Alternatif** butonlarıyla tek tıkla mikro-iyileştirme yapabilirsiniz.\n"
                                    f"• Ya da aşağıdaki CV Copilot sohbet kutusuna doğrudan talimat verebilirsiniz (*'Twilio projesini çıkar'*, *'Docker deneyimini öne çıkar'* gibi)."
                                ),
                            }
                        ]
                        st.rerun()

                    except json.JSONDecodeError as exc:
                        st.error(f"⚠️ Gemini beklenmeyen format döndü: {exc}. Lütfen tekrar deneyin.")
                    except Exception as exc:
                        st.error(f"⚠️ Optimizasyon başarısız: {exc}")

        # If we have an active tailored CV for the currently selected job, render the interactive refiner
        current_job_id_str = str(selected_job.get("id"))
        if st.session_state.get("tailored_cv_working") and st.session_state.get("tailored_cv_job_id") == current_job_id_str:
            tailored_cv = st.session_state["tailored_cv_working"]
            opt_meta = st.session_state.get("cv_opt_meta", {})
            orig_score = opt_meta.get("original_score", result.score)
            new_score = opt_meta.get("estimated_new_score", result.score)
            delta = new_score - orig_score

            st.markdown("---")
            st.markdown("### ✨ İlana Özel Optimize Edilmiş CV & İnteraktif Düzenleyici")

            col_g1, col_g2, col_note = st.columns([1, 1, 2])
            with col_g1:
                st.metric("Önceki Skor", f"{orig_score}%")
            with col_g2:
                st.metric("Optimize Skor", f"{new_score}%", delta=f"+{delta}%" if delta >= 0 else f"{delta}%")
            with col_note:
                note = opt_meta.get("optimization_notes", "")
                if note:
                    st.info(f"💡 {note}")

            from src.ai_assistant import generate_cv_pdf, generate_cv_docx

            # Candidate & company name for filenames
            candidate_name = tailored_cv.get("personal", {}).get("name", "Candidate")
            safe_candidate = "".join(c for c in candidate_name if c.isalnum() or c in " _-").strip().replace(" ", "_") or "Candidate"
            raw_co = selected_job.get("company", "job")
            safe_co = "".join(c for c in raw_co if c.isalnum() or c in " _-").strip().replace(" ", "_") or "job"

            # Always dynamically generate bytes from live working state
            pdf_bytes = generate_cv_pdf(tailored_cv)

            col_dl_pdf, col_dl_space = st.columns([2, 3])
            with col_dl_pdf:
                st.download_button(
                    label="📥 Canlı CV'yi İndir (.pdf)",
                    data=pdf_bytes,
                    file_name=f"{safe_candidate}_CV_{safe_co}.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True,
                    help="Yapılan tüm düzenlemeleri ve revizyonları içeren güncel CV'yi PDF olarak indirir",
                )

            # Editable summary in collapsed expander
            with st.expander("📝 İlana Özel Profesyonel Özet (Summary)", expanded=False):
                current_summary = tailored_cv.get("summary", "")
                edited_summary = st.text_area(
                    "Özet Metni (doğrudan düzenleyebilirsiniz):",
                    value=current_summary,
                    height=90,
                    key=f"working_summary_{selected_job.get('id')}",
                )
                if edited_summary != current_summary:
                    tailored_cv["summary"] = edited_summary

            job_ctx = f"Job: {selected_job.get('title')} at {selected_job.get('company')}. Requirements: {selected_job.get('description', '')[:500]}"

            # Experience section in collapsed expander
            if tailored_cv.get("experience"):
                with st.expander("💼 Deneyim Maddeleri & Mikro-İyileştirmeler", expanded=False):
                    st.caption("Her maddeyi doğrudan metin kutusundan değiştirebilir veya altındaki yapay zeka butonlarıyla tek tıkla dönüştürebilirsiniz:")
                    for exp_idx, exp in enumerate(tailored_cv.get("experience", [])):
                        role_label = exp.get("role", "")
                        company_label = exp.get("company", "")
                        st.markdown(f"**💼 {role_label} — {company_label}**")
                        new_bullets = list(exp.get("bullets", []))
                        for b_idx, bullet in enumerate(new_bullets):
                            edited_bullet = st.text_area(
                                f"Exp Bullet {exp_idx}_{b_idx}",
                                value=bullet,
                                height=68,
                                key=f"input_exp_{selected_job.get('id')}_{exp_idx}_{b_idx}",
                                label_visibility="collapsed",
                            )
                            if edited_bullet != bullet:
                                new_bullets[b_idx] = edited_bullet
                                tailored_cv["experience"][exp_idx]["bullets"] = new_bullets

                            col_m1, col_m2, col_m3, col_pad = st.columns([1.5, 1.5, 1.8, 3.2])
                            with col_m1:
                                if st.button("⚡ Daha Teknik", key=f"btn_tech_exp_{exp_idx}_{b_idx}", use_container_width=True, help="Metrik ve teknik araçlarla derinleştir"):
                                    with st.spinner("⚡ Teknik revizyon yapılıyor..."):
                                        from src.ai_assistant import refine_cv_bullet
                                        refined = refine_cv_bullet(bullet, "technical", job_ctx)
                                        new_bullets[b_idx] = refined
                                        tailored_cv["experience"][exp_idx]["bullets"] = new_bullets
                                        st.rerun()
                            with col_m2:
                                if st.button("✂️ Kısalt", key=f"btn_short_exp_{exp_idx}_{b_idx}", use_container_width=True, help="Daha vurucu ve kısa yap"):
                                    with st.spinner("✂️ Kısaltılıyor..."):
                                        from src.ai_assistant import refine_cv_bullet
                                        refined = refine_cv_bullet(bullet, "shorten", job_ctx)
                                        new_bullets[b_idx] = refined
                                        tailored_cv["experience"][exp_idx]["bullets"] = new_bullets
                                        st.rerun()
                            with col_m3:
                                if st.button("🔁 Alternatif", key=f"btn_alt_exp_{exp_idx}_{b_idx}", use_container_width=True, help="Farklı bir bakış açısıyla yeniden yaz"):
                                    with st.spinner("🔁 Alternatif üretiliyor..."):
                                        from src.ai_assistant import refine_cv_bullet
                                        refined = refine_cv_bullet(bullet, "alternative", job_ctx)
                                        new_bullets[b_idx] = refined
                                        tailored_cv["experience"][exp_idx]["bullets"] = new_bullets
                                        st.rerun()
                            st.write("")

            # Projects section in collapsed expander
            if tailored_cv.get("projects"):
                with st.expander("🔬 Proje Maddeleri & Mikro-İyileştirmeler", expanded=False):
                    for p_idx, proj in enumerate(tailored_cv.get("projects", [])):
                        proj_name = proj.get("name", "")
                        st.markdown(f"**🔬 {proj_name}**")
                        new_p_bullets = list(proj.get("bullets", []))
                        for b_idx, bullet in enumerate(new_p_bullets):
                            edited_bullet = st.text_area(
                                f"Proj Bullet {p_idx}_{b_idx}",
                                value=bullet,
                                height=68,
                                key=f"input_proj_{selected_job.get('id')}_{p_idx}_{b_idx}",
                                label_visibility="collapsed",
                            )
                            if edited_bullet != bullet:
                                new_p_bullets[b_idx] = edited_bullet
                                tailored_cv["projects"][p_idx]["bullets"] = new_p_bullets

                            col_m1, col_m2, col_m3, col_pad = st.columns([1.5, 1.5, 1.8, 3.2])
                            with col_m1:
                                if st.button("⚡ Daha Teknik", key=f"btn_tech_proj_{p_idx}_{b_idx}", use_container_width=True, help="Metrik ve teknik araçlarla derinleştir"):
                                    with st.spinner("⚡ Teknik revizyon yapılıyor..."):
                                        from src.ai_assistant import refine_cv_bullet
                                        refined = refine_cv_bullet(bullet, "technical", job_ctx)
                                        new_p_bullets[b_idx] = refined
                                        tailored_cv["projects"][p_idx]["bullets"] = new_p_bullets
                                        st.rerun()
                            with col_m2:
                                if st.button("✂️ Kısalt", key=f"btn_short_proj_{p_idx}_{b_idx}", use_container_width=True, help="Daha vurucu ve kısa yap"):
                                    with st.spinner("✂️ Kısaltılıyor..."):
                                        from src.ai_assistant import refine_cv_bullet
                                        refined = refine_cv_bullet(bullet, "shorten", job_ctx)
                                        new_p_bullets[b_idx] = refined
                                        tailored_cv["projects"][p_idx]["bullets"] = new_p_bullets
                                        st.rerun()
                            with col_m3:
                                if st.button("🔁 Alternatif", key=f"btn_alt_proj_{p_idx}_{b_idx}", use_container_width=True, help="Farklı bir bakış açısıyla yeniden yaz"):
                                    with st.spinner("🔁 Alternatif üretiliyor..."):
                                        from src.ai_assistant import refine_cv_bullet
                                        refined = refine_cv_bullet(bullet, "alternative", job_ctx)
                                        new_p_bullets[b_idx] = refined
                                        tailored_cv["projects"][p_idx]["bullets"] = new_p_bullets
                                        st.rerun()
                            st.write("")

            # Conversational CV Copilot
            st.markdown("---")
            st.markdown("#### 💬 CV Copilot — Doğal Dille Düzenleme Asistanı")
            st.caption("CV üzerinde istediğiniz her türlü değişikliği serbestçe söyleyin (örn: *'Fotoğraf projesindeki Twilio kısmını çıkar, Docker ve Kubernetes deneyimini vurgula'*).")

            chat_history = st.session_state.get("cv_copilot_messages", [])
            for msg in chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            # Quick download button right below chat
            st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
            col_chat_dl1, col_chat_pad = st.columns([2, 3])
            with col_chat_dl1:
                st.download_button(
                    label="📥 Güncel CV İndir (.pdf)",
                    data=pdf_bytes,
                    file_name=f"{safe_candidate}_CV_{safe_co}.pdf",
                    mime="application/pdf",
                    type="primary",
                    key=f"chat_dl_pdf_{selected_job.get('id')}",
                    use_container_width=True,
                    help="Copilot ile yapılan tüm düzenlemeleri içeren güncel CV'yi PDF olarak indirir",
                )

            if copilot_prompt := st.chat_input("CV'nizde neyi değiştirmek istersiniz?"):
                chat_history.append({"role": "user", "content": copilot_prompt})
                st.session_state["cv_copilot_messages"] = chat_history

                with st.spinner("🤖 Copilot CV'nizi güncelliyor…"):
                    try:
                        from src.ai_assistant import chat_refine_cv
                        updated_cv, explanation = chat_refine_cv(
                            current_cv=tailored_cv,
                            user_prompt=copilot_prompt,
                            chat_history=chat_history[:-1],
                            job_title=selected_job.get("title", ""),
                            company=selected_job.get("company", ""),
                            description=selected_job.get("description", ""),
                        )
                        st.session_state["tailored_cv_working"] = updated_cv
                        chat_history.append({"role": "assistant", "content": explanation})
                        st.session_state["cv_copilot_messages"] = chat_history
                        st.rerun()
                    except Exception as chat_err:
                        st.error(f"⚠️ Copilot düzenleme hatası: {chat_err}")

        # ── Cover Letter Result ───────────────────────────────────────────────────
        if cover_clicked:
            if not os.getenv("GEMINI_API_KEY"):
                st.error("❌ GEMINI_API_KEY ayarlanmamış. .env dosyanızı kontrol edin.")
            else:
                with st.spinner("✍️ Gemini ön yazınızı yazıyor… (10–20 saniye)"):
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

                        cover_letter = generate_cover_letter(job_obj)

                        st.markdown("#### 📝 Özel Hazırlanan Ön Yazı (Cover Letter)")
                        st.caption("Kopyalamadan önce doğrudan aşağıdaki kutuda düzenleyebilirsiniz:")

                        edited = st.text_area(
                            label="Cover Letter (editable)",
                            value=cover_letter,
                            height=420,
                            label_visibility="collapsed",
                        )

                        from src.ai_assistant import (
                            generate_cover_letter_pdf,
                            generate_cover_letter_docx,
                        )

                        # Safe company name
                        raw_co = selected_job.get("company", "job")
                        safe_co = "".join(c for c in raw_co if c.isalnum() or c in " _-").strip().replace(" ", "_") or "job"
                        job_title_str = selected_job.get("title", "")

                        # Generate PDF and DOCX bytes using current/edited text
                        cl_pdf_bytes = generate_cover_letter_pdf(
                            text=edited,
                            job_title=job_title_str,
                            company=raw_co,
                            cv=cv,
                        )
                        cl_docx_bytes = generate_cover_letter_docx(
                            text=edited,
                            job_title=job_title_str,
                            company=raw_co,
                            cv=cv,
                        )

                        col_dl_cl_pdf, col_dl_cl_docx, col_dl_cl_txt = st.columns([1.5, 1.2, 1])
                        with col_dl_cl_pdf:
                            st.download_button(
                                label="📥 Ön Yazıyı İndir (.pdf)",
                                data=cl_pdf_bytes,
                                file_name=f"CoverLetter_{safe_co}.pdf",
                                mime="application/pdf",
                                type="primary",
                                use_container_width=True,
                                help="Özel tasarlanmış, profesyonel Cover Letter belgenizi PDF olarak indirir",
                            )
                        with col_dl_cl_docx:
                            st.download_button(
                                label="📄 Word İndir (.docx)",
                                data=cl_docx_bytes,
                                file_name=f"CoverLetter_{safe_co}.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                use_container_width=True,
                                help="Ön yazıyı Word belgesi olarak indirir",
                            )
                        with col_dl_cl_txt:
                            st.download_button(
                                label="📝 Metin İndir (.txt)",
                                data=edited,
                                file_name=f"CoverLetter_{safe_co}.txt",
                                mime="text/plain",
                                use_container_width=True,
                                help="Ön yazı metnini düz yazı (.txt) olarak indirir",
                            )

                        st.success("✅ Ön yazı hazır! İster yukarıdaki kutuda düzenleyip PDF/Word olarak indirin, ister metni kopyalayın.")

                    except Exception as exc:
                        st.error(f"⚠️ Ön yazı üretimi başarısız: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — BAŞVURU TAKİP & E-POSTA HUB (FOLLOW-UP & GMAIL SYNC)
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown('<div class="section-header">📬 Başvuru Takip & E-posta Takipçisi (Follow-up & CRM)</div>', unsafe_allow_html=True)
    st.caption("Başvurduğunuz pozisyonların durumlarını yönetin, 7 günü geçenlere otomatik follow-up maili oluşturun ve Gmail gelen kutunuzu yapay zeka ile takip edin.")

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
            aj["_display_date"] = raw_app_date or "Belirtilmemiş"

    fu_needed = [j for j in applied_jobs if j.get("status") == "applied" and j.get("_days_elapsed", 0) >= 7]
    pending_apps = [j for j in applied_jobs if j.get("status") == "applied" and j.get("_days_elapsed", 0) < 7]
    interview_apps = [j for j in applied_jobs if j.get("status") == "interview"]
    assessment_apps = [j for j in applied_jobs if j.get("status") == "assessment"]
    rejected_apps = [j for j in applied_jobs if j.get("status") == "rejected"]

    # Sub-tabs
    crm_tab1, crm_tab2 = st.tabs([
        f"🗓️ Başvuru Takip Listesi ({len(applied_jobs)})",
        "📧 Gmail Senkronizasyonu & Akıllı Analizör",
    ])

    # ──────────────────────────────────────────────────────────────────────────
    # SUB-TAB 1: Başvuru Takip Listesi & Follow-Up Takvimi
    # ──────────────────────────────────────────────────────────────────────────
    with crm_tab1:
        crm_c1, crm_c2, crm_c3, crm_c4 = st.columns(4)
        crm_c1.metric("🔔 Follow-Up Zamanı", len(fu_needed), help="Başvurunun üzerinden 7 gün veya daha fazla geçenler")
        crm_c2.metric("⏳ Yanıt Beklenen", len(pending_apps))
        crm_c3.metric("🎉 Mülakat / Test", len(interview_apps) + len(assessment_apps))
        crm_c4.metric("📁 Toplam Takip Edilen", len(applied_jobs))

        st.write("")

        if not applied_jobs:
            st.info(
                "💡 **Henüz takip edilen aktif bir başvuru bulunmuyor.**\n\n"
                "1. **'🎯 Job Matcher & AI Optimizer'** sekmesine gidin.\n"
                "2. İncelediğiniz bir ilanın altında **'✅ Başvurdum'** butonuna tıklayın.\n"
                "3. İlan otomatik olarak buraya eklenir ve 7 günlük takip süreci başlar!"
            )
            # Quick demo helper to test the feature
            if st.button("🧪 Örnek Başvuru Ekle (Özelliği Test Etmek İçin)", key="btn_add_demo_app"):
                all_unapplied = [j for j in jobs if j.get("status") not in ("applied", "interview", "assessment", "rejected")]
                if all_unapplied:
                    demo_target = all_unapplied[0]
                    # Set applied date to 8 days ago
                    eight_days_ago = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()[:10]
                    db.update_status(demo_target["id"], "applied", applied_date=eight_days_ago)
                    st.cache_data.clear()
                    st.success(f"'{demo_target['company']} - {demo_target['title']}' başvurusu (8 gün önce yapılmış olarak) eklendi!")
                    st.rerun()
        else:
            filter_choice = st.radio(
                "Listeyi Filtrele:",
                [
                    f"Tümü ({len(applied_jobs)})",
                    f"🔔 Follow-up Zamanı (≥7 Gün) ({len(fu_needed)})",
                    f"⏳ Yanıt Bekleyenler ({len(pending_apps)})",
                    f"🎉 Mülakat & Test ({len(interview_apps) + len(assessment_apps)})",
                    f"❌ Reddedilenler ({len(rejected_apps)})",
                ],
                horizontal=True,
            )

            if "Follow-up Zamanı" in filter_choice:
                displayed_jobs = fu_needed
            elif "Yanıt Bekleyenler" in filter_choice:
                displayed_jobs = pending_apps
            elif "Mülakat & Test" in filter_choice:
                displayed_jobs = interview_apps + assessment_apps
            elif "Reddedilenler" in filter_choice:
                displayed_jobs = rejected_apps
            else:
                displayed_jobs = applied_jobs

            if not displayed_jobs:
                st.info("Bu filtreye uygun başvuru bulunamadı.")

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
                            badge_html = '<span class="badge-interview">🎉 MÜLAKAT AŞAMASINDA</span>'
                        elif status == "assessment":
                            badge_html = '<span class="badge-assessment">💻 TEST / ASSESSMENT</span>'
                        elif status == "rejected":
                            badge_html = '<span class="badge-rejected">❌ REDDEDİLDİ</span>'
                        elif days >= 7:
                            badge_html = f'<span class="badge-followup">🔔 FOLLOW-UP ZAMANI GELDİ ({days}. gün)</span>'
                        else:
                            badge_html = f'<span class="badge-applied">⏳ {days}. Gün — Yanıt Bekleniyor</span>'

                        st.markdown(f"### {job.get('company')} — {job.get('title')} &nbsp; {badge_html}", unsafe_allow_html=True)
                        st.caption(f"📅 **Başvuru Tarihi:** {job.get('_display_date')} &nbsp;|&nbsp; 📍 {job.get('location', 'Berlin')} &nbsp;|&nbsp; [🔗 İlan Sayfası]({job.get('url', '#')})")

                        if job.get("email_notes"):
                            st.info(f"📨 **Gelen E-posta Bildirimi:** {job['email_notes']}")

                    with col_actions:
                        st.markdown("**Durum Değiştir:**")
                        status_options = ["applied", "interview", "assessment", "rejected", "saved"]
                        status_labels = {
                            "applied": "✅ Başvuruldu (Yanıt Bekleniyor)",
                            "interview": "🎉 Mülakat Daveti Alındı",
                            "assessment": "💻 Kodlama Testi / Sınav",
                            "rejected": "❌ Olumsuz / Reddedildi",
                            "saved": "⏳ İleride Tekrar Bakılacak",
                        }
                        current_idx = status_options.index(status) if status in status_options else 0
                        new_status_val = st.selectbox(
                            "Durum Seç",
                            options=status_options,
                            format_func=lambda x: status_labels.get(x, x),
                            index=current_idx,
                            key=f"crm_stat_sel_{job_id}",
                            label_visibility="collapsed",
                        )
                        if new_status_val != status:
                            db.update_status(job_id, new_status_val)
                            st.cache_data.clear()
                            st.toast(f"{job.get('company')} durumu güncellendi: {status_labels.get(new_status_val)}")
                            st.rerun()

                        # Follow up action button
                        btn_label = "✉️ Follow-Up Maili Hazırla (Gemini)" if days >= 7 else "✉️ Follow-Up Maili Hazırla"
                        btn_type = "primary" if days >= 7 else "secondary"
                        if st.button(btn_label, key=f"crm_fu_btn_{job_id}", type=btn_type, use_container_width=True):
                            with st.spinner("✍️ Gemini profesyonel follow-up maili yazıyor..."):
                                try:
                                    from src.ai_assistant import generate_follow_up_email
                                    fu_text = generate_follow_up_email(
                                        job_title=job.get("title", ""),
                                        job_company=job.get("company", ""),
                                        applied_date=job.get("_display_date", ""),
                                        job_description=job.get("description", ""),
                                    )
                                    st.session_state[f"fu_draft_{job_id}"] = fu_text
                                except Exception as exc:
                                    st.error(f"Follow-up üretimi başarısız: {exc}")

                    # If draft exists in session state, show editor and actions
                    if f"fu_draft_{job_id}" in st.session_state:
                        st.markdown("##### ✉️ Hazırlanan Follow-Up E-posta Taslağı")
                        fu_edited = st.text_area(
                            label=f"Follow-Up Draft #{job_id}",
                            value=st.session_state[f"fu_draft_{job_id}"],
                            height=220,
                            key=f"fu_txt_{job_id}",
                            label_visibility="collapsed",
                        )

                        # Extract subject line if present
                        _cand_name = cv.get("personal", {}).get("name", "Hazal Taş") if "cv" in locals() and cv else "Hazal Taş"
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
                                label="📥 Mail Taslağını İndir (.txt)",
                                data=fu_edited,
                                file_name=f"FollowUp_{job.get('company','company')}.txt",
                                mime="text/plain",
                                key=f"dl_fu_{job_id}",
                                use_container_width=True,
                            )
                        with col_fu_mail:
                            mailto_url = f"mailto:?subject={quote(subject_line)}&body={quote(body_to_send)}"
                            st.markdown(
                                f'<a href="{mailto_url}" target="_blank" style="display:inline-block; width:100%; text-align:center; background:#2563eb; color:white; padding:8px 16px; border-radius:8px; text-decoration:none; font-weight:600;">🚀 E-posta İstemcinde Aç (Mailto)</a>',
                                unsafe_allow_html=True,
                            )

    # ──────────────────────────────────────────────────────────────────────────
    # SUB-TAB 2: Gmail Sync & E-posta Analizi
    # ──────────────────────────────────────────────────────────────────────────
    with crm_tab2:
        st.markdown("#### 📨 Gmail Gelen Kutusu Senkronizasyonu")
        st.caption("Gmail gelen kutunuzdaki iş başvurusu, mülakat daveti ve ret e-postalarını yapay zeka ile otomatik tespit edin.")

        gmail_user = os.getenv("GMAIL_USER")
        gmail_pass = os.getenv("GMAIL_APP_PASSWORD")

        col_g1, col_g2 = st.columns([3, 2])

        with col_g1:
            if gmail_user and gmail_pass:
                st.success(f"✅ **Gmail Entegrasyonu Aktif:** `{gmail_user}`")
                scan_days = st.slider("Geriye dönük kaç günlük e-postalar taransın?", min_value=3, max_value=30, value=14, step=1)
                if st.button("🔄 Gelen Kutusunu Şimdi Tara (Sync Gmail)", type="primary", use_container_width=True):
                    with st.spinner("Gmail taranıyor ve e-postalar Gemini ile analiz ediliyor..."):
                        try:
                            from src.email_tracker import sync_gmail
                            res = sync_gmail(days_back=scan_days)
                            if res.get("success"):
                                updates = res.get("updates", [])
                                st.success(f"Tarama tamamlandı! {res.get('processed', 0)} e-posta incelendi, {len(updates)} iş e-postası tespit edildi.")
                                if updates:
                                    for up in updates:
                                        with st.expander(f"📬 {up.get('company')} — {up.get('category')}", expanded=True):
                                            st.write(f"**Gönderen:** {up.get('sender')}")
                                            st.write(f"**Konu:** {up.get('subject')}")
                                            st.write(f"**Özet:** {up.get('summary')}")
                                            if up.get("db_updated"):
                                                st.success(f"✅ İlgili ilan ({up.get('matched_job')}) veritabanında otomatik güncellendi!")
                                            else:
                                                st.info("ℹ️ Veritabanında eşleşen ilan bulunamadı.")
                                    st.cache_data.clear()
                            else:
                                st.error(f"Gmail hatası: {res.get('error')}")
                        except Exception as exc:
                            st.error(f"Hata oluştu: {exc}")
            else:
                st.warning("⚠️ **Gmail Otomatik Senkronizasyonu Henüz Yapılandırılmamış**")
                st.markdown(
                    "Gmail hesabınızdaki mülakat davetlerini ve ret yanıtlarını otomatik taramak için "
                    "16 haneli **Google Uygulama Şifresi** (App Password) gereklidir.\n\n"
                    "*(Gmail bağlamasanız da aşağıdaki **Manuel Test & Analiz Simülatörü** ile tüm yapay zeka özelliklerini hemen kullanabilirsiniz!)*"
                )
                with st.expander("📌 2 Dakikada Nasıl Yapılandırılır? (Adım Adım)", expanded=False):
                    st.markdown("""
                    1. **Google Hesabım** → **Güvenlik** sayfasına gidin.
                    2. **2 Adımlı Doğrulama**'nın açık olduğundan emin olun.
                    3. [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) adresini açın.
                    4. Uygulama adı olarak **JobTracker** yazıp **Oluştur**'a tıklayın.
                    5. Size verilen 16 haneli şifreyi kopyalayın.
                    6. Proje ana dizinindeki `.env` dosyasına şu satırları ekleyin:
                    ```bash
                    GMAIL_USER=senin_mailin@gmail.com
                    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
                    ```
                    7. Kaydettikten sonra sayfayı yenilediğinizde otomatik tarama butonu aktif olacaktır!
                    """)

        with col_g2:
            st.info(
                "💡 **Gizlilik ve Güvenlik:**\n\n"
                "- E-postalarınız yalnızca yerel bilgisayarınızda (IMAP SSL üzerinden) taranır.\n"
                "- Yalnızca başvuru ve kariyer anahtar kelimeleri içeren e-postalar incelenir.\n"
                "- Kişisel e-postalarınız asla kaydedilmez."
            )

        st.divider()

        # ── Interactive Email Simulator / Manual Classifier ───────────────────
        st.markdown("#### 🧪 E-posta Analiz Simülatörü & Manuel Tarayıcı")
        st.caption("Gelen bir mülakat davetini veya ret mailini yapıştırın; Gemini anında sınıflandırsın ve veritabanındaki şirket durumunu güncellesin.")

        # Preset test templates
        col_t1, col_t2, col_t3 = st.columns(3)
        if "sim_sender" not in st.session_state:
            st.session_state["sim_sender"] = "recruiting@bain.com"
        if "sim_subject" not in st.session_state:
            st.session_state["sim_subject"] = "Invitation: First Round Interview - Working Student Data Analytics - Hazal Taş"
        if "sim_body" not in st.session_state:
            st.session_state["sim_body"] = "Dear Hazal,\n\nThank you for applying to the Working Student Data Analytics role at Bain & Company. We were very impressed with your background in AI and Data Analytics at Steinbeis University. We would like to invite you to a 45-minute technical interview next week.\n\nPlease use the link below to select a time slot that works best for you:\nhttps://calendly.com/bain-tech-interview/hazal\n\nBest regards,\nBain Talent Acquisition Team"

        with col_t1:
            if st.button("🎉 Örnek: Mülakat Daveti (Bain)", use_container_width=True):
                st.session_state["sim_sender"] = "recruiting@bain.com"
                st.session_state["sim_subject"] = "Invitation: First Round Interview - Working Student Data Analytics - Hazal Taş"
                st.session_state["sim_body"] = "Dear Hazal,\n\nThank you for applying to the Working Student Data Analytics role at Bain & Company. We were very impressed with your background in AI and Data Analytics at Steinbeis University. We would like to invite you to a 45-minute technical interview next week.\n\nPlease use the link below to select a time slot that works best for you:\nhttps://calendly.com/bain-tech-interview/hazal\n\nBest regards,\nBain Talent Acquisition Team"
                st.rerun()

        with col_t2:
            if st.button("❌ Örnek: Nazik Ret (Personio)", use_container_width=True):
                st.session_state["sim_sender"] = "no-reply@personio.de"
                st.session_state["sim_subject"] = "Update regarding your application for Junior Data Analyst at Personio"
                st.session_state["sim_body"] = "Dear Hazal,\n\nThank you very much for your interest in Personio and for taking the time to apply for the Junior Data Analyst position.\n\nWe received many applications from talented candidates, making our decision difficult. Unfortunately, we have decided not to move forward with your application for this role at this time.\n\nWe wish you all the best in your career search.\n\nSincerely,\nPersonio People Team"
                st.rerun()

        with col_t3:
            if st.button("💻 Örnek: Kodlama Testi (Delivery Hero)", use_container_width=True):
                st.session_state["sim_sender"] = "talent@deliveryhero.com"
                st.session_state["sim_subject"] = "Next Step: Technical Assessment for Software Working Student"
                st.session_state["sim_body"] = "Hi Hazal,\n\nThanks for applying to Delivery Hero! As the next step in our process, please complete the following 60-minute HackerRank coding challenge within the next 5 days:\nhttps://hackerrank.com/test/delivery-hero-hazal\n\nGood luck!\nDelivery Hero Engineering Recruitment"
                st.rerun()

        with st.form("email_simulator_form"):
            in_sender = st.text_input("Gönderen (From / Şirket):", value=st.session_state.get("sim_sender", ""))
            in_subject = st.text_input("E-posta Konusu (Subject):", value=st.session_state.get("sim_subject", ""))
            in_body = st.text_area("E-posta Metni (Body):", value=st.session_state.get("sim_body", ""), height=150)
            btn_analyze = st.form_submit_button("🧠 Gemini ile E-postayı Analiz Et & Durumu Güncelle", type="primary", use_container_width=True)

        if btn_analyze:
            if not in_body.strip():
                st.warning("Lütfen analiz edilecek bir e-posta metni girin.")
            elif not os.getenv("GEMINI_API_KEY"):
                st.error("GEMINI_API_KEY ayarlanmamış.")
            else:
                with st.spinner("🤖 Gemini e-postayı inceliyor, sınıflandırıyor ve şirket eşleşmesini kontrol ediyor..."):
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
                            "INTERVIEW": ("#dcfce7", "#15803d", "🎉 MÜLAKAT DAVETİ"),
                            "ASSESSMENT": ("#f3e8ff", "#7e22ce", "💻 KODLAMA / DEĞERLENDİRME TESTİ"),
                            "REJECTED": ("#fee2e2", "#b91c1c", "❌ RET BİLDİRİMİ"),
                            "RECEIVED": ("#e0f2fe", "#0369a1", "📩 BAŞVURU ALINDI ONAYI"),
                            "UNRELATED": ("#f1f5f9", "#475569", "⚪ BAŞVURU İLE İLGİSİZ"),
                        }
                        bg, fg, title_cat = cat_colors.get(category, ("#f1f5f9", "#475569", category))

                        st.markdown(
                            f"""
                            <div style="background:{bg}; color:{fg}; padding:14px; border-radius:10px; margin-top:10px;">
                                <h4 style="margin:0 0 6px 0;">{title_cat}</h4>
                                <b>Tespit Edilen Şirket:</b> {company or 'Bilinmiyor'} &nbsp;|&nbsp; <b>Pozisyon:</b> {res_sim.get('position') or 'Belirtilmemiş'}<br>
                                <b>Özet:</b> {summary}<br>
                                <b>Sıradaki Aksiyon:</b> {next_step or 'Yok'}
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
                                st.success(f"🎯 **Harika Eşleşme!** Veritabanındaki **{matched_job['company']} - {matched_job['title']}** ilanının durumu otomatik olarak **'{new_st.upper()}'** yapıldı!")
                            elif matched_job:
                                st.info(f"ℹ️ Veritabanında **{matched_job['company']}** bulundu ancak durum değişikliği gerektirmeyen kategori ({category}).")
                            else:
                                st.info(f"ℹ️ Veritabanında şu an '{company}' için aktif bir başvuru kaydı bulunamadı. Firma adını eşleştirmek için ilanı CRM'e ekleyebilirsiniz.")

                    except Exception as exc:
                        st.error(f"Analiz sırasında hata: {exc}")
