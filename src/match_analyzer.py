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

# Kapsamlı tech skill listesi — her biri normalize edilmiş
_ALL_SKILLS: list[str] = [
    # Programming languages
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "golang",
    "rust", "kotlin", "swift", "dart", "scala", "r", "matlab", "bash", "sql",
    # Web / Backend frameworks
    "fastapi", "flask", "django", "spring boot", "spring", "node.js", "express",
    "react", "angular", "vue", "next.js", "nuxt", "svelte", "html", "css",
    # Data & ML
    "pandas", "numpy", "scikit-learn", "sklearn", "tensorflow", "pytorch", "keras",
    "xgboost", "lightgbm", "hugging face", "transformers", "langchain", "openai",
    "gemini", "llm", "rag", "vector database", "embeddings", "nlp",
    "machine learning", "deep learning", "computer vision", "time series",
    "feature engineering", "mlops", "model deployment",
    # Data Engineering
    "spark", "airflow", "dbt", "kafka", "flink", "databricks",
    "etl", "data pipeline", "data warehouse", "snowflake", "bigquery",
    "redshift", "duckdb", "polars",
    # BI & Visualization
    "tableau", "power bi", "looker", "looker studio", "metabase",
    "matplotlib", "seaborn", "plotly", "streamlit",
    # Databases
    "postgresql", "mysql", "mongodb", "redis", "sqlite", "elasticsearch",
    "cassandra", "neo4j", "pinecone", "chromadb", "weaviate", "qdrant",
    # Cloud & DevOps
    "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "terraform",
    "ansible", "ci/cd", "github actions", "jenkins", "linux", "bash scripting",
    # Mobile
    "flutter", "android", "ios", "react native",
    # Tools & Practices
    "git", "github", "gitlab", "jira", "confluence", "notion",
    "rest api", "graphql", "microservices", "agile", "scrum",
    "swagger", "openapi", "postman", "unit testing", "pytest",
    "object-oriented programming", "oop", "data structures", "algorithms",
]


@dataclass
class MatchResult:
    score: int                          # 0–100
    found_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    all_job_keywords: list[str] = field(default_factory=list)
    cv_skill_pool: set[str] = field(default_factory=set)


def _extract_cv_skill_pool(cv: dict) -> set[str]:
    """
    CV'deki tüm metinlerden normalize edilmiş skill seti oluştur.
    Skills bölümü + experience bullets + project descriptions dahil.
    """
    texts: list[str] = []

    # Skills bölümü
    skills = cv.get("skills", {})
    for skill_list in skills.values():
        if isinstance(skill_list, list):
            texts.extend(str(s).lower() for s in skill_list)

    # Experience bullet points
    for exp in cv.get("experience", []):
        for bullet in exp.get("bullets", []):
            texts.append(bullet.lower())

    # Projects
    for proj in cv.get("projects", []):
        texts.append(proj.get("description", "").lower())
        for tech in proj.get("technologies", []):
            texts.append(tech.lower())
        for bullet in proj.get("bullets", []):
            texts.append(bullet.lower())

    # Summary
    texts.append(cv.get("summary", "").lower())

    combined = " ".join(texts)

    pool: set[str] = set()
    for skill in _ALL_SKILLS:
        pattern = rf"\b{re.escape(skill)}\b"
        if re.search(pattern, combined, re.IGNORECASE):
            pool.add(skill.lower())

    return pool


def _extract_job_keywords(description: str, title: str) -> list[str]:
    """İlan metninden geçen skill keyword'lerini çıkar."""
    text = f"{title} {description}".lower()
    found: list[str] = []
    for skill in _ALL_SKILLS:
        pattern = rf"\b{re.escape(skill)}\b"
        if re.search(pattern, text, re.IGNORECASE):
            found.append(skill.lower())
    return found


def analyze_match(
    job_title: str,
    job_description: str,
    cv: dict | None = None,
) -> MatchResult:
    """
    İlan ile CV'yi karşılaştırır.
    Returns MatchResult with score, found/missing skills.
    """
    if cv is None:
        with open(MASTER_CV_PATH, "r", encoding="utf-8") as f:
            cv = json.load(f)

    cv_pool = _extract_cv_skill_pool(cv)
    job_keywords = _extract_job_keywords(job_description, job_title)

    if not job_keywords:
        return MatchResult(score=0, all_job_keywords=[], cv_skill_pool=cv_pool)

    found    = [kw for kw in job_keywords if kw in cv_pool]
    missing  = [kw for kw in job_keywords if kw not in cv_pool]

    # Deduplicate preserving order
    found   = list(dict.fromkeys(found))
    missing = list(dict.fromkeys(missing))

    score = int(len(found) / len(job_keywords) * 100)

    return MatchResult(
        score=score,
        found_skills=found,
        missing_skills=missing,
        all_job_keywords=job_keywords,
        cv_skill_pool=cv_pool,
    )


def skill_frequency_from_db(descriptions: list[str], total_jobs: int) -> list[dict]:
    """
    Tüm ilan açıklamalarından skill frekansı hesapla.
    Returns: [{"skill": "Python", "count": 42, "pct": 85.0}, ...]
    """
    from collections import Counter
    counter: Counter = Counter()
    for desc in descriptions:
        text = desc.lower()
        for skill in _ALL_SKILLS:
            pattern = rf"\b{re.escape(skill)}\b"
            if re.search(pattern, text, re.IGNORECASE):
                counter[skill] += 1

    results = []
    for skill, count in counter.most_common(20):
        pct = round(count / total_jobs * 100, 1) if total_jobs > 0 else 0.0
        results.append({"skill": skill.title(), "count": count, "pct": pct})
    return results
