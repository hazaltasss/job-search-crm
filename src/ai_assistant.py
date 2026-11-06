"""
Gemini AI Career Assistant.

Generates tailored cover letters and ATS-optimized CV drafts
using the Gemini 1.5 Flash model via the google-generativeai SDK.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
import re
import time

import google.generativeai as genai

from src.config import GEMINI_API_KEY, MASTER_CV_PATH, OUTPUT_DIR
from src.models import Job

logger = logging.getLogger(__name__)

# ─── Gemini Setup (lazy — configured on first use) ────────────────────────────
_cached_models: dict = {}

def _get_model(model_name: str = "gemini-3.8-flash"):
    global _cached_models
    if not GEMINI_API_KEY:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. Add it to your .env file.\n"
            "Get a free key at: https://aistudio.google.com/app/apikey"
        )
    genai.configure(api_key=GEMINI_API_KEY)
    if model_name not in _cached_models:
        _cached_models[model_name] = genai.GenerativeModel(
            model_name=model_name,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                top_p=0.9,
                max_output_tokens=2048,
            ),
        )
    return _cached_models[model_name]


_model_cooldowns: dict = {}


def _extract_retry_delay(err_str: str) -> float:
    """Extract retry delay in seconds from Gemini quota error string."""
    m_sec = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", err_str)
    if m_sec:
        return float(m_sec.group(1))
    m_h = re.search(r"retry in (\d+)h(\d+)m", err_str)
    if m_h:
        return float(m_h.group(1)) * 3600 + float(m_h.group(2)) * 60
    m_s = re.search(r"retry in (\d+(?:\.\d+)?)s", err_str)
    if m_s:
        return float(m_s.group(1))
    return 0.0


def generate_content_with_fallback(prompt: str, generation_config=None):
    """
    Generate content with automatic fallback across models.
    Prioritizes ultra-fast, high-quota models (gemini-3.5-flash-lite, gemini-flash-lite-latest),
    followed by standard flash models (gemini-3.6-flash, gemini-3.7-flash, gemini-3.8-flash).
    Immediately advances to the next candidate on 429 quota exhaustion without stalling.
    """
    candidate_models = [
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "gemini-3.5-flash",
    ]
    last_err = None
    had_quota_err = None
    now = time.time()

    for m_name in candidate_models:
        # Check if model is on cooldown (e.g. quota limit reached)
        if now < _model_cooldowns.get(m_name, 0):
            remaining = int(_model_cooldowns[m_name] - now)
            logger.debug("Skipping model '%s' (cooldown: %ds remaining)", m_name, remaining)
            continue

        try:
            model = _get_model(model_name=m_name)
            if generation_config:
                return model.generate_content(prompt, generation_config=generation_config)
            return model.generate_content(prompt)
        except Exception as err:
            last_err = err
            err_str = str(err)
            if "429" in err_str or "quota" in err_str.lower() or "resource has been exhausted" in err_str.lower():
                had_quota_err = err
                delay = _extract_retry_delay(err_str)
                cooldown = max(delay, 180.0)
                _model_cooldowns[m_name] = time.time() + cooldown
                logger.warning(
                    "Gemini model '%s' hit quota limit (429). Cooldown %ds. Advancing immediately to next candidate...",
                    m_name, int(cooldown)
                )
                continue  # Immediately advance to next model, zero sleep!

            if "404" in err_str or "not found" in err_str.lower() or "is no longer available" in err_str.lower():
                logger.warning("Gemini model '%s' unavailable (%s). Trying next candidate...", m_name, err_str[:120])
                continue

            raise err

    if had_quota_err:
        raise had_quota_err
    raise last_err


# ─── CV Loader ────────────────────────────────────────────────────────────────
def _load_cv() -> dict:
    if not MASTER_CV_PATH.exists():
        raise FileNotFoundError(
            f"master_cv.json not found at {MASTER_CV_PATH}. "
            "Please fill in your profile data."
        )
    with open(MASTER_CV_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _cv_summary(cv: dict) -> str:
    """Convert the CV JSON to a human-readable summary for the prompt."""
    p = cv.get("personal", {})
    skills = cv.get("skills", {})
    experience = cv.get("experience", [])
    education = cv.get("education", [])
    projects = cv.get("projects", [])

    lines = [
        f"Name: {p.get('name', '')}",
        f"Location: {p.get('location', '')}",
        f"Summary: {cv.get('summary', '')}",
        "",
        "=== EDUCATION ===",
    ]
    for edu in education:
        lines.append(
            f"- {edu.get('degree')} in {edu.get('field')} @ {edu.get('institution')} "
            f"({edu.get('start_date','')}–{edu.get('end_date','')})"
        )

    lines.append("\n=== WORK EXPERIENCE ===")
    for exp in experience:
        lines.append(
            f"- {exp.get('title')} @ {exp.get('company')} "
            f"({exp.get('start_date','')}–{'Present' if exp.get('is_current') else exp.get('end_date','')})"
        )
        for bullet in exp.get("bullets", []):
            lines.append(f"    • {bullet}")

    lines.append("\n=== ACADEMIC PROJECTS ===")
    for proj in projects:
        lines.append(f"- {proj.get('name')}: {proj.get('description')}")
        lines.append(f"  Tech: {', '.join(proj.get('technologies', []))}")

    lines.append("\n=== SKILLS ===")
    for category, skill_list in skills.items():
        if skill_list:
            lines.append(f"- {category.replace('_', ' ').title()}: {', '.join(skill_list)}")

    lines.append("\n=== LANGUAGES ===")
    for lang in cv.get("languages", []):
        lines.append(f"- {lang.get('language')}: {lang.get('level')}")

    return "\n".join(lines)


# ─── Cover Letter Generator ───────────────────────────────────────────────────
_COVER_LETTER_PROMPT = """
You are an expert career coach and senior technical recruiter in Germany. Write a highly tailored, compelling, and authentic cover letter in professional ENGLISH for the candidate (Hazal Taş, M.Sc. student in Data Analytics & AI at Steinbeis University Berlin; B.Sc. in Computer Engineering).

APPLICANT PROFILE:
{cv_summary}

TARGET JOB:
Title: {job_title}
Company: {company}
Location: {location}
Full Job Description:
{description}

CRITICAL ROLE-FIRST WRITING INSTRUCTIONS (NO GENERIC FLUFF, DIRECT ROLE ADAPTATION):
1. ROLE-FIRST DOMAIN DIAGNOSIS & HOOK (PARAGRAPH 1):
   - First, diagnose the PRIMARY technical and operational domain of this target role from the full job description:
     * If IT Support / Systems / IT Operations: The hook and entire tone MUST focus on IT support, hardware/software troubleshooting, Linux/Windows environments, ticket resolution, network fundamentals, and end-user satisfaction.
     * If Data Analytics / Business Intelligence: The hook MUST focus on data analysis, SQL queries, business metrics, dashboards, and deriving actionable insights.
     * If QA / Testing: The hook MUST focus on software reliability, structured test cases, API integration testing (Postman), edge-case validation, and bridging developer-tester communication.
     * If Software / Backend Engineering: The hook MUST focus on API microservices, Spring Boot, FastAPI, clean code, database optimization, and scalability.
     * If AI / Machine Learning / Data Science: The hook MUST focus on LLMs, RAG pipelines, vector search, and model deployment.
   - STRICT RULE: Do NOT force an "AI/LLM specialist" identity onto a non-AI role! If the job is QA or IT Support, do NOT open talking about neural networks or RAG pipelines; a recruiter will immediately dismiss the candidate as mismatched or uninterested in QA/IT support.
   - Start paragraph 1 with an authentic, domain-focused hook connecting Hazal's engineering mindset directly to {company}'s specific needs.

2. CONCRETE TECHNICAL PROOF POINTS (PARAGRAPH 2):
   - Directly address 2-3 specific technical requirements from the job description.
   - Ground each point in Hazal's real experience (Computer Engineering B.Sc., Softtech internship, backend systems, database schemas, and automation scripts).
   - Adapt the angle of her experience to the target domain:
     * For QA / Software Testing roles: Emphasize her engineering approach to quality, rigorous API testing using Postman & Swagger/OpenAPI at Softtech, designing test cases, validating payload schemas and edge cases, bug reporting in Jira, and writing test scripts.
     * For IT Support / Operations roles: Emphasize her practical debugging, Postman API testing, MySQL schema indexing, cross-platform issue resolution at Softtech, and automated pipeline monitoring with GitHub Actions and Python scripts.
     * For Data / Backend / AI roles: Emphasize the corresponding relevant projects and metrics.

