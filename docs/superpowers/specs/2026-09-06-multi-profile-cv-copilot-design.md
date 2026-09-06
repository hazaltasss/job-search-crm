# 📋 Multi-Profile Management & Interactive CV Copilot Design Spec

**Date:** 2026-09-06  
**Status:** Approved by User  
**Author:** Antigravity & Hazal Taş  

---

## 1. Executive Summary

This specification expands the Job Discovery & Application CRM from a single-user tool into an extensible, multi-profile AI Career Platform with two core capabilities:
1. **Multi-Profile & AI CV Ingestion:** Allows any user (friends, colleagues, or new candidates) to upload their existing CV (PDF or Word DOCX) and automatically parse it into a structured profile using Gemini AI. Profiles are stored in SQLite and can be seamlessly switched from the UI.
2. **Interactive CV Refiner & Chatbot Copilot:** Enables candidate-directed refinement of AI-optimized CVs through a hybrid interface:
   - **Inline Text Editing:** Directly modify any bullet point or summary in text fields.
   - **One-Click Micro-Actions:** Instantly rephrase bullets (*⚡ Make More Technical*, *✂️ Shorten*, *🔁 Alternative Angle*).
   - **Natural Language CV Copilot:** Chat directly with the AI assistant to apply holistic or surgical modifications to the CV before downloading.
   - **Live PDF & DOCX Synchronization:** All edits immediately update the generated PDF and Word download files.

---

## 2. Architecture & Data Model

### 2.1 Database Schema (`data/jobs.db`)
A new table `profiles` is introduced:
```sql
CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,             -- Unique ID: 'default_hazal', 'prof_<uuid>'
    name TEXT NOT NULL,              -- Candidate full name
    headline TEXT DEFAULT '',        -- Headline / Target specialization
    data_json TEXT NOT NULL,         -- JSON payload matching master_cv.json schema
    is_active INTEGER DEFAULT 0,     -- 1 for currently active profile, 0 otherwise
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2.2 Default Profile Guarantee
- On startup, `init_db()` verifies if `default_hazal` exists.
- If missing, it populates `default_hazal` directly from `data/master_cv.json` and sets `is_active = 1`.
- Hazal Taş's base CV is protected and cannot be deleted.

### 2.3 Active Profile Lifecycle
- Global active profile is queried via `get_active_profile()`.
- The matching engine (`match_analyzer.py`), filters, and dashboard read `active_profile.data_json`.
- A profile selector dropdown in the sidebar allows switching between candidates in real-time.

---

## 3. Subsystem 1: AI CV Parser & Multi-Profile Management

### 3.1 Upload & Text Ingestion
- Supported formats: **PDF** (`.pdf`) and **Word** (`.docx`).
- Text extractors:
  - `.docx`: via `python-docx` reading paragraphs and tables.
  - `.pdf`: via `pypdf` reading raw text streams.

### 3.2 Gemini Structured Extraction
- A structured prompt (`_PARSE_CV_PROMPT`) passes the extracted text to Gemini Flash with `response_mime_type="application/json"`.
- Extraction schema:
  - `personal`: name, email, phone, location, links
  - `summary`: professional summary
  - `education`: list of degrees, institutions, locations, dates
  - `skills`: categorized technical and soft skills
  - `experience`: company, role, dates, bullets
  - `projects`: name, tech stack, bullets
- Robust parsing via `extract_json_from_text` ensures resilience against LLM formatting variations.

### 3.3 Profile Review & Persistence Flow
1. User uploads CV in sidebar or Profile modal.
2. System extracts and displays parsed sections for candidate review.
3. Candidate reviews/edits fields and clicks **"Save Profile"**.
4. Record is inserted into `profiles` and activated.

---

## 4. Subsystem 2: Interactive CV Refiner & Chatbot Copilot

### 4.1 State Management
- `st.session_state["tailored_cv_working"]`: Holds the active working copy of the optimized CV for the currently selected job.
- `st.session_state["cv_copilot_messages"]`: Holds the chat message history between the candidate and the CV Copilot for the current job session.

### 4.2 Interactive Layers

#### Layer 1: Inline Direct Editing
- Each section (Tailored Summary, Experience Bullets, Project Bullets) is rendered in an editable `st.text_area` or `st.text_input`.
- Hand-typed changes immediately update `st.session_state["tailored_cv_working"]`.

#### Layer 2: Micro-Action Buttons
Adjacent to each bullet point, 3 micro-actions are provided:
- **⚡ Daha Teknik Yap (More Technical):** Re-writes the specific bullet with deeper technical terminology and quantified impact.
- **✂️ Kısalt (Shorten):** Condenses verbose descriptions into a crisp, single-line ATS bullet.
- **🔁 Alternatif Üret (Alternative):** Re-frames the bullet from a different engineering angle.

#### Layer 3: Conversational CV Copilot
- Powered by `st.chat_input` and Gemini Flash.
- Prompt Context:
  - Job Title, Company, Full Job Description
  - Full current CV working state
  - Candidate instruction (e.g., *"Make project 1 more focused on SQL indexing and remove Twilio"*)
- Copilot Execution:
  - Returns updated CV JSON and an explanation of the change.
  - Updates `st.session_state["tailored_cv_working"]`.
  - Re-renders the UI with the updated bullets.

### 4.3 Live Document Generation
- The download buttons:
  - **📥 Optimize CV'yi İndir (.pdf)**
  - **📄 Word İndir (.docx)**
  - **📝 Maddeleri İndir (.txt)**
- Dynamically compile `st.session_state["tailored_cv_working"]` into PDF/DOCX on demand, ensuring that any direct edit, micro-action, or chatbot adjustment is instantly reflected in the downloaded files.

---

## 5. Verification & Testing Standards

1. **Unit & Syntax Tests:**
   - Parse sample PDF and DOCX files into valid JSON schemas.
   - Test micro-action prompt execution and JSON parsing.
   - Validate that `generate_cv_pdf` and `generate_cv_docx` correctly render modified working copies.
2. **Database Integrity:**
   - Verify `profiles` table schema migrations on existing `data/jobs.db`.
   - Test multi-profile switching, default profile retention, and active state persistence.
3. **End-to-End UI Testing:**
   - Upload new CV -> Verify auto-switch -> Check match score update.
   - Optimize CV -> Edit bullet -> Ask Copilot to adjust -> Download PDF -> Verify PDF contains the refined text.
