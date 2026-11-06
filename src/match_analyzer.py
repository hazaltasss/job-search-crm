"""
Match Analyzer: CV vs job description skill gap analysis.

master_cv.json dosyasındaki tüm skill ve deneyim metinlerini
bir ilanın gereksinimlerine karşı kıyaslar.
Çıktı: match score (0-100), bulunan beceriler, eksik beceriler.
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from src.config import MASTER_CV_PATH

# ─── Structured Tech Taxonomy & Categorization ─────────────────────────────────
TECH_TAXONOMY: dict[str, list[str]] = {
    "Programming & Backend": [
        "python", "sql", "java", "javascript", "typescript", "c++", "c#", "go", "golang",
        "rust", "kotlin", "swift", "dart", "scala", "r", "matlab", "bash", "bash scripting",
        "fastapi", "flask", "django", "spring boot", "spring", "node.js", "express",
        "react", "angular", "vue", "next.js", "rest api", "graphql", "microservices",
    ],
    "AI, LLM & Machine Learning": [
        "pytorch", "tensorflow", "keras", "scikit-learn", "sklearn",
        "langchain", "llm", "rag", "hugging face", "transformers", "openai", "gemini",
        "vector database", "embeddings", "pinecone", "chromadb", "weaviate", "qdrant",
        "nlp", "machine learning", "deep learning", "computer vision", "time series",
        "mlops", "model deployment", "xgboost", "lightgbm",
        "ai tools", "generative ai", "prompt engineering", "agentic workflows", "multimodal ai",
    ],
    "Data Engineering & Cloud": [
        "docker", "kubernetes", "aws", "azure", "gcp", "google cloud",
        "terraform", "ansible", "ci/cd", "github actions", "jenkins", "linux",
        "spark", "airflow", "dbt", "kafka", "flink", "databricks",
        "etl", "data pipeline", "data warehouse", "snowflake", "bigquery",
        "redshift", "duckdb", "polars", "pandas", "numpy",
        "postgresql", "mysql", "mongodb", "redis", "sqlite", "elasticsearch",
    ],
    "BI, Analytics & Tools": [
        "power bi", "tableau", "excel", "advanced excel", "looker", "looker studio",
        "metabase", "matplotlib", "seaborn", "plotly", "streamlit",
        "statistics", "statistical analysis", "a/b testing", "data modeling",
        "data analysis", "data analytics", "business intelligence",
    ],
    "Product, Business & Operations": [
        "product management", "business operations", "business management", "market research",
        "competitor analysis", "competitor research", "stakeholder management", "stakeholders",
        "cross-functional collaboration", "cross-functional", "process optimization",
        "presentations", "presentation", "analytical thinking", "analytical skills",
        "kpi", "crm", "salesforce", "hubspot",
    ],
    "QA & Software Testing": [
        "qa", "quality assurance", "software testing", "software tester", "test automation",
        "manual testing", "test case", "test cases", "cypress", "playwright", "selenium",
        "regression testing", "api testing", "postman", "swagger", "openapi", "unit testing",
        "pytest", "bug reporting", "test execution",
    ],
    "IT & Technical Support": [
        "technical support", "tech support", "it support", "application support", "helpdesk",
        "it helpdesk", "troubleshooting", "customer support", "saas support",
        "jira service desk", "incident management",
    ],
    "Methodologies & Practices": [
        "agile", "scrum", "kanban", "jira", "confluence", "notion",
        "git", "github", "gitlab", "postman", "swagger", "openapi",
        "unit testing", "pytest", "oop", "object-oriented programming",
        "data structures", "algorithms",
    ],
}

# Generic noise keywords to exclude from hard technology rankings in charts
GENERIC_NOISE_TERMS: set[str] = {
    "reporting", "dashboard", "dashboards",
    "pricing", "forecasting", "crm", "sap", "salesforce",
    "communication", "teamwork",
}

# ─── Contextual Regex Patterns for Ambiguous / Polysemous Words ────────────────
# Eliminates false positives like "Go-to-Market" -> Go, "R&D" -> R, "Spring 2026" -> Spring
CUSTOM_SKILL_PATTERNS: dict[str, re.Pattern] = {
    "go": re.compile(
        r"\b(?:golang|go\s+lang(?:uage)?|(?:backend|developer|engineer|programming)\s+in\s+go\b|go\s*[/,]\s*(?:python|java|c\+\+|rust|ruby|kotlin|scala|c#)\b|(?:python|java|c\+\+|rust|ruby|kotlin|scala|c#)\s*[/,]\s*go\b)\b",
        re.IGNORECASE,
    ),
    "r": re.compile(
        r"\b(?:r\s+lang(?:uage)?|r\s+programming|r\s+studio|rstudio|(?:python|sql|matlab|sas|spss)\s*[/,]\s*r\b|\br\s*[/,]\s*(?:python|sql|matlab|sas|spss))\b",
        re.IGNORECASE,
    ),
    "spring": re.compile(
        r"\b(?:spring\s+(?:boot|framework|mvc|cloud|data|security|batch)|spring-boot)\b",
        re.IGNORECASE,
    ),
    "spark": re.compile(
        r"\b(?:apache\s+spark|pyspark|spark\s+(?:streaming|sql|core|dataframe|cluster|job|processing))\b",
        re.IGNORECASE,
    ),
    "excel": re.compile(
        r"\b(?:ms\s*excel|microsoft\s*excel|advanced\s*excel|excel\s+(?:vba|macros?|formulas?|spreadsheets?|pivot|tables?|skills?)|(?:power\s*bi|tableau|sql|python|word|powerpoint|office|sheets)\s*[/,]\s*excel\b|\bexcel\s*[/,]\s*(?:power\s*bi|tableau|sql|python|word|powerpoint|office|sheets))\b|(?<!\bwill\s)(?<!\bto\s)(?<!\bcan\s)(?<!\byou\s)\bexcel\b(?!\s+(?:at|in|beyond)\b)",
        re.IGNORECASE,
    ),
    "express": re.compile(
        r"\b(?:express\.js|expressjs|express\s+framework|(?:node|nodejs|node\.js)\s*[/,]\s*express\b|\bexpress\s*[/,]\s*(?:node|nodejs|node\.js))\b",
        re.IGNORECASE,
    ),
    "react": re.compile(
        r"\b(?:react\.js|reactjs|react\s+native|react\s+(?:developer|frontend|library|components?)|(?:react|angular|vue)\s*[/,]\s*(?:react|angular|vue)|(?<!\bto\s)(?<!\bcan\s)\breact\b(?!\s+(?:to|quickly|promptly|under)\b))\b",
        re.IGNORECASE,
    ),
    "cross-functional": re.compile(
        r"\bcross[- ]functional(?:\s+collaboration|\s+teams?|\s+projects?)?\b",
        re.IGNORECASE,
    ),
    "competitor analysis": re.compile(
        r"\b(?:competitor|competition)\s+(?:research|analysis|insights)\b|\bmarket\s*,\s*(?:customer\s+and\s+)?competitor\s+research\b",
        re.IGNORECASE,
    ),
    "market research": re.compile(
        r"\bmarket\s+(?:research|analysis|insights)\b|\bmarket\s*,\s*(?:customer\s+and\s+)?competitor\s+research\b",
        re.IGNORECASE,
    ),
    "stakeholder management": re.compile(
        r"\bstakeholders?(?:\s+management|\s+communication|\s+alignment)?\b",
        re.IGNORECASE,
    ),
    "presentations": re.compile(
        r"\bpresentations?\b|\bpresentation\s+skills?\b",
        re.IGNORECASE,
    ),
    "analytical thinking": re.compile(
        r"\banalytical\s+(?:thinking|skills?|mindset)\b|\banalytical\s+and\s+structured\b",
        re.IGNORECASE,
    ),
}

# ─── Canonical Skill Normalization Map ─────────────────────────────────────────
CANONICAL_SKILL_MAP: dict[str, str] = {
    # Data & Analytics
    "data analysis": "Data Analytics",
    "data analytics": "Data Analytics",
    "data analyst": "Data Analytics",
    "business analytics": "Data Analytics",
    "business intelligence": "BI",
    "bi": "BI",
    "data modeling": "Data Modeling",
    "statistics": "Statistics",
    "statistical analysis": "Statistics",
    "a/b testing": "A/B Testing",

    # AI & ML
    "artificial intelligence": "AI & Generative Tools",
    "ai": "AI & Generative Tools",
    "ai tools": "AI & Generative Tools",
    "generative ai": "AI & Generative Tools",
    "prompt engineering": "Prompt Engineering",
    "agentic workflows": "Agentic Workflows",
    "multimodal ai": "Multimodal AI",
    "machine learning": "Machine Learning",
    "ml": "Machine Learning",
    "deep learning": "Deep Learning",
    "dl": "Deep Learning",
    "natural language processing": "NLP",
    "nlp": "NLP",
    "large language models": "LLM",
    "large language model": "LLM",
    "llm": "LLM",
    "llms": "LLM",
    "retrieval augmented generation": "RAG",
    "retrieval-augmented generation": "RAG",
    "rag": "RAG",
    "vector database": "Vector Search & Databases",
    "vector databases": "Vector Search & Databases",
    "vector search": "Vector Search & Databases",

    # Programming & Frameworks
    "golang": "Go",
    "go": "Go",
    "bash scripting": "Bash",
    "bash": "Bash",
    "python": "Python",
    "sql": "SQL",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "react": "React",
    "react.js": "React",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "rest api": "REST APIs",
    "restful api": "REST APIs",
    "restful apis": "REST APIs",
    "rest apis": "REST APIs",
    "oop": "OOP",
    "object-oriented programming": "OOP",
    "ci/cd": "CI/CD",
    "ci cd": "CI/CD",
    "scikit-learn": "Scikit-Learn",
    "sklearn": "Scikit-Learn",
    "power bi": "Power BI",
    "powerbi": "Power BI",
    "spring": "Spring Boot",
    "spring boot": "Spring Boot",
    "apache spark": "Spark",
    "spark": "Spark",
    "excel": "Excel",
    "advanced excel": "Excel",

    # QA & Testing
    "qa": "QA & Software Testing",
    "quality assurance": "QA & Software Testing",
    "software testing": "QA & Software Testing",
    "software tester": "QA & Software Testing",
    "test automation": "Test Automation",
    "manual testing": "Manual Testing",
    "test case": "Test Cases",
    "test cases": "Test Cases",
    "api testing": "API Testing",
    "regression testing": "Regression Testing",
    "postman": "Postman",
    "swagger": "Swagger / OpenAPI",
    "openapi": "Swagger / OpenAPI",
    "pytest": "PyTest",
    "unit testing": "Unit Testing",
    "cypress": "Cypress",
    "playwright": "Playwright",
    "selenium": "Selenium",
    "bug reporting": "Bug Tracking & Reporting",

    # IT & Technical Support
    "technical support": "Technical Support",
    "tech support": "Technical Support",
    "it support": "IT Support",
    "application support": "Application Support",
    "helpdesk": "IT Helpdesk",
    "it helpdesk": "IT Helpdesk",
    "troubleshooting": "Troubleshooting & Diagnostics",
    "saas support": "SaaS Support",
    "jira service desk": "Jira Service Desk",

    # Product, Business & Operations
    "market research": "Market Research",
    "competitor research": "Competitor Analysis",
    "competitor analysis": "Competitor Analysis",
    "business operations": "Business Operations",
    "business management": "Business Operations",
    "product management": "Product Management",
    "product operations": "Product Management",
    "stakeholder management": "Stakeholder Management",
    "stakeholders": "Stakeholder Management",
    "cross-functional collaboration": "Cross-Functional Collaboration",
    "cross functional collaboration": "Cross-Functional Collaboration",
    "cross-functional": "Cross-Functional Collaboration",
    "analytical thinking": "Analytical Thinking",
    "analytical skills": "Analytical Thinking",
    "presentation": "Presentations & Reporting",
    "presentations": "Presentations & Reporting",
    "process optimization": "Process Optimization",
    "kpi": "KPIs & Performance Metrics",
}

# Flat list of all recognized skills for match scoring
_ALL_SKILLS: list[str] = list(dict.fromkeys(
    [skill for cat_skills in TECH_TAXONOMY.values() for skill in cat_skills] +
    list(GENERIC_NOISE_TERMS)
))

# Precompiled regex patterns
_SKILL_PATTERNS: dict[str, re.Pattern] = {}
for skill in _ALL_SKILLS:
    if skill in CUSTOM_SKILL_PATTERNS:
        _SKILL_PATTERNS[skill] = CUSTOM_SKILL_PATTERNS[skill]
    else:
        _SKILL_PATTERNS[skill] = re.compile(rf"\b{re.escape(skill)}\b", re.IGNORECASE)


@dataclass
class MatchResult:
    score: int                          # 0–100
    found_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    all_job_keywords: list[str] = field(default_factory=list)
    cv_skill_pool: set[str] = field(default_factory=set)


def _canonical_name(skill: str) -> str:
    """Return clean canonical display name for any skill variant."""
    return CANONICAL_SKILL_MAP.get(skill.lower(), skill.title())


def _extract_cv_skill_pool(cv: dict) -> set[str]:
    """
    CV'deki tüm metinlerden normalize edilmiş canonical skill seti oluşturur.
    Education (dereceler & dersler) + Skills bölümü + Experience + Projects + Summary dahil.
    """
    texts: list[str] = []

    # 1. Education bölümü (Master/B.Sc. alanları, relevant_courses, thesis)
    for edu in cv.get("education", []):
        if edu.get("degree"):
            texts.append(str(edu["degree"]).lower())
        if edu.get("field"):
            texts.append(str(edu["field"]).lower())
        if edu.get("institution"):
            texts.append(str(edu["institution"]).lower())
        for course in edu.get("relevant_courses", []):
            texts.append(str(course).lower())
        if edu.get("thesis"):
            texts.append(str(edu["thesis"]).lower())

    # 2. Skills bölümü (Tüm kategoriler)
    skills = cv.get("skills", {})
    for skill_list in skills.values():
        if isinstance(skill_list, list):
            texts.extend(str(s).lower() for s in skill_list)

    # 3. Experience bullet points & ünvanlar
    for exp in cv.get("experience", []):
        if exp.get("title"):
            texts.append(str(exp["title"]).lower())
        for bullet in exp.get("bullets", []):
            texts.append(str(bullet).lower())

    # 4. Projects (başlık, açıklama, teknolojiler, maddeler)
    for proj in cv.get("projects", []):
        if proj.get("name"):
            texts.append(str(proj["name"]).lower())
        if proj.get("description"):
            texts.append(str(proj["description"]).lower())
        for tech in proj.get("technologies", []):
            texts.append(str(tech).lower())
        for bullet in proj.get("bullets", []):
            texts.append(str(bullet).lower())

    # 5. Summary
    if cv.get("summary"):
        texts.append(str(cv["summary"]).lower())

    combined = " ".join(texts)

    pool: set[str] = set()
    for skill, pat in _SKILL_PATTERNS.items():
        if pat.search(combined):
            canonical = _canonical_name(skill)
            pool.add(canonical.lower())

    return pool


def _extract_job_keywords(description: str, title: str) -> list[str]:
    """İlan metninden geçen becerileri canonical formatta çıkarır."""
    text = f"{title}\n{description}"
    extracted_canonical: list[str] = []

    for skill, pat in _SKILL_PATTERNS.items():
        if pat.search(text):
            canonical = _canonical_name(skill)
            if canonical not in extracted_canonical:
                extracted_canonical.append(canonical)

    return extracted_canonical


def analyze_match(
    job_title: str,
    job_description: str,
    cv: dict | None = None,
) -> MatchResult:
    """
    İlan ile CV'yi karşılaştırır.
    Returns MatchResult with score, found/missing skills (canonical display names).
    """
    if cv is None:
        with open(MASTER_CV_PATH, "r", encoding="utf-8") as f:
            cv = json.load(f)

    cv_pool = _extract_cv_skill_pool(cv)
    job_keywords = _extract_job_keywords(job_description, job_title)

    if not job_keywords:
        return MatchResult(score=50, all_job_keywords=[], cv_skill_pool=cv_pool)

    found: list[str] = []
    missing: list[str] = []

    for kw in job_keywords:
        if kw.lower() in cv_pool:
            found.append(kw)
        else:
            missing.append(kw)

    score = int(len(found) / len(job_keywords) * 100) if job_keywords else 50

    return MatchResult(
        score=score,
        found_skills=found,
        missing_skills=missing,
        all_job_keywords=job_keywords,
        cv_skill_pool=cv_pool,
    )


# Map each skill to its taxonomy category
_SKILL_TO_CAT: dict[str, str] = {}
for _cat_name, _skills in TECH_TAXONOMY.items():
    for _s in _skills:
        if _s not in _SKILL_TO_CAT:
            _SKILL_TO_CAT[_s] = _cat_name

_FREQ_CACHE: dict = {}


def skill_frequency_from_db(
    descriptions: list[str],
    total_jobs: int,
    category: str = "Tüm Somut Teknolojiler",
) -> list[dict]:
    """
    İlan açıklamalarından kategorize edilmiş ve gürültüsü temizlenmiş beceri frekanslarını hesaplar.
    Returns: [{"skill": "Python", "category": "Programming & Backend", "count": 42, "pct": 85.0}, ...]
    """
    from collections import Counter

    category_map: dict[str, list[str]] = {
        "All Concrete Technologies": [
            "Programming & Backend",
            "AI, LLM & Machine Learning",
            "Data Engineering & Cloud",
            "BI, Analytics & Tools",
            "QA & Software Testing",
            "IT & Technical Support",
            "Product, Business & Operations",
        ],
        "Tüm Somut Teknolojiler": [
            "Programming & Backend",
            "AI, LLM & Machine Learning",
            "Data Engineering & Cloud",
            "BI, Analytics & Tools",
            "QA & Software Testing",
            "IT & Technical Support",
            "Product, Business & Operations",
        ],
        "🤖 AI & Machine Learning": ["AI, LLM & Machine Learning"],
        "🗄️ Data Engineering & Cloud": ["Data Engineering & Cloud"],
        "🗄️ Veri Mühendisliği & Cloud": ["Data Engineering & Cloud"],
        "💻 Programming & Backend": ["Programming & Backend"],
        "💻 Programlama & Backend": ["Programming & Backend"],
        "🧪 QA & Software Testing": ["QA & Software Testing"],
        "🎧 IT & Technical Support": ["IT & Technical Support"],
        "📊 BI & Data Analytics": ["BI, Analytics & Tools"],
        "📊 BI & Veri Analitiği": ["BI, Analytics & Tools"],
        "💼 Product & Operations": ["Product, Business & Operations"],
        "💼 Ürün & Operasyon": ["Product, Business & Operations"],
        "📋 Methodologies & Tools": ["Methodologies & Practices", "Product, Business & Operations"],
        "📋 Metodolojiler & İş Araçları": ["Methodologies & Practices", "Product, Business & Operations"],
    }

    active_cats = set(category_map.get(category, category_map["Tüm Somut Teknolojiler"]))
    allowed_skills = {
        s: _SKILL_TO_CAT[s]
        for s, cat in _SKILL_TO_CAT.items()
        if cat in active_cats and s not in GENERIC_NOISE_TERMS
    }

    # Fast cached single-pass counting across all skills
    cache_key = (len(descriptions), hash(descriptions[0]) if descriptions else 0, hash(descriptions[-1]) if descriptions else 0)
    if cache_key not in _FREQ_CACHE:
        all_counts: Counter = Counter()
        for desc in descriptions:
            text = desc.lower()
            for s, pat in _SKILL_PATTERNS.items():
                if s not in GENERIC_NOISE_TERMS and pat.search(text):
                    all_counts[s] += 1
        if len(_FREQ_CACHE) > 8:
            _FREQ_CACHE.clear()
        _FREQ_CACHE[cache_key] = all_counts
    else:
        all_counts = _FREQ_CACHE[cache_key]

    counter: Counter = Counter({s: all_counts[s] for s in allowed_skills if all_counts.get(s, 0) > 0})

    results = []
    # Standard capitalization for acronyms & known tech names
    ACRONYMS = {"sql", "aws", "gcp", "ci/cd", "llm", "rag", "nlp", "etl", "dbt", "bi", "oop", "kpi", "api", "rest api"}
    for skill, count in counter.most_common(25):
        pct = round(count / total_jobs * 100, 1) if total_jobs > 0 else 0.0
        display_name = skill.upper() if skill in ACRONYMS else skill.title()
        if skill == "power bi":
            display_name = "Power BI"
        elif skill == "scikit-learn":
            display_name = "Scikit-Learn"
        elif skill == "fastapi":
            display_name = "FastAPI"
        elif skill == "postgresql":
            display_name = "PostgreSQL"
        elif skill == "bigquery":
            display_name = "BigQuery"
        elif skill == "snowflake":
            display_name = "Snowflake"
        elif skill == "databricks":
            display_name = "Databricks"
        elif skill == "hugging face":
            display_name = "Hugging Face"
        elif skill == "github actions":
            display_name = "GitHub Actions"

        results.append({
            "skill": display_name,
            "category": allowed_skills[skill],
            "count": count,
            "pct": pct,
        })
    return results