3. THE COMPLEMENTARY SUPERPOWER & AVAILABILITY (PARAGRAPH 3):
   - Position her Computer Engineering degree and current M.Sc. studies in Berlin as an ADDED VALUE / MULTIPLIER for this specific role:
     * For QA / Testing: Her Computer Engineering background means she understands backend architecture and code, enabling deeper testing, root-cause identification, and seamless collaboration with core developers.
     * For IT Support: Her software engineering foundation and familiarity with modern automation/AI tools enable her to write Python scripts to automate repetitive support tasks, triage tickets faster, and systematically diagnose technical root causes.
     * For Data/Analytics: Her AI coursework brings modern analytical approaches to core business reporting.
   - State clearly: Fully eligible and available in Berlin / Germany for a working student role (up to 20h/week during semester, full-time during breaks), fast onboarding, and high ownership.

4. STRUCTURE:
   - 3 to 4 focused paragraphs, ~300-350 words.
   - Confident call to action (interview invitation).
   - Output ONLY the body of the cover letter, starting with "Dear Hiring Team at {company}," or similar, and ending with "Sincerely,\nHazal Taş".
"""

def generate_cover_letter(job: Job) -> str:
    """
    Generate a tailored cover letter for the given job.
    Returns the cover letter as a plain text string.
    """
    cv = _load_cv()
    cv_summary = _cv_summary(cv)

    prompt = _COVER_LETTER_PROMPT.format(
        cv_summary=cv_summary,
        job_title=job.title,
        company=job.company,
        location=job.location,
        description=job.description.strip() if job.description else "(See job URL)",
    )

    logger.info("Generating cover letter for: %s @ %s", job.title, job.company)
    response = generate_content_with_fallback(prompt)
    return response.text.strip()


# ─── CV Tailoring ─────────────────────────────────────────────────────────────
_CV_TAILOR_PROMPT = """
You are an expert ATS optimizer and career strategist. Analyze the job description and
applicant's profile, then produce a tailored CV outline optimized for this specific role.

APPLICANT PROFILE:
{cv_summary}

TARGET JOB:
Title: {job_title}
Company: {company}
Job Description:
{description}

INSTRUCTIONS:
1. Extract the TOP 10 ATS keywords from the job description (hard skills, tools, technologies).
2. Identify which of the applicant's experiences and skills best match the role.
3. Suggest a prioritized order for experience bullet points (most relevant first).
4. Recommend a skills section that mirrors the job's requirements.
5. Suggest a 2-sentence professional summary tailored to this specific role type. IMPORTANT: Keep the summary 100% company-agnostic; do NOT mention {company} or express desire to work for them (that belongs in a cover letter). Focus strictly on technical qualifications and domain alignment.

Format your response EXACTLY like this:

🎯 ATS KEYWORDS TO INCLUDE:
[comma-separated list]

📋 TAILORED PROFESSIONAL SUMMARY:
[2 sentences - objective and technical, no company name]

⭐ PRIORITIZED EXPERIENCE (most relevant first):
1. [Job title @ Company] — [Why relevant]
   • [Most relevant bullet]
   • [Second most relevant bullet]
2. ...

🛠️ RECOMMENDED SKILLS SECTION:
[Organize skills into 3-4 categories, highlighting what the job requires]

💡 TIPS:
[2-3 specific tips to strengthen this application]
"""

def tailor_cv(job: Job) -> str:
    """
    Analyze the job description against the master CV and return
    an ATS-optimized restructuring guide.
    """
    cv = _load_cv()
    cv_summary = _cv_summary(cv)

    prompt = _CV_TAILOR_PROMPT.format(
        cv_summary=cv_summary,
        job_title=job.title,
        company=job.company,
        description=job.description[:3000] if job.description else "(See job URL)",
    )

    logger.info("Tailoring CV for: %s @ %s", job.title, job.company)
    response = generate_content_with_fallback(prompt)
    return response.text.strip()


def generate_cover_letter_pdf(
    text: str,
    job_title: str = "",
    company: str = "",
    cv: dict | None = None,
    output_path: Path | None = None,
) -> bytes:
    """
    Generate a beautifully styled, ATS-ready Cover Letter PDF.
    Returns the PDF bytes for direct download.
    """
    import html
    import io
    from datetime import datetime
    from pathlib import Path
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.pdfmetrics import registerFontFamily

    if cv is None:
        cv = _load_cv()

    font_name = "Helvetica"
    font_bold = "Helvetica-Bold"
    font_italic = "Helvetica-Oblique"

    arial_paths = [
        (
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
        ),
        (
            "/Library/Fonts/Arial.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/Library/Fonts/Arial Italic.ttf",
        ),
        (
            "/usr/share/fonts/truetype/msttcorefonts/arial.ttf",
            "/usr/share/fonts/truetype/msttcorefonts/arialbd.ttf",
            "/usr/share/fonts/truetype/msttcorefonts/ariali.ttf",
        ),
    ]

    for reg_path, bold_path, ital_path in arial_paths:
        if Path(reg_path).exists() and Path(bold_path).exists():
            try:
                pdfmetrics.registerFont(TTFont("Arial", reg_path))
                pdfmetrics.registerFont(TTFont("Arial-Bold", bold_path))
                if Path(ital_path).exists():
                    pdfmetrics.registerFont(TTFont("Arial-Italic", ital_path))
                else:
                    pdfmetrics.registerFont(TTFont("Arial-Italic", reg_path))
                registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic", boldItalic="Arial-Bold")
                font_name = "Arial"
                font_bold = "Arial-Bold"
                font_italic = "Arial-Italic"
                break
            except Exception:
                pass

    def _esc(t: str) -> str:
        return html.escape(str(t), quote=False)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=44,
        rightMargin=44,
        topMargin=40,
        bottomMargin=40,
    )

    name_style = ParagraphStyle(
        "CLName",
        fontName=font_bold,
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=2,
    )

    contact_style = ParagraphStyle(
        "CLContact",
        fontName=font_name,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#475569"),
        spaceAfter=8,
    )

    meta_style = ParagraphStyle(
        "CLMeta",
        fontName=font_name,
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )

    subject_style = ParagraphStyle(
        "CLSubject",
        fontName=font_bold,
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=10,
        spaceAfter=12,
    )

    body_style = ParagraphStyle(
        "CLBody",
        fontName=font_name,
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=9,
    )

    story = []

    # 1. Header
    pers = cv.get("personal", {})
    name = pers.get("name") or "CANDIDATE NAME"
    story.append(Paragraph(_esc(name.upper()), name_style))

    contacts = [
        pers.get("location", ""),
        pers.get("phone", ""),
        pers.get("email", ""),
        pers.get("linkedin", ""),
        pers.get("github", ""),
    ]
    contacts = [c for c in contacts if c]
    story.append(Paragraph(" | ".join([_esc(c) for c in contacts]), contact_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#CBD5E1"), spaceAfter=12))

    # 2. Date & Meta
    story.append(Paragraph(f"<b>Date:</b> {datetime.now().strftime('%B %d, %Y')}", meta_style))
    if company:
        story.append(Paragraph(f"<b>Company:</b> {_esc(company)}", meta_style))
    if job_title:
        story.append(Paragraph(f"<b>Subject:</b> Application for {_esc(job_title)} Position", subject_style))

    # 3. Body paragraphs
    for para in text.split("\n\n"):
        p_text = para.strip()
        if p_text:
            cleaned_para = " ".join(p_text.split("\n"))
            story.append(Paragraph(_esc(cleaned_para), body_style))

    doc.build(story)
    pdf_data = buf.getvalue()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_data)

    return pdf_data


def generate_cover_letter_docx(
    text: str,
    job_title: str = "",
    company: str = "",
    cv: dict | None = None,
    output_path: Path | None = None,
) -> bytes:
    """Generate a formatted Word (.docx) document of the cover letter."""
    import io
    from datetime import datetime
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor

    if cv is None:
        cv = _load_cv()

    doc = Document()
    for s in doc.sections:
        s.top_margin = Inches(0.65)
        s.bottom_margin = Inches(0.65)
        s.left_margin = Inches(0.65)
        s.right_margin = Inches(0.65)

    pers = cv.get("personal", {})

    # Name
    p_name = doc.add_paragraph()
    r_name = p_name.add_run((pers.get("name") or "CANDIDATE NAME").upper())
    r_name.bold = True
    r_name.font.size = Pt(16)
    r_name.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

    # Contact
    p_con = doc.add_paragraph()
    contacts = [
        pers.get("location", ""),
        pers.get("phone", ""),
        pers.get("email", ""),
        pers.get("linkedin", ""),
        pers.get("github", ""),
    ]
    r_con = p_con.add_run(" | ".join([c for c in contacts if c]))
    r_con.font.size = Pt(9)
    r_con.font.color.rgb = RGBColor(0x47, 0x55, 0x69)

    # Meta
    p_meta = doc.add_paragraph()
    p_meta.paragraph_format.space_before = Pt(8)
    p_meta.paragraph_format.space_after = Pt(2)
    p_meta.add_run(f"Date: {datetime.now().strftime('%B %d, %Y')}\nCompany: {company}")

    if job_title:
        p_sub = doc.add_paragraph()
        p_sub.paragraph_format.space_before = Pt(4)
        p_sub.paragraph_format.space_after = Pt(8)
        r_sub = p_sub.add_run(f"Subject: Application for {job_title} Position")
        r_sub.bold = True
        r_sub.font.size = Pt(11)

    for para in text.split("\n\n"):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(8)
        p.paragraph_format.line_spacing = 1.15
        r = p.add_run(para.strip())
        r.font.size = Pt(10)

    buf = io.BytesIO()
    doc.save(buf)
    docx_bytes = buf.getvalue()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(docx_bytes)

    return docx_bytes


# ─── Save to .docx ────────────────────────────────────────────────────────────
def save_cover_letter_docx(text: str, job: Job) -> Path:
    """Save a cover letter string to a .docx file and return its path."""
    safe_company = "".join(c for c in job.company if c.isalnum() or c in " _-")[:30]
    filename = f"CoverLetter_{safe_company}_{job.job_id}.docx"
    path = OUTPUT_DIR / filename
    generate_cover_letter_docx(text, job_title=job.title, company=job.company, output_path=path)
    logger.info("Saved cover letter to %s", path)
    return path


# ─── CV Optimization for Dashboard ───────────────────────────────────────────

_OPTIMIZE_PROMPT = """
You are a senior ATS optimization expert and technical resume writer in Germany.

