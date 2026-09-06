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

import google.generativeai as genai

from src.config import GEMINI_API_KEY, MASTER_CV_PATH, OUTPUT_DIR
from src.models import Job

logger = logging.getLogger(__name__)

# ─── Gemini Setup (lazy — configured on first use) ────────────────────────────
_model_instance = None

def _get_model():
    global _model_instance
    if _model_instance is None:
        if not GEMINI_API_KEY:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. Add it to your .env file.\n"
                "Get a free key at: https://aistudio.google.com/app/apikey"
            )
        genai.configure(api_key=GEMINI_API_KEY)
        _model_instance = genai.GenerativeModel(
            model_name="gemini-3.6-flash",
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                top_p=0.9,
                max_output_tokens=2048,
            ),
        )
    return _model_instance


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
You are an expert career coach and professional writer. Generate a tailored, compelling
cover letter in ENGLISH for the following job application.

APPLICANT PROFILE:
{cv_summary}

TARGET JOB:
Title: {job_title}
Company: {company}
Location: {location}
Job Description:
{description}

INSTRUCTIONS:
1. Write a professional, warm, and confident cover letter (3-4 paragraphs, ~300 words).
2. Personalize it: mention the company name and specific role.
3. Highlight the most relevant skills and experiences from the applicant's profile that match the job.
4. Use natural, modern language. Avoid clichés.
5. End with a confident call-to-action.
6. Format it ready to send (no placeholders left).
7. Do NOT include subject line or email headers — just the letter body.

