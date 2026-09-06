# Multi-Profile Management & Interactive CV Copilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the application into a multi-profile AI platform allowing candidates to upload their existing PDF/Word CVs, auto-parse them into SQLite profiles, switch active profiles dynamically, and interactively refine job-optimized CVs via inline text fields, one-click micro-actions, and an AI chat copilot.

**Architecture:** Extend SQLite database schema with a `profiles` table ensuring the default Hazal Taş profile is preserved; create `src/cv_parser.py` using `python-docx` and `pypdf` + Gemini Flash structured JSON extraction for CV onboarding; add bullet refinement micro-actions and conversational CV Copilot in `src/ai_assistant.py`; and upgrade `dashboard.py` with profile switching and a 3-layer interactive CV editor.

**Tech Stack:** Python 3.12/3.13, Streamlit, SQLite, Google Generative AI (Gemini 3.6 Flash), ReportLab, python-docx, pypdf.

**Spec:** `docs/superpowers/specs/2026-09-06-multi-profile-cv-copilot-design.md`

## Global Constraints
- Use Gemini model `gemini-3.6-flash` with `response_mime_type="application/json"` for structured tasks.
- Always preserve Hazal Taş's base CV under `default_hazal` and protect it from deletion.
- All PDF generations must use TrueType Unicode font (`Arial`) with fallback to ensure clean Turkish/German characters.
- Follow existing codebase patterns and verify with syntax checks and automated test runs after each task.

---

### Task 1: Database Profiles Model & Migration

**Files:**
- Modify: `src/database.py`
- Test: `tests/test_database_profiles.py`

**Interfaces:**
- Produces:
  - `ensure_default_profile(cv_data: dict) -> str`
  - `get_profiles() -> list[dict]`
  - `get_active_profile() -> dict`
  - `set_active_profile(profile_id: str) -> bool`
  - `save_profile(name: str, headline: str, data: dict, profile_id: str | None = None) -> str`
  - `delete_profile(profile_id: str) -> bool`

- [ ] **Step 1: Write failing test for profile operations**

```python
# tests/test_database_profiles.py
import pytest
from src.database import (
    init_db,
    ensure_default_profile,
    get_profiles,
    get_active_profile,
    set_active_profile,
    save_profile,
    delete_profile,
)

def test_profile_lifecycle():
    init_db()
    mock_cv = {
        "personal": {"name": "Hazal Taş", "email": "hazal@test.com"},
        "summary": "AI Student",
        "skills": {},
        "experience": [],
        "projects": [],
        "education": [],
    }
    def_id = ensure_default_profile(mock_cv)
    assert def_id == "default_hazal"
    
    active = get_active_profile()
    assert active is not None
    assert active["name"] == "Hazal Taş"
    
    new_cv = {"personal": {"name": "Ali Yılmaz"}, "summary": "Backend Dev"}
    new_id = save_profile("Ali Yılmaz", "Backend Developer", new_cv)
    assert new_id != "default_hazal"
    
    set_active_profile(new_id)
    active = get_active_profile()
    assert active["name"] == "Ali Yılmaz"
    
    # Cannot delete default
    assert delete_profile("default_hazal") is False
    # Can delete custom profile
    assert delete_profile(new_id) is True
```

- [ ] **Step 2: Run test to verify it fails**
Run: `/opt/anaconda3/bin/python -m pytest tests/test_database_profiles.py -v`
Expected: FAIL with missing functions or table error

- [ ] **Step 3: Implement profiles schema and CRUD in `src/database.py`**
In `src/database.py`:
- In `init_db()`, execute:
  ```sql
  CREATE TABLE IF NOT EXISTS profiles (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      headline TEXT DEFAULT '',
      data_json TEXT NOT NULL,
      is_active INTEGER DEFAULT 0,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  ```
- Implement `ensure_default_profile(cv_data: dict) -> str`:
  Checks if `default_hazal` exists. If not, inserts it with `is_active = 1`.
- Implement `get_profiles() -> list[dict]`: returns all profiles ordered by `is_active DESC, name ASC`.
- Implement `get_active_profile() -> dict`: returns active profile dict with parsed `data_json`. If none active, activates default.
- Implement `set_active_profile(profile_id: str) -> bool`: sets `is_active = 0` for all, then `is_active = 1` for `profile_id`.
- Implement `save_profile(name: str, headline: str, data: dict, profile_id: str | None = None) -> str`: inserts or updates.
- Implement `delete_profile(profile_id: str) -> bool`: returns `False` if `profile_id == 'default_hazal'`, else deletes and re-activates default if needed.

- [ ] **Step 4: Run test to verify it passes**
Run: `/opt/anaconda3/bin/python -m pytest tests/test_database_profiles.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add src/database.py tests/test_database_profiles.py
git commit -m "feat(database): add multi-profile table and CRUD operations"
```

---

### Task 2: AI CV Parser Engine (`src/cv_parser.py`)

**Files:**
- Create: `src/cv_parser.py`
- Test: `tests/test_cv_parser.py`

**Interfaces:**
- Consumes:
  - `pypdf`, `python-docx`
  - `src.ai_assistant.extract_json_from_text`
  - `google.generativeai`