TASK: Tailor the applicant's resume for the target job while keeping all facts 100% truthful.
1. Tailor the 2-3 sentence PROFESSIONAL SUMMARY so that its PRIMARY FOCUS matches the target job's specific domain (e.g. IT Support, Data Analytics, Backend, AI).
2. Rewrite experience and project bullet points to emphasize relevant technical aspects matching the role.

CRITICAL ROLE-FIRST CV ADAPTATION RULES:
- The base CV is the single source of truth for all historical facts, BUT the CV's professional summary, bullet point emphasis, and skill prioritization MUST directly adapt to the TARGET JOB'S PRIMARY DOMAIN:
  * If the job is IT Support / Systems / IT Operations:
    The Professional Summary MUST lead with IT systems, software engineering discipline, troubleshooting, OS/network fundamentals, and workflow automation.
    DO NOT describe the candidate as an exclusive "Generative AI & RAG specialist". Frame her AI and Computer Engineering background as an analytical foundation and automation strength that enables faster ticket triage and automated scripting.
  * If the job is Data Analytics / BI:
    Lead with data analysis, SQL, statistical modeling, dashboards, and business insights.
  * If the job is Software / Backend Engineering:
    Lead with backend architectures, RESTful APIs, Spring Boot, FastAPI, databases, and microservices.
  * If the job is AI / Machine Learning:
    Lead with LLM architectures, RAG, vector search, and multimodal pipelines.
- STRICTLY FORBIDDEN: NEVER mention the target company name ({company}) in the summary or anywhere in the CV.
- STRICTLY FORBIDDEN: NEVER write subjective, personal motivational statements about wanting to work with, join, or contribute to this specific company (e.g., do NOT write "Highly motivated to contribute within {company}...", "Seeking to join {company}", "Excited to work at {company}"). Cover-letter style declarations belong ONLY in a cover letter!
- The professional summary must remain 100% company-agnostic, objective, and professional: focus purely on the candidate's technical identity, core competencies, relevant technical stack, and engineering capabilities aligned with the role's domain.

APPLICANT PROFILE (JSON):
{cv_json}

TARGET JOB:
Title: {job_title}
Target Domain / Context: (Company name must NOT be mentioned in the CV)
Full Job Description:
{description}

SKILLS ALREADY IN CV: {found_skills}
SKILLS MISSING FROM CV (integrate naturally where truthful): {missing_skills}
CURRENT MATCH SCORE: {current_score}%

INSTRUCTIONS:
1. PROFESSIONAL SUMMARY:
   - 2 to 3 sentences in formal CV style.
   - Company-agnostic: NEVER mention {company}.
   - No cover-letter motivational declarations ("motivated to contribute at...", "seeking to join...", etc.).
   - Directly aligned with the target role's core responsibilities and domain.
2. Rewrite ONLY the experience and project bullet points that can be truthfully enhanced.
3. Naturally weave in missing skills where the underlying work already implies them.
4. Keep all facts 100% accurate — do NOT invent companies, dates, degrees, or fictional experience.
5. Use strong action verbs and quantify where possible. Preserve bullet label prefixes where applicable (e.g. "API & Backend Development: ...").
6. Provide structured feedback on the enhancements made:
   - "added_technologies": Explicit list of specific technologies, tools, libraries, or core domain keywords you added or strongly emphasized in the CV bullets/summary (e.g. ["Docker", "FastAPI", "PostgreSQL", "CI/CD"]). If no new tools were added, list the top 2-3 existing technical skills emphasized for this role.
   - "key_changes": List of 1 to 3 concise, concrete bullet points describing the improvements made (e.g. "Tailored summary toward IT operations and troubleshooting", "Highlighted database and API testing responsibilities").
7. Format output as JSON with this exact structure:
{{
  "tailored_summary": "Objective 2-3 sentence technical professional summary matching the role's domain. Strictly NO company names and NO motivational 'seeking to join' statements.",
  "optimized_experience": [
    {{
      "role": "Software Engineering Intern @ Softtech A.Ş.",
      "bullets": [
        "API & Backend Development: ...",
        "API Testing & Documentation: ...",
        "Data & Schema Optimization: ...",
        "Cross-Platform Integration: ..."
      ]
    }}
  ],
  "optimized_projects": [
    {{
      "name": "AI-Powered Smart Photo Memory Assistant",
      "bullets": ["..."]
    }},
    {{
      "name": "Automated Job Application & Pipeline Agent",
      "bullets": ["..."]
    }},
    {{
      "name": "AI Tandem – Conversational Language Partner",
      "bullets": ["..."]
    }}
  ],
  "estimated_new_score": 95,
  "optimization_notes": "Brief explanation of what was improved (e.g. enhanced keywords, tightened metrics, alignment with domain)",
  "added_technologies": ["Docker", "FastAPI", "PostgreSQL"],
  "key_changes": [
    "Integrated Docker and FastAPI into Softtech backend bullets",
    "Highlighted CI/CD and data pipeline metrics in projects"
  ]
}}
NOTE: "estimated_new_score" MUST NOT be lower than {current_score}%. If current match score is 100%, return 100.