Output only the cover letter text, starting with "Dear Hiring Team at {company}," or similar.
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
        description=job.description[:3000] if job.description else "(See job URL)",
    )

    logger.info("Generating cover letter for: %s @ %s", job.title, job.company)
    response = _get_model().generate_content(prompt)
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
    response = _get_model().generate_content(prompt)
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
    story.append(Paragraph(_esc(pers.get("name", "HAZAL TAŞ").upper()), name_style))

    contacts = [
        pers.get("location", "Berlin, Germany"),
        pers.get("phone", "+49 155 1098 2021"),
        pers.get("email", "hazaltas.623@gmail.com"),
        pers.get("linkedin", "[LinkedIn Profile Link]"),
        pers.get("github", "[GitHub Profile Link]"),
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
    r_name = p_name.add_run(pers.get("name", "HAZAL TAŞ").upper())
    r_name.bold = True
    r_name.font.size = Pt(16)
    r_name.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

    # Contact
    p_con = doc.add_paragraph()
    contacts = [
        pers.get("location", "Berlin, Germany"),
        pers.get("phone", "+49 155 1098 2021"),
        pers.get("email", "hazaltas.623@gmail.com"),
        pers.get("linkedin", "[LinkedIn Profile Link]"),
        pers.get("github", "[GitHub Profile Link]"),
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
You are a senior ATS optimization expert and technical resume writer.

TASK: Tailor the applicant's resume for the target job while keeping all facts 100% truthful.
1. Tailor the 2-3 sentence PROFESSIONAL SUMMARY to highlight the candidate's technical profile, educational foundation, and domain expertise relevant to this target role.
2. Rewrite the experience and project bullet points to naturally integrate the missing skills where the underlying work already implies them.

CRITICAL RULES FOR PROFESSIONAL SUMMARY (CV / RESUME):
- This summary goes onto an ATS CV / Resume, NOT a Cover Letter.
- STRICTLY FORBIDDEN: NEVER mention the target company name ({company}) in the summary or anywhere in the CV.
- STRICTLY FORBIDDEN: NEVER write subjective, personal motivational statements about wanting to work with, join, or contribute to this specific company (e.g., do NOT write "Highly motivated to contribute within {company}...", "Seeking to join {company}", "Excited to work at {company}"). Cover-letter style declarations belong ONLY in a cover letter!
- The professional summary must remain 100% company-agnostic, objective, and professional: focus purely on Hazal's technical identity (Computer Engineer and M.Sc. student in Data Analytics & AI), core competencies, relevant technical stack (e.g., Python, SQL, data pipelines, schema design, CI/CD), and engineering capabilities aligned with the role's domain.

APPLICANT PROFILE (JSON):
{cv_json}

TARGET JOB:
Title: {job_title}
Target Domain / Context: (Company name must NOT be mentioned in the CV)
Description:
{description}

SKILLS ALREADY IN CV: {found_skills}
SKILLS MISSING FROM CV (integrate naturally where truthful): {missing_skills}

INSTRUCTIONS:
1. PROFESSIONAL SUMMARY:
   - 2 to 3 sentences in formal CV style.
   - Company-agnostic: NEVER mention {company}.
   - No cover-letter motivational declarations ("motivated to contribute at...", "seeking to join...", etc.).
   - Highlight candidate's technical profile, academic foundation (M.Sc. Data Analytics & AI, B.Sc. Computer Engineering), and relevant technical capabilities matching the position's requirements.
2. Rewrite ONLY the experience and project bullet points that can be truthfully enhanced.
3. Naturally weave in missing skills where the underlying work already implies them.
4. Keep all facts 100% accurate — do NOT invent companies, dates, degrees, or fictional experience.
5. Use strong action verbs and quantify where possible. Preserve bullet label prefixes where applicable (e.g. "API & Backend Development: ...").
6. Format output as JSON with this exact structure:
{{
  "tailored_summary": "Objective 2-3 sentence technical professional summary. Strictly NO company names and NO motivational 'seeking to join' statements.",
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
  "estimated_new_score": 88,
  "optimization_notes": "Brief explanation of what was improved"
}}

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
        description=job_description[:2500] if job_description else "(See job URL)",
        found_skills=", ".join(found_skills[:15]) or "none detected",
        missing_skills=", ".join(missing_skills[:15]) or "none",
    )

    logger.info("Optimizing CV for: %s @ %s", job_title, job_company)

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
            response = _get_model().generate_content(prompt, generation_config=config)
        except Exception as api_err:
            logger.warning("Generation with response_mime_type failed (%s), falling back to default", api_err)
            response = _get_model().generate_content(prompt)

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

            # Ensure keys exist with sensible defaults
            data.setdefault("optimized_experience", [])
            data.setdefault("optimized_projects", [])
            data.setdefault("estimated_new_score", 85)
            data.setdefault("optimization_notes", "")

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
        response = _get_model().generate_content(prompt, generation_config=config)
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
    """Construct prompt for the CV Copilot conversational assistant."""
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
The candidate is reviewing and interactively editing their tailored CV for a specific target job.

TARGET JOB:
Title: {job_title}
Company: {company}
Description: {description[:2000] if description else '(Not specified)'}

CURRENT CV WORKING STATE (JSON):
{json.dumps(compact_cv, ensure_ascii=False, indent=2)}

RECENT CHAT HISTORY:
{history_str}

CANDIDATE'S EDIT REQUEST:
"{user_prompt}"

INSTRUCTIONS:
1. Carefully interpret what the candidate wants to modify in their CV (e.g. adjusting a specific bullet, adding a technology, shortening the summary, rephrasing a project).
2. Modify ONLY the requested parts of the CV working state while keeping everything else intact.
3. Keep all factual experience 100% accurate — do not invent degrees or fictional companies.
4. If the candidate asks a question or makes an edit, provide a friendly, helpful 1-2 sentence explanation of what was updated.
5. Format your output as JSON with this exact schema:
{{
  "updated_cv": {{
    "summary": "...",
    "experience": [ ... ],
    "projects": [ ... ]
  }},
  "assistant_message": "A concise explanation in Turkish of what was modified (e.g. 'Softtech deneyimindeki 2. madde Docker ve CI/CD odaklı olarak güncellendi.')"
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
    Process candidate's conversational instruction, modify the current CV state,
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
        response = _get_model().generate_content(prompt, generation_config=config)
    except Exception as exc:
        logger.warning("Copilot with response_mime_type failed (%s), using fallback", exc)
        response = _get_model().generate_content(prompt)

    raw_text = response.text.strip() if (response and response.text) else "{}"
    try:
        parsed = extract_json_from_text(raw_text)
        updated_part = parsed.get("updated_cv", {})
        msg = parsed.get("assistant_message", "CV belirtilen doğrultuda güncellendi.")

        new_cv = json.loads(json.dumps(current_cv))
        if "summary" in updated_part and isinstance(updated_part["summary"], str) and len(updated_part["summary"]) > 10:
            new_cv["summary"] = updated_part["summary"]
        if "experience" in updated_part and isinstance(updated_part["experience"], list) and updated_part["experience"]:
            new_cv["experience"] = updated_part["experience"]
        if "projects" in updated_part and isinstance(updated_part["projects"], list) and updated_part["projects"]:
            new_cv["projects"] = updated_part["projects"]

        return new_cv, msg

    except Exception as exc:
        logger.error("Failed to parse Copilot response: %s (Raw: %s)", exc, raw_text[:200])
        return current_cv, "Üzgünüm, isteğinizi uygularken bir sorun oluştu. Lütfen tekrar deneyin."


def generate_cv_docx(cv: dict, output_path: Path | None = None) -> bytes:
    """
    Generate an ATS-compliant, professionally styled Word (.docx) document
    matching the layout, typography, and structure of Hazal's base CV.
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
    name_run = p_name.add_run(cv.get("personal", {}).get("name", "HAZAL TAŞ").upper())
    name_run.bold = True
    name_run.font.size = Pt(18)
    name_run.font.color.rgb = RGBColor(0x0F, 0x17, 0x2A)

    # Contact line
    p_contact = doc.add_paragraph()
    p_contact.paragraph_format.space_before = Pt(0)
    p_contact.paragraph_format.space_after = Pt(7)
    pers = cv.get("personal", {})
    contacts = [
        pers.get("location", "Berlin, Germany"),
        pers.get("phone", "+49 155 1098 2021"),
        pers.get("email", "hazaltas.623@gmail.com"),
        pers.get("linkedin", "[LinkedIn Profile Link]"),
        pers.get("github", "[GitHub Profile Link]"),
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
    matching the layout, typography, and structure of Hazal's base CV.
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
    story.append(Paragraph(_esc(cv.get("personal", {}).get("name", "HAZAL TAŞ").upper()), name_style))

    pers = cv.get("personal", {})
    contacts = [
        pers.get("location", "Berlin, Germany"),
        pers.get("phone", "+49 155 1098 2021"),
        pers.get("email", "hazaltas.623@gmail.com"),
        pers.get("linkedin", "[LinkedIn Profile Link]"),
        pers.get("github", "[GitHub Profile Link]"),
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
You are a career communications specialist helping Hazal Taş write a professional follow-up email regarding her job application in Berlin, Germany.

Candidate Profile:
- Name: Hazal Taş
- Email: hazaltas.623@gmail.com
- Degree: M.Sc. in Data Analytics & AI at Steinbeis University, Berlin
- Background: Computer Engineer with practical experience in Python, Generative AI, RAG pipelines, API development

Job Application Details:
- Company: {company}
- Position: {job_title}
- Application Date: {applied_date}
- Job Context: {description}

Instructions:
1. Write a polite, concise, and professional follow-up email in English (approx. 120-160 words).
2. Include a clear subject line: "Subject: Follow-up: Application for {job_title} - Hazal Taş".
3. Acknowledge that the recruitment team is likely reviewing many candidates.
4. Reiterate enthusiasm for {company} and briefly mention how Hazal's background in Data Analytics & AI aligns with the team's needs.
5. Inquire if any additional information or portfolio samples are needed.
6. Close professionally with contact information.
7. Return ONLY the plain text email (no markdown code blocks, no greetings to the user).
"""


def generate_follow_up_email(
    job_title: str,
    job_company: str,
    applied_date: str,
    job_description: str = "",
) -> str:
    """Generate a tailored, professional follow-up email for a pending job application."""
    prompt = _FOLLOW_UP_PROMPT.format(
        company=job_company,
        job_title=job_title,
        applied_date=applied_date or "recently",
        description=job_description[:1500] if job_description else "",
    )

    logger.info("Generating follow-up email for %s @ %s", job_title, job_company)
    response = _get_model().generate_content(prompt)
    return response.text.strip()

