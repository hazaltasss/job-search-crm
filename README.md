# 🤖 Job Search CRM & Career Intelligence Assistant

An AI-powered job search automation platform, skill gap optimizer, and personal application CRM tailored for **Berlin Working Student (*Werkstudent*) & Internship (*Praktikum*)** tech roles.

Built with **Python**, **Streamlit**, **SQLite**, and **Google Gemini AI (`gemini-3.6-flash`)**.

---

## 🌟 Key Capabilities & Features

### 1. 🔍 Multi-Source Intelligent Scraper Suite
- **Arbeitnow API:** Remote & Berlin-based tech positions.
- **WorkingStudentJobs.de:** JSON-LD schema parsing + fallback scraper.
- **HiringCafe API:** High-efficiency tech search with rate-limit protection.
- **Strict English Language Filter:** Eliminates roles requiring fluent German (`command of German`, `Deutsch in Wort und Schrift`, etc.) while permitting legitimate English tech roles (e.g., German university enrollment).
- **Location Guard:** Filters strictly for Berlin (onsite/hybrid) or Germany-wide Remote.

### 2. 📊 Market Intelligence & Skill Gap Analytics
- **Live Tech Demand Bar Charts:** Analyzes all scraped job descriptions to surface the most in-demand frameworks, languages, and tools in Berlin.
- **Top Hiring Companies:** Leaderboard of companies with the most open student positions.
- **Interactive Match Scoring:** Calculates a real-time match percentage (0–100%) against your master profile (`data/master_cv.json`).
- **Visual Skill Badging:**
  - 🟢 **Matched Skills:** Skills present in your profile.
  - 🔴 **Missing Skills:** Critical skills requested by the employer that you should address.
  - 🔵 **General Market Skills:** Relevant domain competencies.

### 3. 🧠 Generative AI Career Tools (Gemini 3.6 Flash)
- **ATS CV Optimizer:** Rewrites experience and project bullet points to naturally incorporate missing job skills without exaggerating or falsifying background.
- **Customized Cover Letter Generator:** Crafts role-specific, 300-word cover letters highlighting your degree, thesis, and technical stack. Exports to `.docx` and editable plain text.
- **7-Day Follow-Up Email Writer:** Automatically detects when 7 days have elapsed since applying and generates a polite, professional follow-up email.
- **1-Click Mailto Handoff:** Opens your default desktop email client with the subject and body pre-filled.

### 4. 📬 Personal CRM & Gmail Application Tracker
- **Application Status Pipeline:** Tracks statuses across `Applied`, `Interview Scheduled`, `Coding Assessment`, `Rejected`, and `Saved`.
- **Gmail IMAP Sync:** Automatically scans incoming emails via secure IMAP SSL for interview invitations, coding tests, and status updates.
- **Gemini Email Classifier:** Accurately categorizes recruiter emails into `INTERVIEW`, `ASSESSMENT`, `REJECTED`, or `RECEIVED`, linking them back to the company in SQLite.
- **Interactive Email Simulator:** Test any recruiter email or test notification with pre-loaded samples (Bain, Personio, Delivery Hero) even without connecting a Gmail account.

### 5. 📲 Telegram Bot & Google Sheets Sync
- **Instant Telegram Alerts:** Delivers formatted alerts for new high-match jobs with 5 inline interactive buttons (`Applied`, `Skip`, `Save`, `Cover Letter`, `Tailor CV`).
- **Google Sheets CRM:** Automatically synchronizes application statuses in real-time.
- **Automated GitHub Actions:** Scheduled workflows run twice daily (09:00 & 18:00 CET).

---

## 📁 Repository Structure

