"""
seed_demo_data.py — Dashboard'u test etmek için sahte ilanlar yükler.
Gerçek scraping başlamadan önce UI'yi görmek için kullanılır.

Usage:
    python scripts/seed_demo_data.py
"""
import sys
import os
from pathlib import Path
from datetime import datetime, timezone

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Env placeholder so config.py doesn't crash
for _v in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GOOGLE_SHEET_ID", "GEMINI_API_KEY"]:
    if not os.getenv(_v):
        os.environ[_v] = "__demo__"

from src.database import init_db, insert_job, is_duplicate
from src.models import Job

now = datetime.now(timezone.utc).isoformat()

DEMO_JOBS = [
    Job(
        job_id="demo_001", source="hiringcafe",
        title="Working Student – Data Science & ML",
        company="Zalando SE",
        location="Berlin, Germany",
        url="https://jobs.zalando.com/demo/001",
        description="""We are looking for a Working Student to join our Data Science team.
        You will work with Python, Pandas, Scikit-learn, and SQL to build machine learning
        models and data pipelines. Experience with Docker and GitHub Actions is a plus.
        Our working language is English. You will collaborate with international teams
        on recommendation systems using PyTorch and TensorFlow.
        Requirements: Python, SQL, machine learning, data analysis, Jupyter notebooks.
        Nice to have: Spark, Airflow, MLops, Databricks.""",
        language="en", is_remote=False, is_berlin=True,
        category="Data & AI", match_score=85,
        posted_at="2026-09-01", fetched_at=now, status="new",
    ),
    Job(
        job_id="demo_002", source="workingstudentjobs",
        title="Werkstudent Backend Engineering (Python)",
        company="N26 GmbH",
        location="Berlin, Germany",
        url="https://n26.com/careers/demo/002",
        description="""Join N26's backend engineering team as a Working Student.
        You'll build and maintain REST APIs using Python (FastAPI, Flask) and PostgreSQL.
        We use Docker, Kubernetes, and GitHub Actions for CI/CD.
        Our team language is English — international environment with 40+ nationalities.
        Requirements: Python, REST API, Git, SQL, Docker basics.
        Nice to have: Kafka, microservices architecture, AWS or GCP.""",
        language="en", is_remote=False, is_berlin=True,
        category="Software & IT", match_score=78,
        posted_at="2026-09-02", fetched_at=now, status="applied",
    ),
    Job(
        job_id="demo_003", source="hiringcafe",
        title="Internship – AI & Generative AI Engineering",
        company="Delivery Hero",
        location="Berlin, Germany",
        url="https://deliveryhero.com/careers/demo/003",
        description="""We're hiring an intern to work on our AI platform team.
        You'll build RAG pipelines, experiment with LangChain and LLMs (GPT, Gemini),
        and work on vector databases (Pinecone, ChromaDB).
        All communication in English. Python required. FastAPI experience a plus.
        You will implement prompt engineering strategies and support MLOps workflows.
        Requirements: Python, LLM APIs, Prompt Engineering, REST API.""",
        language="en", is_remote=False, is_berlin=True,
        category="Data & AI", match_score=92,
        posted_at="2026-09-02", fetched_at=now, status="saved",
    ),
    Job(
        job_id="demo_004", source="workingstudentjobs",
        title="Working Student – Cloud & DevOps Engineering",
        company="Siemens Energy",
        location="Berlin, Germany (Hybrid)",
        url="https://siemens-energy.com/careers/demo/004",
        description="""Support our Cloud Engineering team in building and maintaining
        infrastructure on AWS and Azure. You will work with Docker, Kubernetes,
        Terraform, and implement CI/CD pipelines using GitHub Actions.
        English is our working language. Linux scripting required.
        Requirements: Docker, Kubernetes, AWS or Azure, CI/CD, Linux, Git, Bash.""",
        language="en", is_remote=False, is_berlin=True,
        category="Software & IT", match_score=65,
        posted_at="2026-09-01", fetched_at=now, status="new",
    ),
    Job(
        job_id="demo_005", source="hiringcafe",
        title="Working Student – Business Intelligence & Analytics",
        company="HelloFresh SE",
        location="Berlin, Germany",
        url="https://hellofresh.com/careers/demo/005",
        description="""Join our BI team and help build dashboards and reports in Tableau
        and Looker Studio. You will write complex SQL queries, work with BigQuery,
        and support data-driven decision making across the business.
        English-speaking environment. Python for data processing is a plus.
        Requirements: SQL, Tableau or Power BI, Google Sheets, data analysis, Excel.""",
        language="en", is_remote=False, is_berlin=True,
        category="Data & AI", match_score=70,
        posted_at="2026-08-31", fetched_at=now, status="new",
    ),
    Job(
        job_id="demo_006", source="workingstudentjobs",
        title="Intern – Full Stack Web Development",
        company="GetYourGuide",
        location="Berlin, Germany",
        url="https://getyourguide.com/careers/demo/006",
        description="""We are looking for a motivated intern to join our frontend team.
        You will work with React, TypeScript, and Node.js to build user-facing features.
        Our stack also includes PostgreSQL, Docker, and GitHub Actions.
        Working language: English. RESTful API design knowledge expected.
        Requirements: React, TypeScript, JavaScript, HTML, CSS, REST API, Git.""",
        language="en", is_remote=False, is_berlin=True,
        category="Software & IT", match_score=55,
        posted_at="2026-09-03", fetched_at=now, status="skipped",
    ),
    Job(
        job_id="demo_007", source="hiringcafe",
        title="Working Student – Data Engineering",
        company="AUTO1 Group",
        location="Remote, Germany",
        url="https://auto1.com/careers/demo/007",
        description="""Build and maintain data pipelines on our modern data stack.
        You will use Python, Apache Airflow, dbt, and Snowflake to process large datasets.
        Spark and BigQuery experience is a bonus. Fully remote — English working language.
        Requirements: Python, SQL, Airflow or dbt, data pipeline, ETL, Snowflake.""",
        language="en", is_remote=True, is_berlin=False,
        category="Data & AI", match_score=80,
        posted_at="2026-09-03", fetched_at=now, status="new",
    ),
    Job(
        job_id="demo_008", source="workingstudentjobs",
        title="Werkstudent – Product Management (Tech)",
        company="Wolt",
        location="Berlin, Germany",
        url="https://wolt.com/careers/demo/008",
        description="""Support our product team with data-driven analysis and roadmap planning.
        Work closely with engineering, design, and business stakeholders using Agile/Scrum.
        You will use SQL for product analytics and Jira for project tracking.
        Business language: English. Experience with product analytics tools preferred.
        Requirements: SQL, Jira, Scrum, stakeholder management, product management.""",
        language="en", is_remote=False, is_berlin=True,
        category="Business Tech", match_score=50,
        posted_at="2026-09-02", fetched_at=now, status="new",
    ),
]

def main():
    print("🌱 Seeding demo data into jobs.db...")
    init_db()
    added = 0
    for job in DEMO_JOBS:
        if not is_duplicate(job.url):
            insert_job(job)
            added += 1
            print(f"  ✅ Added: {job.title} @ {job.company}")
        else:
            print(f"  ⏭️  Skip (duplicate): {job.title}")
    print(f"\n✨ Done! {added} demo jobs added.")
    print("Now run:  streamlit run dashboard.py")

if __name__ == "__main__":
    main()