Return ONLY valid JSON. No markdown fences, no extra text.
"""


def extract_json_from_text(raw: str) -> dict:
    """
    Extract and parse JSON from a model response that might contain
    markdown fences, surrounding conversational text, or minor syntax quirks.
    """
    if not raw or not raw.strip():
        raise json.JSONDecodeError("Empty response received from model", raw or "", 0)

    text = raw.strip()

    # 1. Direct parse attempt if clean
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # 2. Extract code block inside ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if match:
        block = match.group(1).strip()
        try:
            data = json.loads(block)
            if isinstance(data, dict):
                return data
        except Exception:
            text = block  # fall through to substring extractor with block content

    # 3. Locate outermost curly brackets { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

        # 4. Clean trailing commas: [1, 2,] or {"a": 1,} -> [1, 2] or {"a": 1}
        cleaned = re.sub(r",\s*([\]}])", r"\1", candidate)
        # Remove single-line comments (// ...)
        cleaned = re.sub(r"//.*$", "", cleaned, flags=re.MULTILINE)
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    logger.error("Failed to parse JSON from response. Snippet: %s", raw[:300])
    raise json.JSONDecodeError("Could not extract valid JSON from model response", raw, 0)


def sanitize_cv_summary(summary: str, company: str = "") -> str:
    """
    Ensure the CV professional summary is objective, ATS-focused, and 100%
    free of target company names or cover-letter style motivational phrases.
    A CV summary represents the candidate's professional profile, not an application letter.
    """
    if not summary or not isinstance(summary, str):
        return ""

    cleaned = summary.strip()

    if company:
        # Strip common legal designations to catch variations (e.g., 'Vattenfall GmbH' -> 'Vattenfall')
        base_company = re.sub(
            r"(?i)\s+(gmbh|ag|se|inc\.?|corp\.?|llc|co\.?|kg|ltd\.?)\b",
            "",
            company,
        ).strip()
        comp_patterns = [re.escape(company)]
        if base_company and base_company.lower() != company.lower():
            comp_patterns.append(re.escape(base_company))

        for c_pat in comp_patterns:
            # 1. Clean "within/at/in [Company]'s [ecosystem/team/platform]" -> "in modern \1s"
            cleaned = re.sub(
                rf"(?i)\b(?:within|at|for|in)\s+{c_pat}(?:'s)?\s+(cloud\s+analytics\s+ecosystem|data\s+ecosystem|ecosystem|team|platform|infrastructure|organization)\b",
                r"in modern \1s",
                cleaned,
            )
            # 2. Clean "to contribute as a [Role] at/within/for [Company]"
            cleaned = re.sub(
                rf"(?i)\b(?:within|at|for|in|to\s+join)\s+{c_pat}(?:'s)?\b",
                "",
                cleaned,
            )
            # 3. Clean any remaining standalone company name mention
            cleaned = re.sub(rf"(?i)\b{c_pat}(?:'s)?\b", "", cleaned)

    # 4. Remove cover-letter style motivational phrases
    cleaned = re.sub(
        r"(?i)\b(?:highly\s+)?motivated\s+to\s+(?:leverage|contribute|apply)\b",
        "experienced in leveraging",
        cleaned,
    )
    cleaned = re.sub(
        r"(?i)\bto\s+contribute\s+as\s+a\s+[^.,;]+\b",
        "delivering robust technical solutions",
        cleaned,
    )

    # 5. Clean punctuation and whitespace
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;])", r"\1", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = cleaned.strip()

    return cleaned


def optimize_cv_for_job(
    job_title: str,
    job_company: str,
    job_description: str,
    found_skills: list[str],
    missing_skills: list[str],
    cv: dict | None = None,
    current_score: int = 0,
) -> dict:
    """
    Dashboard'daki "Optimize CV" butonu için.
    Mevcut CV bullet point'lerini eksik becerileri doğal şekilde
    entegre edecek biçimde ATS odaklı yeniden yazar.

    Returns a dict with optimized bullets and estimated new score.
    """
    if cv is None:
        cv = _load_cv()

    # Only send relevant CV sections to keep prompt compact
    compact_cv = {
        "personal": cv.get("personal", {}),
        "summary": cv.get("summary", ""),
        "experience": cv.get("experience", []),
        "projects": cv.get("projects", []),
        "skills": cv.get("skills", {}),
    }

    prompt = _OPTIMIZE_PROMPT.format(
        cv_json=json.dumps(compact_cv, ensure_ascii=False, indent=2),
        job_title=job_title,
        company=job_company,
        description=job_description.strip() if job_description else "(See job URL)",
        found_skills=", ".join(found_skills[:15]) or "none detected",
        missing_skills=", ".join(missing_skills[:15]) or "none",
        current_score=current_score,
    )

    logger.info("Optimizing CV for: %s @ %s (current_score=%d)", job_title, job_company, current_score)

    last_exc = None
    # Retry up to 2 times
    for attempt in range(2):
        try:
            # Enforce application/json output if supported by model/SDK
            config = genai.types.GenerationConfig(
                temperature=0.2,
                max_output_tokens=4096,
                response_mime_type="application/json",
            )
            response = generate_content_with_fallback(prompt, generation_config=config)
        except Exception as api_err:
            if "429" in str(api_err) or "quota" in str(api_err).lower():
                raise api_err
            logger.warning("Generation with response_mime_type failed (%s), falling back to default", api_err)
            response = generate_content_with_fallback(prompt)

        raw = response.text.strip() if (response and response.text) else ""
        try:
            data = extract_json_from_text(raw)
            # Normalize possible key variations
            if "experience" in data and "optimized_experience" not in data:
                data["optimized_experience"] = data["experience"]
            if "projects" in data and "optimized_projects" not in data:
                data["optimized_projects"] = data["projects"]
            if "notes" in data and "optimization_notes" not in data:
                data["optimization_notes"] = data["notes"]
            if "new_score" in data and "estimated_new_score" not in data:
                data["estimated_new_score"] = data["new_score"]
            if "technologies" in data and "added_technologies" not in data:
                data["added_technologies"] = data["technologies"]
            if "skills_added" in data and "added_technologies" not in data:
                data["added_technologies"] = data["skills_added"]
            if "skills" in data and "added_technologies" not in data and isinstance(data["skills"], list):
                data["added_technologies"] = data["skills"]
            if "changes" in data and "key_changes" not in data:
                data["key_changes"] = data["changes"]

            # Ensure keys exist with sensible defaults
            data.setdefault("optimized_experience", [])
            data.setdefault("optimized_projects", [])
            data.setdefault("optimization_notes", "")
            data.setdefault("added_technologies", [])
            data.setdefault("key_changes", [])

            # Normalize added_technologies
            raw_techs = data["added_technologies"]
            if isinstance(raw_techs, str):
                data["added_technologies"] = [t.strip() for t in raw_techs.split(",") if t.strip()]
            elif isinstance(raw_techs, list):
                data["added_technologies"] = [str(t).strip() for t in raw_techs if str(t).strip()]
            else:
                data["added_technologies"] = []

            # Normalize key_changes
            raw_changes = data["key_changes"]
            if isinstance(raw_changes, str):
                data["key_changes"] = [c.strip() for c in raw_changes.splitlines() if c.strip()]
            elif isinstance(raw_changes, list):
                data["key_changes"] = [str(c).strip() for c in raw_changes if str(c).strip()]
            else:
                data["key_changes"] = []

            # Fallback & Supplement: Detect missing skills that are now present in tailored CV text
            opt_corpus = (
                data.get("tailored_summary", "") + " " +
                " ".join(
                    " ".join(exp.get("bullets", []))
                    for exp in data.get("optimized_experience", [])
                    if isinstance(exp, dict)
                ) + " " +
                " ".join(
                    " ".join(proj.get("bullets", []))
                    for proj in data.get("optimized_projects", [])
                    if isinstance(proj, dict)
                )
            ).lower()

            existing_techs_lower = {t.lower() for t in data["added_technologies"]}
            if missing_skills and isinstance(missing_skills, list):
                for ms in missing_skills:
                    if ms and isinstance(ms, str) and ms.lower() not in existing_techs_lower:
                        pattern = r"\b" + re.escape(ms.lower()) + r"\b"
                        if re.search(pattern, opt_corpus):
                            data["added_technologies"].append(ms.strip())
                            existing_techs_lower.add(ms.lower())

            # If key_changes is still empty but optimization_notes has text, derive bullet points
            if not data["key_changes"] and data.get("optimization_notes"):
                note_str = str(data["optimization_notes"]).strip()
                if ";" in note_str:
                    data["key_changes"] = [p.strip() for p in note_str.split(";") if p.strip()]
                elif "\n" in note_str:
                    data["key_changes"] = [p.strip("•- \t") for p in note_str.splitlines() if p.strip("•- \t")]
                elif note_str:
                    data["key_changes"] = [note_str]

            # Ensure estimated_new_score is at least current_score
            raw_new_score = data.get("estimated_new_score", current_score or 85)
            try:
                parsed_score = int(raw_new_score)
            except (ValueError, TypeError):
                parsed_score = current_score or 85

            if current_score >= 100:
                data["estimated_new_score"] = 100
            else:
                data["estimated_new_score"] = min(100, max(current_score, parsed_score))

            # Sanitize tailored_summary to guarantee no company references slip through
            if "tailored_summary" in data and isinstance(data["tailored_summary"], str):
                data["tailored_summary"] = sanitize_cv_summary(data["tailored_summary"], job_company)

            return data
        except Exception as exc:
            last_exc = exc
            logger.warning("Attempt %d to parse JSON failed: %s", attempt + 1, exc)
            prompt += "\nIMPORTANT: Return ONLY a valid JSON object. No Markdown fences, no explanation."

    raise last_exc or json.JSONDecodeError("Failed to parse Gemini output as JSON", "", 0)


def build_tailored_cv_data(opt_result: dict, base_cv: dict | None = None, company: str = "") -> dict:
    """
    Merge base CV data with optimized summary, experience, and project bullets.
    Produces a complete, updated CV dictionary ready for Word (.docx) generation.
    """
    if base_cv is None:
        base_cv = _load_cv()

    tailored = json.loads(json.dumps(base_cv))  # deep copy

    # 1. Update summary if tailored_summary is provided
    tailored_summary = opt_result.get("tailored_summary")
    if tailored_summary and isinstance(tailored_summary, str) and len(tailored_summary.strip()) > 20:
        tailored["summary"] = sanitize_cv_summary(tailored_summary, company).strip()

    # 2. Update experience bullets if provided
    opt_exp = opt_result.get("optimized_experience", [])
    if opt_exp and isinstance(opt_exp, list):
        for i, orig_exp in enumerate(tailored.get("experience", [])):
            if i < len(opt_exp) and isinstance(opt_exp[i], dict):
                bullets = opt_exp[i].get("bullets")
                if bullets and isinstance(bullets, list) and len(bullets) > 0:
                    orig_exp["bullets"] = bullets

    # 3. Update projects bullets if provided
    opt_proj = opt_result.get("optimized_projects", [])
    if opt_proj and isinstance(opt_proj, list):
        for i, orig_proj in enumerate(tailored.get("projects", [])):
            if i < len(opt_proj) and isinstance(opt_proj[i], dict):
                bullets = opt_proj[i].get("bullets")
                if bullets and isinstance(bullets, list) and len(bullets) > 0:
                    orig_proj["bullets"] = bullets

    return tailored


# ─── Micro-Action & CV Copilot ────────────────────────────────────────────────

def build_micro_action_prompt(bullet: str, action: str, job_context: str = "") -> str:
    """Build the prompt for rewriting an individual CV bullet based on an action."""
    action_lower = action.lower()
    if "tech" in action_lower:
        directive = (
            "Rewrite this bullet point to be more technical. Use precise engineering terminology, "
            "mention architectural patterns or frameworks where truthful, and emphasize quantitative metrics or scale."
        )
    elif "short" in action_lower:
        directive = (
            "Condense this bullet point into a crisp, concise, high-impact single line. "
            "Eliminate filler words while keeping the core accomplishment and action verb."
        )
    else:  # alternative
        directive = (
            "Reframe this bullet point from an alternative angle, emphasizing different aspects "
            "such as problem solving, performance optimization, or cross-functional value."
        )

    context_part = f"\nTARGET JOB CONTEXT:\n{job_context}\n" if job_context else ""

    return f"""You are a senior technical resume writer.