- Produces:
  - `extract_text_from_upload(file_bytes: bytes, filename: str) -> str`
  - `parse_cv_with_gemini(raw_text: str) -> dict`

- [ ] **Step 1: Ensure `pypdf` dependency is installed**
Run: `/opt/anaconda3/bin/pip install pypdf`
Add `pypdf>=4.0.0` to `requirements.txt`.

- [ ] **Step 2: Write test for text extraction and schema validation**
```python
# tests/test_cv_parser.py
from src.cv_parser import extract_text_from_upload, normalize_parsed_cv

def test_extract_text_docx():
    import io
    from docx import Document
    doc = Document()
    doc.add_paragraph("Hazal Taş\nSoftware Engineer")
    buf = io.BytesIO()
    doc.save(buf)
    text = extract_text_from_upload(buf.getvalue(), "sample.docx")
    assert "Hazal Taş" in text
    assert "Software Engineer" in text

def test_normalize_parsed_cv():
    raw_dict = {
        "personal": {"name": "Test User"},
        "summary": "Summary test",
        "education": [{"degree": "B.Sc."}],
    }
    normalized = normalize_parsed_cv(raw_dict)
    assert "personal" in normalized
    assert "experience" in normalized
    assert "projects" in normalized
    assert "skills" in normalized
```

- [ ] **Step 3: Implement `src/cv_parser.py`**
- `extract_text_from_upload(file_bytes: bytes, filename: str) -> str`:
  - If `.docx`: extract via `docx.Document(io.BytesIO(file_bytes))` paragraphs and tables.
  - If `.pdf`: extract via `pypdf.PdfReader(io.BytesIO(file_bytes))`.
- `parse_cv_with_gemini(raw_text: str) -> dict`:
  - Passes extracted text to Gemini Flash with `_PARSE_CV_PROMPT`.
  - Enforces `response_mime_type="application/json"`.
  - Calls `extract_json_from_text(response.text)` and `normalize_parsed_cv(parsed)`.

- [ ] **Step 4: Run test to verify it passes**
Run: `/opt/anaconda3/bin/python -m pytest tests/test_cv_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add requirements.txt src/cv_parser.py tests/test_cv_parser.py
git commit -m "feat(parser): add AI CV text extraction and Gemini parser"
```

---

### Task 3: Interactive CV Refiner Micro-Actions & Conversational Copilot

**Files:**
- Modify: `src/ai_assistant.py`
- Test: `tests/test_cv_copilot.py`

**Interfaces:**
- Produces:
  - `refine_cv_bullet(bullet: str, action: str, job_context: str) -> str`
  - `chat_refine_cv(current_cv: dict, user_prompt: str, chat_history: list[dict], job_title: str, company: str, description: str) -> tuple[dict, str]`

- [ ] **Step 1: Write test for bullet micro-action and copilot chat logic**
```python
# tests/test_cv_copilot.py
from src.ai_assistant import refine_cv_bullet, build_copilot_prompt

def test_build_copilot_prompt():
    cv = {"personal": {"name": "Hazal"}, "experience": []}
    prompt = build_copilot_prompt(
        current_cv=cv,
        user_prompt="Make it shorter",
        chat_history=[],
        job_title="Data Analyst",
        company="Acme",
        description="SQL required",
    )
    assert "Hazal" in prompt
    assert "Data Analyst" in prompt
    assert "Make it shorter" in prompt
```

- [ ] **Step 2: Run test to verify it fails**
Run: `/opt/anaconda3/bin/python -m pytest tests/test_cv_copilot.py -v`
Expected: FAIL

- [ ] **Step 3: Implement micro-actions and conversational copilot in `src/ai_assistant.py`**
- `refine_cv_bullet(bullet: str, action: str, job_context: str) -> str`:
  - Actions: `'technical'` (adds quantified engineering depth), `'shorten'` (crisp concise ATS bullet), `'alternative'` (re-angles accomplishment).
  - Calls Gemini Flash with low temperature (0.2) and returns the refined single bullet string.
- `chat_refine_cv(current_cv: dict, user_prompt: str, chat_history: list[dict], job_title: str, company: str, description: str) -> tuple[dict, str]`:
  - Instructs Gemini to act as an expert CV editor.
  - Takes candidate request, modifies specific parts of `current_cv` accurately while preserving factual truth.
  - Returns `(updated_cv_dict, explanation_message)`.

- [ ] **Step 4: Run test to verify it passes**
Run: `/opt/anaconda3/bin/python -m pytest tests/test_cv_copilot.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add src/ai_assistant.py tests/test_cv_copilot.py
git commit -m "feat(ai): add CV bullet micro-actions and conversational copilot engine"
```

---

### Task 4: Dashboard Integration — Multi-Profile Switcher & Onboarding UI

**Files:**
- Modify: `dashboard.py`

**Interfaces:**
- Consumes:
  - `src.database`: `get_profiles`, `get_active_profile`, `set_active_profile`, `save_profile`, `delete_profile`
  - `src.cv_parser`: `extract_text_from_upload`, `parse_cv_with_gemini`

