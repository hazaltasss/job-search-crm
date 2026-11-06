# 🤖 AGENTS.md — Developer & AI Agent Guidelines

Welcome to the **Job Search CRM & Career Intelligence Assistant** codebase. This guide provides essential context, architectural rules, and development practices for AI agents and human contributors working on this project.

---

## 🎯 Mission & Project Scope

The project is an autonomous job discovery, application optimization, and personal CRM platform built specifically for **Hazal Taş** (M.Sc. Data Analytics & AI student at Steinbeis University, Berlin; Computer Engineering B.Sc.).

### Core Criteria & Constraints:
1. **Job Types:** Working Student (*Werkstudent*) and Internship (*Praktikum*) roles only.
2. **Locations:** Berlin, Germany (onsite/hybrid) or Germany-wide Remote.
3. **Working Language:** **100% English working language.**
   - Strict filter: Exclude any listing requiring fluent or conversational German (`fließend Deutsch`, `command of German`, `Deutsch in Wort und Schrift`, etc.).
   - Allow exceptions: Positions that mention German enrollment criteria (e.g., "enrolled at a German university") or where German is purely optional / a "nice-to-have" ("German is a plus").
4. **Target Domains:** Data Analytics, Artificial Intelligence, Machine Learning, Python Backend, Software Engineering, and Business Tech.

---

## 🧱 Repository Architecture & File Directory

```
├── dashboard.py               # Streamlit UI: 3-tab CRM, Market Analytics, Job Matcher & Email Hub
├── main.py                    # Scraper orchestration root runner (calls scripts/run_pipeline.py)
├── requirements.txt           # Python dependencies
├── .env.example               # Template of required environment variables
├── .gitignore                 # Strict credential and artifact ignore rules
├── AGENTS.md                  # Development guidelines for AI agents
├── architecture.md            # Detailed system design & architecture documentation
├── README.md                  # User-facing setup & usage documentation
├── data/
│   ├── master_cv.json         # Hazal Taş master profile (experience, skills, education)
│   └── jobs.db                # SQLite database (auto-generated, gitignored)
├── scripts/
│   ├── __init__.py
│   ├── run_pipeline.py        # Primary fetch, filter, dedup & notify orchestration
│   ├── bot_server.py          # Long-polling Telegram bot listener for inline callbacks
│   ├── weekly_report.py       # Weekly analytics digest generator (Monday cron)
│   └── seed_demo_data.py      # Demo data generator for local UI testing
├── src/
│   ├── __init__.py
│   ├── config.py              # Configuration constants, keywords, regex patterns, paths
│   ├── models.py              # Dataclass models (`Job`)
│   ├── database.py            # SQLite schema, CRUD operations, auto-migration
│   ├── filters.py             # 3-stage location, language, and category filter pipeline
│   ├── match_analyzer.py      # Skill extraction, match scoring against master_cv.json
│   ├── ai_assistant.py        # Gemini API: Cover Letter, ATS CV Tailor, Follow-up Email
│   ├── email_tracker.py       # Gmail IMAP SSL client & Gemini email classifier
│   ├── analytics.py           # Skill aggregation & reporting helpers
│   ├── telegram_bot.py        # Telegram alert notifications & inline keyboard buttons
│   ├── sheets.py              # Google Sheets API live sync
│   └── fetchers/
│       ├── __init__.py
│       ├── arbeitnow.py       # Arbeitnow API client
│       ├── hiringcafe.py      # HiringCafe search API client (Cloudflare headers)
│       └── workingstudentjobs.py # WorkingStudentJobs.de scraper
└── .github/workflows/         # GitHub Actions cron workflows (09:00 & 18:00 CET)
```

---

## 🔑 Critical Rules & Technical Decisions

### 1. Gemini AI Model Selection
- **Active Model:** Primary is **`gemini-3.8-flash`** with automatic candidate fallback (`gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-flash-latest`).
  - `gemini-1.5-flash`, `gemini-2.0-flash`, and `gemini-2.5-flash` return `404 Not Found` (deprecated for new users).
  - Use `generate_content_with_fallback()` from `src.ai_assistant` for resilient API calls.
  - Initializing model in code:
    ```python
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-3.8-flash")
    ```

### 2. Strict German Filter Pipeline (`src/filters.py`)
- Any new fetcher or job ingestion flow **must** pass through `is_english_role(title, description, url)`.
- Rejection patterns check for:
  - `command of german`, `german alongside english`, `german is required`, `german skills (c1/b2)`.
  - German language text fragments: `deutsch in wort und schrift`, `sehr gute deutschkenntnisse`, `verhandlungssicher`.
- Permitted patterns (via `GERMAN_OPTIONAL_PATTERNS` in `src/config.py`):
  - `enrolled at a german university`, `state-recognized german university`, `german is a plus / advantage`.

### 3. Database Migration & Safety (`src/database.py`)
- Database file is located at `data/jobs.db`.
- Database initialization (`init_db()`) uses automatic non-destructive column additions:
  ```python
  # Safe migrations check PRAGMA table_info before adding columns
  ALTER TABLE jobs ADD COLUMN applied_at TEXT DEFAULT '';
  ALTER TABLE jobs ADD COLUMN email_notes TEXT DEFAULT '';
  ```
- Any status changes to `'applied'` automatically record `applied_at = YYYY-MM-DD`.

### 4. macOS Python & Environment Nuances
- On the host environment, Anaconda Python is installed at `/opt/anaconda3/bin/python`.
- Streamlit is typically launched with:
  ```bash
  /opt/anaconda3/bin/streamlit run dashboard.py
  ```
- When running commands requiring sandbox execution, commands should be executed cleanly or with appropriate pathing.

---

## 🛠️ Testing & Verification Standards

Before committing or completing any work, ensure:
1. **Syntax Check:**
   ```bash
   python3 -c "import ast; [ast.parse(open(f).read()) for f in ['dashboard.py', 'src/database.py', 'src/email_tracker.py', 'src/ai_assistant.py']]"
   ```
2. **Database Integrity:**
   Ensure `get_stats()`, `get_applied_jobs()`, and `find_job_by_company()` execute without SQLite locking or missing column errors.
3. **Streamlit UI:**
   Ensure Streamlit pages render without unhandled exceptions. If external secrets (`GEMINI_API_KEY`, `GMAIL_APP_PASSWORD`) are missing, fallback gracefully with informative alerts rather than crashing.

---

## 🔒 Security & Secrets Management
- **Never commit `.env` or any JSON service account keys.**
- The `.gitignore` is preconfigured to protect credentials.
- All email IMAP operations use SSL on port 993. Emails are processed in-memory and are never stored or logged outside the local SQLite database.