TASK: {directive}

ORIGINAL BULLET:
"{bullet}"
{context_part}
INSTRUCTIONS:
- Return ONLY the rewritten bullet point text as a single string.
- Do NOT add quotation marks, bullet symbols (like • or -), or commentary.
- Preserve any existing bold prefix style if present (e.g. "Topic: ...").
- Keep facts 100% truthful.
"""


def refine_cv_bullet(bullet: str, action: str, job_context: str = "") -> str:
    """Use Gemini Flash to refine a single CV bullet point according to the requested micro-action."""
    prompt = build_micro_action_prompt(bullet, action, job_context)
    try:
        config = genai.types.GenerationConfig(temperature=0.2, max_output_tokens=256)
        response = generate_content_with_fallback(prompt, generation_config=config)
        cleaned = response.text.strip()
        cleaned = re.sub(r"^[•\-\*\s]+", "", cleaned)
        cleaned = cleaned.strip('"\'')
        return cleaned or bullet
    except Exception as exc:
        logger.warning("Micro-action %s failed for bullet (%s): %s", action, bullet, exc)
        return bullet


def build_copilot_prompt(
    current_cv: dict,
    user_prompt: str,
    chat_history: list[dict],
    job_title: str = "",
    company: str = "",
    description: str = "",
) -> str:
    """Construct prompt for the CV Copilot conversational assistant with intent recognition."""
    history_lines = []
    for m in chat_history[-6:]:
        role = "User" if m.get("role") == "user" else "Assistant"
        history_lines.append(f"{role}: {m.get('content', '')}")
    history_str = "\n".join(history_lines) if history_lines else "(No previous conversation)"

    compact_cv = {
        "personal": current_cv.get("personal", {}),
        "summary": current_cv.get("summary", ""),
        "experience": current_cv.get("experience", []),
        "projects": current_cv.get("projects", []),
        "skills": current_cv.get("skills", {}),
    }

    return f"""You are an expert AI Career Copilot and technical resume strategist.
The candidate is reviewing, discussing, and interactively editing their tailored CV for a specific target job.

TARGET JOB:
Title: {job_title}
Company: {company}
Description: {description[:2000] if description else '(Not specified)'}

CURRENT CV WORKING STATE (JSON):
{json.dumps(compact_cv, ensure_ascii=False, indent=2)}

RECENT CHAT HISTORY:
{history_str}

CANDIDATE'S INPUT:
"{user_prompt}"

TASK & INTENT RECOGNITION:
First determine the candidate's intent:
1. "question": The candidate is asking a question, asking for clarification, checking what was done (e.g. "go ekledin mi?", "bu ilanda hangi yetenekler aranıyor?", "özeti neden değiştirdin?", "ATS skoru neden arttı?"), or asking for advice/recommendation.
   - DO NOT modify the CV. Leave updated_cv as null.
   - Answer the question directly, thoroughly, and accurately in Turkish based on the CURRENT CV WORKING STATE and the TARGET JOB description.
   - For example, if asked whether a technology (like "Go", "Docker", etc.) is added or present ("go ekledin mi?"): check the CURRENT CV WORKING STATE (in skills, experience bullets, and projects). If it is already there, state where it appears. If it is NOT in the CV, clearly state that it is not currently included and explain why or offer to add it.
2. "edit": The candidate wants to modify, add, remove, rewrite, shorten, or rephrase something in their CV (e.g. "Go'yu yeteneklere ekle", "özeti kısalt", "Twilio projesini sil", "Docker deneyimini öne çıkar").
   - Modify ONLY the relevant sections in updated_cv (summary, experience, projects, skills). Keep everything else intact.
   - If modifying skills, update the corresponding category list (e.g. "programming_languages", "backend_and_systems", "generative_ai_and_llms", "tools", "core_competencies").
   - In assistant_message, provide a clear, friendly 1-2 sentence explanation in Turkish of what was updated.
3. "both": The candidate is both asking a question AND requesting a change.
   - Answer the question in assistant_message AND apply the edits in updated_cv.

RULES:
- Keep all factual experience 100% accurate — do not invent degrees or fictional companies.
- Always provide a helpful response in Turkish for assistant_message.
- Format your output as JSON with this exact schema:
{{
  "intent": "question" | "edit" | "both",
  "assistant_message": "Clear explanation or direct answer to the question in Turkish.",
  "updated_cv": null or {{
    "summary": "...",
    "experience": [ ... ],
    "projects": [ ... ],
    "skills": {{
      "programming_languages": [ ... ],
      "generative_ai_and_llms": [ ... ],
      "backend_and_systems": [ ... ],
      "core_competencies": [ ... ],
      "tools": [ ... ]
    }}
  }}
}}

Return ONLY valid JSON.
"""


def chat_refine_cv(
    current_cv: dict,
    user_prompt: str,
    chat_history: list[dict],
    job_title: str = "",
    company: str = "",
    description: str = "",
) -> tuple[dict, str]:
    """
    Process candidate's conversational instruction or question, modify the CV if requested,
    and return (updated_cv, assistant_message).
    """
    prompt = build_copilot_prompt(
        current_cv=current_cv,
        user_prompt=user_prompt,
        chat_history=chat_history,
        job_title=job_title,
        company=company,
        description=description,
    )

    try:
        config = genai.types.GenerationConfig(
            temperature=0.2,
            max_output_tokens=4096,
            response_mime_type="application/json",
        )
        response = generate_content_with_fallback(prompt, generation_config=config)
    except Exception as exc:
        if "429" in str(exc) or "quota" in str(exc).lower():
            raise exc
        logger.warning("Copilot with response_mime_type failed (%s), using fallback", exc)
        response = generate_content_with_fallback(prompt)

    raw_text = response.text.strip() if (response and response.text) else "{}"
    try:
        parsed = extract_json_from_text(raw_text)
        intent = str(parsed.get("intent", "edit")).lower()
        msg = parsed.get("assistant_message", "").strip() or "İsteğiniz işlendi."
        updated_part = parsed.get("updated_cv")

        # If pure question or no valid updated_cv provided, do NOT mutate the CV
        if intent == "question" or not updated_part or not isinstance(updated_part, dict):
            return current_cv, msg

        new_cv = json.loads(json.dumps(current_cv))
        if "summary" in updated_part and isinstance(updated_part["summary"], str) and len(updated_part["summary"]) > 10:
            new_cv["summary"] = updated_part["summary"]
        if "experience" in updated_part and isinstance(updated_part["experience"], list) and updated_part["experience"]:
            new_cv["experience"] = updated_part["experience"]
        if "projects" in updated_part and isinstance(updated_part["projects"], list) and updated_part["projects"]:
            new_cv["projects"] = updated_part["projects"]
        if "skills" in updated_part and isinstance(updated_part["skills"], dict) and updated_part["skills"]:
            if "skills" not in new_cv or not isinstance(new_cv["skills"], dict):
                new_cv["skills"] = {}
            for cat_k, cat_v in updated_part["skills"].items():
                if isinstance(cat_v, list) and cat_v:
                    new_cv["skills"][cat_k] = cat_v

        return new_cv, msg

    except Exception as exc:
        logger.error("Failed to parse Copilot response: %s (Raw: %s)", exc, raw_text[:200])
        return current_cv, "Üzgünüm, isteğinizi uygularken bir sorun oluştu. Lütfen tekrar deneyin."


def build_cover_letter_copilot_prompt(
    current_cover_letter: str,
    user_prompt: str,
    chat_history: list[dict],
    job_title: str = "",
    company: str = "",
    description: str = "",
    cv: dict | None = None,
) -> str:
    """Construct prompt for the Cover Letter Copilot conversational assistant."""
    history_lines = []
    for m in chat_history[-6:]:
        role = "User" if m.get("role") == "user" else "Assistant"
        history_lines.append(f"{role}: {m.get('content', '')}")
    history_str = "\n".join(history_lines) if history_lines else "(No previous conversation)"

    cv_summary_str = _cv_summary(cv or _load_cv())

    return f"""You are an elite Cover Letter Strategist and Career Mentor.
