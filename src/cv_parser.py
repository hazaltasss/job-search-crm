"""
CV Document Parser & AI Extraction Engine.
Extracts raw text from PDF/DOCX and converts it into structured candidate profiles using Gemini.
"""
from __future__ import annotations
import io
import json
import logging
from pathlib import Path

import google.generativeai as genai
from docx import Document
import pypdf

from src.config import GEMINI_API_KEY
from src.ai_assistant import extract_json_from_text

logger = logging.getLogger(__name__)

_PARSE_CV_PROMPT = """
You are an expert technical resume parser and career data strategist.
TASK: Analyze the following raw CV/Resume text and extract all details into a structured JSON profile.

RAW CV TEXT:
{raw_text}

INSTRUCTIONS:
1. Extract personal details (name, email, phone, location, linkedin, github).
2. Extract or summarize a professional summary (3-4 impactful sentences).
3. Extract all education entries with institution, degree, field, location, and graduation date.
4. Extract work experience entries with title, company, location, dates, and bullet points. Preserve bold topic prefixes if present (e.g. "Backend Development: ...").
5. Extract projects with name, tech stack, description, and bullets.
6. Extract skills into structured categories: programming_languages, generative_ai_and_llms, backend_and_systems, core_competencies, tools, and soft_skills.
7. Output MUST match this JSON structure:
{{
  "personal": {{
    "name": "Full Name",
    "email": "email@domain.com",
    "phone": "+49 ...",
    "location": "City, Country",
    "linkedin": "LinkedIn URL or Link",
    "github": "GitHub URL or Link",
    "portfolio": ""
  }},
  "summary": "Professional summary...",
  "education": [
    {{
      "institution": "University Name",
      "location": "City, Country",
      "degree": "Degree (e.g. Master of Science (M.Sc.))",
      "field": "Field of Study",
      "date_display": "July 2026 – July 2028 or Graduated: 2024",
      "start_date": "2024-09",
      "end_date": "2026-07"
    }}
  ],
  "experience": [
    {{
      "title": "Role Title",
      "company": "Company Name",
      "location": "City, Country",
      "type": "Full-time / Internship / Working Student",
      "date_range": "June 2024 – August 2024",
      "start_date": "2024-06",
      "end_date": "2024-08",
      "bullets": [
        "Prefix: Action taken and quantified outcome...",
        "..."
      ]
    }}
  ],
  "projects": [
    {{
      "name": "Project Name",
      "technologies_header": "Tech 1, Tech 2, Tech 3",
      "technologies": ["Tech 1", "Tech 2"],
      "description": "Brief project description",
      "bullets": [
        "Engineered...",
        "..."
      ]
    }}
  ],
  "skills": {{
    "programming_languages": ["Python", "SQL"],
    "generative_ai_and_llms": ["RAG", "LLMs"],
    "backend_and_systems": ["FastAPI", "Docker"],
    "core_competencies": ["Data Structures", "OOP"],
    "tools": ["Git", "Postman"],
    "soft_skills": ["Problem Solving", "Collaboration"]
  }},
  "languages": [
    {{"language": "English", "level": "Fluent"}},
    {{"language": "German", "level": "Intermediate"}}
  ]
}}

Return ONLY valid JSON.
"""


def extract_text_from_upload(file_bytes: bytes, filename: str) -> str:
    """Extract raw text from PDF, DOCX, or TXT file bytes."""
    fname = filename.lower()
    text_chunks: list[str] = []

    try:
        if fname.endswith(".pdf"):
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_chunks.append(page_text)

        elif fname.endswith(".docx"):
            doc = Document(io.BytesIO(file_bytes))
            for p in doc.paragraphs:
                if p.text.strip():
                    text_chunks.append(p.text.strip())
            for table in doc.tables:
                for row in table.rows:
                    row_txt = " | ".join(c.text.strip() for c in row.cells if c.text.strip())
                    if row_txt:
                        text_chunks.append(row_txt)

        else:
            text_chunks.append(file_bytes.decode("utf-8", errors="replace"))

    except Exception as exc:
        logger.error("Failed to extract text from %s: %s", filename, exc)
        raise ValueError(f"Could not read file {filename}: {exc}")

    full_text = "\n\n".join(text_chunks).strip()
    if not full_text:
        raise ValueError(f"Uploaded file {filename} appears to be empty or image-only.")
    return full_text


def normalize_parsed_cv(raw_dict: dict) -> dict:
    """Ensure all required profile keys exist with proper types and defaults."""
    normalized = dict(raw_dict)

    # 1. Personal
    personal = normalized.get("personal")
    if not isinstance(personal, dict):
        personal = {}
    personal.setdefault("name", "Candidate")
    personal.setdefault("email", "")
    personal.setdefault("phone", "")
    personal.setdefault("location", "")
    personal.setdefault("linkedin", "")
    personal.setdefault("github", "")
    personal.setdefault("portfolio", "")
    normalized["personal"] = personal

    # 2. Summary
    if not isinstance(normalized.get("summary"), str):
        normalized["summary"] = ""

    # 3. Education
    education = normalized.get("education")
    if not isinstance(education, list):
        education = []
    normalized["education"] = education

    # 4. Experience
    experience = normalized.get("experience")
    if not isinstance(experience, list):
        experience = []
    for exp in experience:
        if isinstance(exp, dict) and "bullets" not in exp:
            exp["bullets"] = []
    normalized["experience"] = experience

    # 5. Projects
    projects = normalized.get("projects")
    if not isinstance(projects, list):
        projects = []
    for proj in projects:
        if isinstance(proj, dict):
            proj.setdefault("bullets", [])
            proj.setdefault("technologies", [])
    normalized["projects"] = projects

    # 6. Skills
    skills = normalized.get("skills")
    if not isinstance(skills, dict):
        skills = {}
    for cat in [
        "programming_languages",
        "generative_ai_and_llms",
        "backend_and_systems",
        "core_competencies",
        "tools",
        "soft_skills",
    ]:
        if not isinstance(skills.get(cat), list):
            skills[cat] = []
    normalized["skills"] = skills

    # 7. Languages
    languages = normalized.get("languages")
    if not isinstance(languages, list):
        languages = []
    normalized["languages"] = languages

    return normalized


def parse_cv_with_gemini(raw_text: str) -> dict:
    """Use Gemini Flash to parse raw CV text into a normalized candidate profile dict."""
    if not GEMINI_API_KEY:
        raise EnvironmentError("GEMINI_API_KEY is not configured.")

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-3.6-flash")

    prompt = _PARSE_CV_PROMPT.format(raw_text=raw_text[:6000])

    try:
        config = genai.types.GenerationConfig(
            temperature=0.1,
            max_output_tokens=4096,
            response_mime_type="application/json",
        )
        response = model.generate_content(prompt, generation_config=config)
    except Exception as exc:
        logger.warning("Gemini parse with application/json failed (%s), using fallback config", exc)
        response = model.generate_content(prompt)

    raw_json_str = response.text.strip() if (response and response.text) else "{}"
    parsed = extract_json_from_text(raw_json_str)
    return normalize_parsed_cv(parsed)
