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
5. Suggest a 2-sentence professional summary tailored to this specific role.

Format your response EXACTLY like this:

🎯 ATS KEYWORDS TO INCLUDE:
[comma-separated list]

📋 TAILORED PROFESSIONAL SUMMARY:
[2 sentences]

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


# ─── Save to .docx ────────────────────────────────────────────────────────────
def save_cover_letter_docx(text: str, job: Job) -> Path:
    """Save a cover letter string to a .docx file and return its path."""
    try:
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        cv = _load_cv()
        author = cv.get("personal", {}).get("name", "Applicant")

        doc = Document()
        style = doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(11)

        # Header
        header = doc.add_paragraph()
        header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run = header.add_run(author)
        run.bold = True

        doc.add_paragraph()  # Spacer

        # Body
        for paragraph in text.split("\n\n"):
            p = doc.add_paragraph(paragraph.strip())
            p.paragraph_format.space_after = Pt(8)

        # Save
        safe_company = "".join(c for c in job.company if c.isalnum() or c in " _-")[:30]
        filename = f"CoverLetter_{safe_company}_{job.job_id}.docx"
        path = OUTPUT_DIR / filename
        doc.save(path)
        logger.info("Saved cover letter to %s", path)
        return path
    except ImportError:
        logger.error("python-docx not installed. Run: pip install python-docx")
        raise


# ─── CV Optimization for Dashboard ───────────────────────────────────────────

_OPTIMIZE_PROMPT = """
You are a senior ATS optimization expert and technical resume writer.

TASK: Rewrite the applicant's experience bullet points to better match the target job.
Focus ONLY on naturally integrating the missing skills — do not fabricate experience.

APPLICANT PROFILE (JSON):
{cv_json}

TARGET JOB:
Title: {job_title}
Company: {company}
Description:
{description}

SKILLS ALREADY IN CV: {found_skills}
SKILLS MISSING FROM CV (integrate naturally where truthful): {missing_skills}

INSTRUCTIONS:
1. Rewrite ONLY the experience and project bullet points that can be truthfully enhanced.
2. Naturally weave in missing skills where the underlying work already implies them.
   (e.g. if they built a REST API, they used CI/CD concepts — it's fair to mention it)
3. Keep all facts 100% accurate — do not invent experience.
4. Use strong action verbs and quantify where possible.
5. Format output as JSON with this exact structure:
{{
  "optimized_experience": [
    {{
      "role": "Job Title @ Company",
      "bullets": ["bullet 1", "bullet 2", ...]
    }}
  ],
  "optimized_projects": [
    {{
      "name": "Project Name",
      "bullets": ["bullet 1", "bullet 2", ...]
    }}
  ],
  "estimated_new_score": 85,
  "optimization_notes": "Brief explanation of what was improved"
}}

Return ONLY valid JSON. No markdown fences, no extra text.
"""


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
    response = _get_model().generate_content(prompt)
    raw = response.text.strip()

    # Strip markdown fences if model adds them
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    return json.loads(raw)


# ─── Follow-Up Email Generator ────────────────────────────────────────────────
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


import re  # noqa: E402