The candidate (Hazal Taş, M.Sc. Data Analytics & AI at Steinbeis University Berlin, B.Sc. Computer Engineering) is reviewing, discussing, brainstorming, and interactively tailoring her Cover Letter for a specific target job.

TARGET JOB:
Title: {job_title}
Company: {company}
Description: {description[:2500] if description else '(Not specified)'}

APPLICANT PROFILE:
{cv_summary_str}

CURRENT COVER LETTER WORKING DRAFT:
\"\"\"
{current_cover_letter}
\"\"\"

RECENT CHAT HISTORY:
{history_str}

CANDIDATE'S INPUT:
"{user_prompt}"

TASK & INTENT RECOGNITION:
First determine the candidate's intent:
1. "question": The candidate is asking for advice, brainstorming ideas, or asking a strategic question (e.g. "Sence bu ilanda Linux ve Docker'ı mı öne çıkaralım yoksa AI projelerimi mi?", "2. paragraf sence yeterince ikna edici mi?", "Şirketin hangi değerlerine değinebiliriz?").
   - Act as an insightful mentor: give strategic, nuanced advice in Turkish explaining WHY and HOW to connect her background with this specific company and role.
   - Do NOT modify the cover letter. Leave "updated_cover_letter" as null.
2. "edit": The candidate wants to modify, refine, rephrase, expand, shorten, or rewrite part or all of the cover letter (e.g. "2. paragrafa Docker ve Linux ekle", "tonunu daha özgüvenli yap", "Softtech stajımdaki API projemle bağ kur", "girişi daha dikkat çekici yap").
   - Revise the cover letter text in English according to the instruction.
   - Maintain professional formatting, high persuasiveness, and authentic connection to {company}.
   - Provide "updated_cover_letter" with the complete revised letter text in English.
   - In "assistant_message", provide a friendly, encouraging explanation in Turkish describing what changes were made and why it enhances the application.
3. "both": The candidate is brainstorming/asking a question AND wants the letter updated accordingly.
   - Provide the strategic answer/explanation in Turkish in "assistant_message" AND provide the revised English letter in "updated_cover_letter".

RULES:
- The cover letter itself must ALWAYS be in professional English.
- The assistant_message (conversation with candidate) must ALWAYS be in clear, supportive Turkish.
- Keep all facts truthful to Hazal's profile — do not invent fictional employers or degrees.
- Format your response as valid JSON with this exact schema:
{{
  "intent": "question" | "edit" | "both",
  "assistant_message": "Türkçe stratejik değerlendirme, tavsiye veya yapılan değişikliğin açıklaması.",
  "updated_cover_letter": null or "Full updated cover letter text in English..."
}}