```
├── dashboard.py               # Streamlit web UI (Market Intel, Job Matcher, CRM Hub)
├── main.py                    # Scraper orchestration & ingestion pipeline
├── bot_server.py              # Long-polling Telegram bot listener for inline callbacks
├── weekly_report.py           # Weekly analytics digest generator
├── seed_demo_data.py          # Demo data generator for local UI testing
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variable templates
├── .gitignore                 # Credential and artifact ignore rules
├── AGENTS.md                  # Development guidelines for AI agents
├── architecture.md            # Detailed system design & architecture documentation
├── data/
│   ├── master_cv.json         # Candidate master profile (Hazal Taş)
│   └── jobs.db                # SQLite database (auto-generated, gitignored)
└── src/
    ├── config.py              # Keywords, regexes, and environment settings
    ├── models.py              # Job dataclass model
    ├── database.py            # SQLite schema, CRUD operations & migrations
    ├── filters.py             # 3-stage location, language, and category filters
    ├── match_analyzer.py      # Skill gap and match score engine
    ├── ai_assistant.py        # Gemini cover letter, CV tailor & follow-up generator
    ├── email_tracker.py       # Gmail IMAP sync & Gemini email classifier
    ├── analytics.py           # Skill aggregation & reporting helpers
    ├── telegram_bot.py        # Telegram notification sender & button handlers
    ├── sheets.py              # Google Sheets API live sync
    └── fetchers/              # Scraper implementations
        ├── arbeitnow.py       # Arbeitnow API fetcher
        ├── hiringcafe.py      # HiringCafe search API fetcher
        └── workingstudentjobs.py # WorkingStudentJobs.de scraper
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+ (or Anaconda Python)
- A Google Gemini API Key ([Google AI Studio](https://aistudio.google.com/app/apikey))

### 2. Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/job-search-crm.git
cd job-search-crm

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Configure your `.env` variables:
```ini
# Core AI Engine (Required for CV tailoring, cover letters, and email classification)
GEMINI_API_KEY=AIzaSy...

# Gmail Integration (Optional — for automatic inbox scanning)
GMAIL_USER=your_email@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

# Telegram Notifications (Optional — for mobile push alerts)
TELEGRAM_BOT_TOKEN=7123456789:AAFxxxxxxxxxx
TELEGRAM_CHAT_ID=123456789

# Google Sheets CRM (Optional — for cloud spreadsheet sync)
GOOGLE_SHEET_ID=your_spreadsheet_id_here
GOOGLE_SERVICE_ACCOUNT_JSON=service_account.json
```

---

## 🖥️ Running the Application

### 1. Launch the Streamlit Dashboard
```bash
streamlit run dashboard.py
```
Open **`http://localhost:8501`** in your browser to access:
- **📊 Market Intelligence:** View top in-demand skills and hiring trends in Berlin.
- **🎯 Job Matcher & AI Optimizer:** Browse jobs, inspect skill gaps, optimize CV bullets, and generate cover letters.
- **📬 Başvuru Takip & E-posta Hub:** Monitor applications, generate 7-day follow-up emails, and sync/simulate recruiter emails.

### 2. Fetch Latest Jobs Manually
```bash
python main.py
```
Scrapes all configured sources, applies the strict English filter, deduplicates, and saves new listings to `data/jobs.db`.

### 3. Start the Telegram Bot Listener (Optional)
```bash
python bot_server.py
```
Runs the interactive Telegram bot to handle button clicks (`Applied`, `Cover Letter`, `Tailor CV`) directly from mobile alerts.

---

## 📬 Gmail App Password Setup (Optional)

To enable automatic inbox scanning for interview and rejection emails:
1. Ensure **2-Step Verification** is enabled on your Google Account.
2. Go to [Google App Passwords](https://myaccount.google.com/apppasswords).
3. Create an app password named **JobTracker**.
4. Copy the 16-character password into `.env`:
   ```ini
   GMAIL_USER=your_email@gmail.com
   GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
   ```
*(Note: You can also use the interactive **Email Simulator** inside Tab 3 without entering Gmail credentials!)*

---

## 🛡️ License & Disclaimers

MIT License — Built for personal career tracking and research. Please respect the Terms of Service and rate limits of each job platform when running scrapers.