- [ ] **Step 1: Integrate Sidebar Profile Switcher**
- In `dashboard.py` sidebar:
  - Display active profile card (Avatar/Icon, Name, Headline).
  - Add `st.selectbox` with all available profiles. On change, call `set_active_profile()` and trigger `st.rerun()`.
  - Add an expander: **"➕ Yeni Profil Ekle (CV Yükle)"**.

- [ ] **Step 2: Integrate Drag & Drop CV Upload with Gemini Parsing**
- Inside the expander:
  - `uploaded_file = st.file_uploader("PDF veya Word (.docx) CV Yükle", type=["pdf", "docx"])`
  - Button: **"🚀 CV'yi Otomatik Ayrıştır ve Profil Oluştur"**
  - Spinner: *"Gemini CV'nizi analiz ediyor…"*.
  - Calls `extract_text_from_upload` and `parse_cv_with_gemini`.
  - Shows preview modal/fields (Ad, Özet, Beceriler, Deneyim Sayısı) with **"✅ Profili Kaydet ve Aktif Et"** button.
  - On save: inserts to database, sets as active, reruns dashboard.

- [ ] **Step 3: Connect Active Profile to Matching & Optimization**
- Replace hardcoded `cv = _load_cv()` calls in `dashboard.py` with `cv = get_active_profile()["data_json"]`.

- [ ] **Step 4: Verify syntax & run dashboard locally**
Run: `/opt/anaconda3/bin/python -c "import ast; ast.parse(open('dashboard.py').read()); print('SYNTAX OK')"`

- [ ] **Step 5: Commit**
```bash
git add dashboard.py
git commit -m "feat(ui): integrate sidebar multi-profile switcher and CV upload parser"
```

---

### Task 5: Dashboard Integration — Interactive CV Refiner & Chatbot UI

**Files:**
- Modify: `dashboard.py`

**Interfaces:**
- Consumes:
  - `st.session_state["tailored_cv_working"]`
  - `src.ai_assistant.refine_cv_bullet`
  - `src.ai_assistant.chat_refine_cv`
  - `src.ai_assistant.generate_cv_pdf`, `generate_cv_docx`

- [ ] **Step 1: Working State Initialization**
- When "🚀 CV'yi Bu İlana Göre Optimize Et" is clicked:
  - Store result in `st.session_state["tailored_cv_working"] = tailored_cv`.
  - Reset `st.session_state["cv_copilot_messages"] = []`.

- [ ] **Step 2: Render Inline Editable Fields & Micro-Actions**
- Render Tailored Summary in an editable `st.text_area`.
- For each Experience and Project:
  - Loop through bullets with `st.text_input` or `st.text_area` for direct editing.
  - Under each bullet, render a 3-column micro-action button row:
    - ⚡ *Daha Teknik*: Calls `refine_cv_bullet(bullet, 'technical', ...)` and updates working bullet.
    - ✂️ *Kısalt*: Calls `refine_cv_bullet(bullet, 'shorten', ...)` and updates working bullet.
    - 🔁 *Alternatif*: Calls `refine_cv_bullet(bullet, 'alternative', ...)` and updates working bullet.

- [ ] **Step 3: Render Conversational CV Copilot Chat Panel**
- Below the editable items, add a chat container:
  - Display chat message history (`user` and `assistant`).
  - Add `chat_input = st.chat_input("CV'nizde değiştirmek istediğiniz yeri yazın (örn: 'Fotoğraf projesindeki Twilio kısmını çıkar')")`.
  - When submitted:
    - Calls `chat_refine_cv(current_cv=st.session_state["tailored_cv_working"], user_prompt=chat_input, ...)`.
    - Updates `st.session_state["tailored_cv_working"]` with new JSON.
    - Appends AI explanation to message history and triggers `st.rerun()`.

- [ ] **Step 4: Live PDF & Word Downloads**
- Ensure download buttons dynamically compile from `st.session_state["tailored_cv_working"]`:
  - `generate_cv_pdf(st.session_state["tailored_cv_working"])`
  - `generate_cv_docx(st.session_state["tailored_cv_working"])`

- [ ] **Step 5: Verify syntax and end-to-end integration**
Run: `/opt/anaconda3/bin/python -c "import ast; ast.parse(open('dashboard.py').read()); print('ALL SYNTAX OK')"`

- [ ] **Step 6: Commit**
```bash
git add dashboard.py
git commit -m "feat(ui): add inline editing, bullet micro-actions, and conversational CV copilot"
```

---

### Task 6: Final Verification & System Demonstration

**Files:**
- Verify: `data/jobs.db`, `dashboard.py`, `src/database.py`, `src/cv_parser.py`, `src/ai_assistant.py`

- [ ] **Step 1: Run comprehensive test suite**
Run: `/opt/anaconda3/bin/python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Database integrity check**
Verify `get_profiles()`, `get_active_profile()`, and default profile retention.

- [ ] **Step 3: End-to-end simulation**
Simulate loading active profile, refining bullets via micro-actions and chat copilot, and generating both PDF and DOCX.