Return ONLY valid JSON.
"""


def chat_refine_cover_letter(
    current_cover_letter: str,
    user_prompt: str,
    chat_history: list[dict],
    job_title: str = "",
    company: str = "",
    description: str = "",
    cv: dict | None = None,
) -> tuple[str, str]:
    """
    Process candidate's conversational instruction or question about the Cover Letter,
    modify the letter if requested, and return (updated_cover_letter, assistant_message).
    """
    prompt = build_cover_letter_copilot_prompt(
        current_cover_letter=current_cover_letter,
        user_prompt=user_prompt,
        chat_history=chat_history,
        job_title=job_title,
        company=company,
        description=description,
        cv=cv,
    )

    try:
        config = genai.types.GenerationConfig(
            temperature=0.3,
            max_output_tokens=4096,
            response_mime_type="application/json",
        )
        response = generate_content_with_fallback(prompt, generation_config=config)
    except Exception as exc:
        if "429" in str(exc) or "quota" in str(exc).lower():
            raise exc
        logger.warning("Cover Letter Copilot with response_mime_type failed (%s), using fallback", exc)
        response = generate_content_with_fallback(prompt)

    raw_text = response.text.strip() if (response and response.text) else "{}"
    try:
        parsed = extract_json_from_text(raw_text)
        intent = str(parsed.get("intent", "edit")).lower()
        msg = parsed.get("assistant_message", "").strip() or "Ön yazı isteğiniz doğrultusunda güncellendi."
        updated_text = parsed.get("updated_cover_letter")

        if intent == "question" or not updated_text or not isinstance(updated_text, str) or len(updated_text.strip()) < 50:
            return current_cover_letter, msg

        return updated_text.strip(), msg
    except Exception as exc:
        logger.error("Failed to parse Cover Letter Copilot response: %s (Raw: %s)", exc, raw_text[:200])
        return current_cover_letter, "İsteğinizi işlerken bir sorun oluştu. Lütfen tekrar deneyin."



def generate_cv_docx(cv: dict, output_path: Path | None = None) -> bytes:
    """
    Generate an ATS-compliant, professionally styled Word (.docx) document
    matching the layout, typography, and structure of the candidate's base CV.
    Returns the document bytes for direct download.
    """
    import io
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor

    doc = Document()

    # Set page margins to 0.6 inches for modern, ATS-friendly spacing
    for section in doc.sections:
        section.top_margin = Inches(0.6)
        section.bottom_margin = Inches(0.6)
        section.left_margin = Inches(0.65)
        section.right_margin = Inches(0.65)

    # Base styling
    normal_style = doc.styles["Normal"]
    normal_style.font.name = "Calibri"
    normal_style.font.size = Pt(10)
    normal_style.font.color.rgb = RGBColor(0x1E, 0x29, 0x3B)

    def add_heading(title: str):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(9)
        p.paragraph_format.space_after = Pt(3)
        run = p.add_run(title.upper())
        run.bold = True
        run.font.size = Pt(11)
        run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

    # 1. Header: Candidate Name
    p_name = doc.add_paragraph()
    p_name.paragraph_format.space_before = Pt(0)
    p_name.paragraph_format.space_after = Pt(2)
    name_run = p_name.add_run((cv.get("personal", {}).get("name") or "CANDIDATE NAME").upper())
    name_run.bold = True
    name_run.font.size = Pt(18)
    name_run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

    # Contact line
    p_contact = doc.add_paragraph()
    p_contact.paragraph_format.space_before = Pt(0)
    p_contact.paragraph_format.space_after = Pt(7)
    pers = cv.get("personal", {})
    contacts = [
        pers.get("location", ""),
        pers.get("phone", ""),
        pers.get("email", ""),
        pers.get("linkedin", ""),
        pers.get("github", ""),
    ]
    contacts = [c for c in contacts if c]
    contact_run = p_contact.add_run(" | ".join(contacts))
    contact_run.font.size = Pt(9.5)
    contact_run.font.color.rgb = RGBColor(0x47, 0x55, 0x69)

    # 2. Professional Summary
    summary_text = cv.get("summary", "")
    if summary_text:
        add_heading("PROFESSIONAL SUMMARY")
        p_sum = doc.add_paragraph()
        p_sum.paragraph_format.space_before = Pt(0)
        p_sum.paragraph_format.space_after = Pt(5)
        p_sum.paragraph_format.line_spacing = 1.15
        r_sum = p_sum.add_run(summary_text)
        r_sum.font.size = Pt(10)

    # 3. Technical Skills
    add_heading("TECHNICAL SKILLS")
    skills = cv.get("skills", {})
    tech_skills = cv.get("technical_skills", {})
    skill_rows = [
        ("Languages & Frameworks", skills.get("programming_languages") or tech_skills.get("Languages & Frameworks")),
        ("Generative AI & LLMs", skills.get("generative_ai_and_llms") or tech_skills.get("Generative AI & LLMs")),
        ("Backend & Systems", skills.get("backend_and_systems") or tech_skills.get("Backend & Systems")),
        ("Core Competencies", skills.get("core_competencies") or tech_skills.get("Core Competencies")),
        ("Tools & Platforms", skills.get("tools") or tech_skills.get("Tools & Platforms")),
    ]
    for cat_name, cat_items in skill_rows:
        if not cat_items:
            continue
        p_sk = doc.add_paragraph(style="List Bullet")
        p_sk.paragraph_format.space_before = Pt(0)
        p_sk.paragraph_format.space_after = Pt(2)
        r_lbl = p_sk.add_run(f"{cat_name}: ")
        r_lbl.bold = True
        r_lbl.font.size = Pt(9.5)
        items_str = ", ".join(cat_items) if isinstance(cat_items, list) else str(cat_items)
        r_val = p_sk.add_run(items_str)
        r_val.font.size = Pt(9.5)

    # 4. Education
    education = cv.get("education", [])
    if education:
        add_heading("EDUCATION")
        for edu in education:
            p_inst = doc.add_paragraph()
            p_inst.paragraph_format.space_before = Pt(2)
            p_inst.paragraph_format.space_after = Pt(1)
            inst_text = edu.get("institution", "")
            if edu.get("location"):
                inst_text += f" — {edu.get('location')}"
            r_inst = p_inst.add_run(inst_text)
            r_inst.bold = True
            r_inst.font.size = Pt(10)

            p_deg = doc.add_paragraph()
            p_deg.paragraph_format.space_before = Pt(0)
            p_deg.paragraph_format.space_after = Pt(1)
            deg_text = edu.get("degree", "")
            if edu.get("field"):
                deg_text += f" in {edu.get('field')}"
            r_deg = p_deg.add_run(deg_text)
            r_deg.italic = True
            r_deg.font.size = Pt(9.5)

            p_dt = doc.add_paragraph()
            p_dt.paragraph_format.space_before = Pt(0)
            p_dt.paragraph_format.space_after = Pt(3)
            dt_str = edu.get("date_display") or (f"{edu.get('start_date','')} – {edu.get('end_date','')}" if edu.get("start_date") else "")
            r_dt = p_dt.add_run(dt_str)
            r_dt.font.size = Pt(9)
            r_dt.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    # 5. Work Experience
    experience = cv.get("experience", [])
    if experience:
        add_heading("WORK EXPERIENCE")
        for exp in experience:
            p_co = doc.add_paragraph()
            p_co.paragraph_format.space_before = Pt(4)
            p_co.paragraph_format.space_after = Pt(1)
            co_text = exp.get("company", "")
            if exp.get("location"):
                co_text += f" — {exp.get('location')}"
            r_co = p_co.add_run(co_text)
            r_co.bold = True
            r_co.font.size = Pt(10.5)

            p_ti = doc.add_paragraph()
            p_ti.paragraph_format.space_before = Pt(0)
            p_ti.paragraph_format.space_after = Pt(2)
            ti_text = exp.get("title", "")
            date_range = exp.get("date_range") or (f"{exp.get('start_date','')} – {exp.get('end_date','')}" if exp.get("start_date") else "")
            if date_range:
                ti_text += f" | {date_range}"
            r_ti = p_ti.add_run(ti_text)
            r_ti.italic = True
            r_ti.font.size = Pt(9.5)
            r_ti.font.color.rgb = RGBColor(0x33, 0x41, 0x55)

            for bullet in exp.get("bullets", []):
                p_b = doc.add_paragraph(style="List Bullet")
                p_b.paragraph_format.space_before = Pt(0)
                p_b.paragraph_format.space_after = Pt(2)
                p_b.paragraph_format.line_spacing = 1.15
                if ": " in bullet:
                    prefix, rest = bullet.split(": ", 1)
                    r_p = p_b.add_run(f"{prefix}: ")
                    r_p.bold = True
                    r_p.font.size = Pt(9.5)
                    r_r = p_b.add_run(rest)
                    r_r.font.size = Pt(9.5)
                else:
                    r_b = p_b.add_run(bullet)
                    r_b.font.size = Pt(9.5)

    # 6. Selected AI & Software Projects
    projects = cv.get("projects", [])
    if projects:
        add_heading("SELECTED AI & SOFTWARE PROJECTS")
        for proj in projects:
            p_pr = doc.add_paragraph()
            p_pr.paragraph_format.space_before = Pt(4)
            p_pr.paragraph_format.space_after = Pt(2)
            pr_name = proj.get("name", "")
            techs = proj.get("technologies_header") or ", ".join(proj.get("technologies", []))
            if techs:
                header_text = f"{pr_name} | {techs}"
            else:
                header_text = pr_name
            r_pr = p_pr.add_run(header_text)
            r_pr.bold = True
            r_pr.font.size = Pt(10)

            for bullet in proj.get("bullets", []):
                p_b = doc.add_paragraph(style="List Bullet")
                p_b.paragraph_format.space_before = Pt(0)
                p_b.paragraph_format.space_after = Pt(2)
                p_b.paragraph_format.line_spacing = 1.15
                r_b = p_b.add_run(bullet)
                r_b.font.size = Pt(9.5)

    buf = io.BytesIO()
    doc.save(buf)
    docx_data = buf.getvalue()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(docx_data)

    return docx_data


def generate_cv_pdf(cv: dict, output_path: Path | None = None) -> bytes:
    """
    Generate an ATS-compliant, professionally styled PDF document
    matching the layout, typography, and structure of the candidate's base CV.
    Returns the PDF bytes for direct download.
    """
    import html
    import io
    from pathlib import Path
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.pdfmetrics import registerFontFamily
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    # Register Arial TrueType font for clean Unicode support (Ş, İ, ç, ö, ü, etc.)
    font_name = "Helvetica"
    font_bold = "Helvetica-Bold"
    font_italic = "Helvetica-Oblique"

    arial_paths = [
        (
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
        ),
        (
            "/Library/Fonts/Arial.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/Library/Fonts/Arial Italic.ttf",
        ),
        (
            "/usr/share/fonts/truetype/msttcorefonts/arial.ttf",
            "/usr/share/fonts/truetype/msttcorefonts/arialbd.ttf",
            "/usr/share/fonts/truetype/msttcorefonts/ariali.ttf",
        ),
    ]

    for reg_path, bold_path, ital_path in arial_paths:
        if Path(reg_path).exists() and Path(bold_path).exists():
            try:
                pdfmetrics.registerFont(TTFont("Arial", reg_path))
                pdfmetrics.registerFont(TTFont("Arial-Bold", bold_path))
                if Path(ital_path).exists():
                    pdfmetrics.registerFont(TTFont("Arial-Italic", ital_path))
                else:
                    pdfmetrics.registerFont(TTFont("Arial-Italic", reg_path))
                registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic", boldItalic="Arial-Bold")
                font_name = "Arial"
                font_bold = "Arial-Bold"
                font_italic = "Arial-Italic"
                break
            except Exception:
                pass

    def _esc(t: str) -> str:
        return html.escape(str(t), quote=False)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=38,
        rightMargin=38,
        topMargin=36,
        bottomMargin=36,
    )

    name_style = ParagraphStyle(
        "CVName",
        fontName=font_bold,
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=3,
    )

    contact_style = ParagraphStyle(
        "CVContact",
        fontName=font_name,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#475569"),
        spaceAfter=10,
    )

    heading_style = ParagraphStyle(
        "CVHeading",
        fontName=font_bold,
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=9,
        spaceAfter=4,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        "CVBody",
        fontName=font_name,
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=4,
    )

    bullet_style = ParagraphStyle(
        "CVBullet",
        fontName=font_name,
        fontSize=9.5,
        leading=13.5,
        leftIndent=12,
        firstLineIndent=-12,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=3,
    )

    role_style = ParagraphStyle(
        "CVRole",
        fontName=font_bold,
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=5,
        spaceAfter=1,
        keepWithNext=True,
    )

    subrole_style = ParagraphStyle(
        "CVSubRole",
        fontName=font_italic,
        fontSize=9.5,
        leading=12.5,
        textColor=colors.HexColor("#334155"),
        spaceAfter=3,
        keepWithNext=True,
    )

    date_style = ParagraphStyle(
        "CVDate",
        fontName=font_name,
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#64748B"),
        spaceAfter=3,
    )

    story = []

    # 1. Header: Name & Contact
    name = cv.get("personal", {}).get("name") or "CANDIDATE NAME"
    story.append(Paragraph(_esc(name.upper()), name_style))

    pers = cv.get("personal", {})
    contacts = [
        pers.get("location", ""),
        pers.get("phone", ""),
        pers.get("email", ""),
        pers.get("linkedin", ""),
        pers.get("github", ""),
    ]
    contacts = [c for c in contacts if c]
    story.append(Paragraph(" | ".join([_esc(c) for c in contacts]), contact_style))

    # 2. Professional Summary
    if cv.get("summary"):
        story.append(Paragraph("PROFESSIONAL SUMMARY", heading_style))
        story.append(Paragraph(_esc(cv.get("summary")), body_style))

    # 3. Technical Skills
    story.append(Paragraph("TECHNICAL SKILLS", heading_style))
    skills = cv.get("skills", {})
    tech_skills = cv.get("technical_skills", {})
    skill_rows = [
        ("Languages & Frameworks", skills.get("programming_languages") or tech_skills.get("Languages & Frameworks")),
        ("Generative AI & LLMs", skills.get("generative_ai_and_llms") or tech_skills.get("Generative AI & LLMs")),
        ("Backend & Systems", skills.get("backend_and_systems") or tech_skills.get("Backend & Systems")),
        ("Core Competencies", skills.get("core_competencies") or tech_skills.get("Core Competencies")),
        ("Tools & Platforms", skills.get("tools") or tech_skills.get("Tools & Platforms")),
    ]
    for cat_name, cat_items in skill_rows:
        if not cat_items:
            continue
        items_str = ", ".join(cat_items) if isinstance(cat_items, list) else str(cat_items)
        txt = f"&bull; <b>{_esc(cat_name)}:</b> {_esc(items_str)}"
        story.append(Paragraph(txt, bullet_style))

    # 4. Education
    if cv.get("education"):
        story.append(Paragraph("EDUCATION", heading_style))
        for edu in cv.get("education", []):
            inst_text = edu.get("institution", "")
            if edu.get("location"):
                inst_text += f" — {edu.get('location')}"
            story.append(Paragraph(_esc(inst_text), role_style))

            deg_text = edu.get("degree", "")
            if edu.get("field"):
                deg_text += f" in {edu.get('field')}"
            story.append(Paragraph(_esc(deg_text), subrole_style))

            dt_str = edu.get("date_display") or (f"{edu.get('start_date','')} – {edu.get('end_date','')}" if edu.get("start_date") else "")
            if dt_str:
                story.append(Paragraph(_esc(dt_str), date_style))

    # 5. Work Experience
    if cv.get("experience"):
        story.append(Paragraph("WORK EXPERIENCE", heading_style))
        for exp in cv.get("experience", []):
            co_text = exp.get("company", "")
            if exp.get("location"):
                co_text += f" — {exp.get('location')}"
            story.append(Paragraph(_esc(co_text), role_style))

            ti_text = exp.get("title", "")
            date_range = exp.get("date_range") or (f"{exp.get('start_date','')} – {exp.get('end_date','')}" if exp.get("start_date") else "")
            if date_range:
                ti_text += f" | {date_range}"
            story.append(Paragraph(_esc(ti_text), subrole_style))

            for bullet in exp.get("bullets", []):
                if ": " in bullet:
                    pref, rest = bullet.split(": ", 1)
                    txt = f"&bull; <b>{_esc(pref)}:</b> {_esc(rest)}"
                else:
                    txt = f"&bull; {_esc(bullet)}"
                story.append(Paragraph(txt, bullet_style))

    # 6. Selected Projects
    if cv.get("projects"):
        story.append(Paragraph("SELECTED AI & SOFTWARE PROJECTS", heading_style))
        for proj in cv.get("projects", []):
            pr_name = proj.get("name", "")
            techs = proj.get("technologies_header") or ", ".join(proj.get("technologies", []))
            header_text = f"{pr_name} | {techs}" if techs else pr_name
            story.append(Paragraph(_esc(header_text), role_style))

            for bullet in proj.get("bullets", []):
                txt = f"&bull; {_esc(bullet)}"
                story.append(Paragraph(txt, bullet_style))

    doc.build(story)
    pdf_data = buf.getvalue()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_data)

    return pdf_data


_FOLLOW_UP_PROMPT = """
You are a career communications specialist helping {candidate_name} write a professional follow-up email regarding a job application.

Candidate Profile:
- Name: {candidate_name}
- Email: {candidate_email}
- Background: {candidate_summary}

Job Application Details:
- Company: {company}
- Position: {job_title}
- Application Date: {applied_date}
- Job Context: {description}

Instructions:
1. Write a polite, concise, and professional follow-up email in English (approx. 120-160 words).
2. Include a clear subject line: "Subject: Follow-up: Application for {job_title} - {candidate_name}".
3. Acknowledge that the recruitment team is likely reviewing many candidates.
4. Reiterate enthusiasm for {company} and briefly mention how the candidate's background aligns with the team's needs.
5. Inquire if any additional information or portfolio samples are needed.
6. Close professionally with the candidate's contact information.
7. Return ONLY the plain text email (no markdown code blocks, no greetings to the user).
"""


def generate_follow_up_email(
    job_title: str,
    job_company: str,
    applied_date: str,
    job_description: str = "",
    cv: dict | None = None,
) -> str:
    """Generate a tailored, professional follow-up email for a pending job application."""
    if cv is None:
        try:
            cv = _load_master_cv()
        except Exception:
            cv = {}

    pers = cv.get("personal", {})
    cand_name = pers.get("name") or "Candidate"
    cand_email = pers.get("email", "")
    cand_summary = cv.get("summary", "Software Engineering & Data Analytics student")

    prompt = _FOLLOW_UP_PROMPT.format(
        candidate_name=cand_name,
        candidate_email=cand_email,
        candidate_summary=cand_summary[:300],
        company=job_company,
        job_title=job_title,
        applied_date=applied_date or "recently",
        description=job_description[:1500] if job_description else "",
    )

    logger.info("Generating follow-up email for %s @ %s", job_title, job_company)
    response = generate_content_with_fallback(prompt)
    return response.text.strip()


_JOB_ANALYSIS_PROMPT = """You are an elite career advisor and technical recruiter evaluating a candidate's fit for a specific job posting.

CANDIDATE PROFILE:
{cv_summary}

JOB POSTING:
Position: {job_title}
Company: {job_company}
Full Description:
{job_description}

CRITICAL INSTRUCTIONS:
1. Carefully analyze what this job REALLY requires (e.g. is it coding/backend, product operations, data analysis, AI tool usage, or business research?). Do NOT hallucinate skills that aren't asked for (e.g. do not claim "Go" programming language is required if the text only mentions "Go-to-Market").
2. Compare the real job requirements against the candidate's actual qualifications in education (Master's in Data Analytics & AI), technical skills (Python, SQL, Generative AI, RAG), and projects.
3. Return ONLY a valid JSON object with the following structure (no markdown fences, no explanatory prefix):
{{
  "role_summary": "1-2 sentence description in Turkish of the real core focus of this role (e.g. 'Ürün operasyonları ve iş verisi odaklı bir rol; yazılım mühendisliği aranmıyor, veri analitiği ve AI araçları kullanımı bekleniyor.')",
  "match_score": 85,
  "required_skills": [
    {{"skill": "Skill or Domain Name", "status": "matched", "explanation": "Brief explanation in Turkish comparing job need vs candidate's background"}}
  ],
  "key_strengths": [
    "Specific strength from candidate's CV directly matching the role"
  ],
  "missing_areas": [
    "Specific area the candidate should address, study, or highlight in their application"
  ],
  "strategic_advice": "Actionable 2-3 sentence strategic advice in Turkish on how the candidate should position their application for maximum interview conversion."
}}
"""


def analyze_job_with_gemini(
    job_title: str,
    job_company: str,
    job_description: str,
    cv: dict | None = None,
) -> dict:
    """
    Perform deep LLM-based skill gap and role analysis using Gemini.
    Provides semantic understanding far beyond static keyword matching.
    """
    if cv is None:
        cv = _load_cv()

    cv_summary_text = _cv_summary(cv)

    prompt = _JOB_ANALYSIS_PROMPT.format(
        cv_summary=cv_summary_text,
        job_title=job_title,
        job_company=job_company,
        job_description=job_description.strip() if job_description else "(No description provided)",
    )

    logger.info("Performing Gemini Deep Analysis for %s @ %s", job_title, job_company)
    config = genai.types.GenerationConfig(
        temperature=0.2,
        max_output_tokens=2048,
        response_mime_type="application/json",
    )
    try:
        response = generate_content_with_fallback(prompt, generation_config=config)
    except Exception:
        response = generate_content_with_fallback(prompt)

    raw_text = response.text.strip() if response and response.text else "{}"
    data = extract_json_from_text(raw_text)
    if not data:
        data = {
            "role_summary": f"{job_title} pozisyonu ({job_company})",
            "match_score": 60,
            "required_skills": [],
            "key_strengths": ["Analitik ve mühendislik altyapısı"],
            "missing_areas": [],
            "strategic_advice": "İlan gereksinimlerini CV'nizdeki somut projelerle destekleyerek başvurun.",
        }
    return data


