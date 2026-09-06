import os
import json
from src import database as db
from src.ai_assistant import build_tailored_cv_data, generate_cv_pdf, generate_cv_docx

def test_e2e_profile_to_cv_generation(tmp_path, monkeypatch):
    test_db = tmp_path / "test_jobs.db"
    monkeypatch.setattr("src.database.DB_PATH", test_db)
    db.init_db()

    # Test database profile ensure & active fetch
    db.ensure_default_profile()
    active = db.get_active_profile()
    assert active is not None
    assert "data" in active
    cv = active["data"]
    assert "personal" in cv
    assert "skills" in cv

    exp_item = (cv.get("experience") or [{}])[0]
    proj_item = (cv.get("projects") or [{}])[0]

    # Mock optimization payload
    mock_opt = {
        "tailored_summary": "Data Analyst specializing in SQL and Python.",
        "estimated_new_score": 88,
        "optimization_notes": "Added SQL metrics and Docker exposure.",
        "optimized_experience": [
            {
                "role": exp_item.get("title") or exp_item.get("role", "Software Engineer"),
                "company": exp_item.get("company", "Tech Co"),
                "bullets": [
                    "Enhanced automated data pipelines achieving 99.8% SLA.",
                    "Implemented predictive analytics models in Python and SQL."
                ]
            }
        ],
        "optimized_projects": [
            {
                "name": proj_item.get("name", "Analytics Project"),
                "bullets": [
                    "Engineered cloud ETL pipeline processing 50k events daily."
                ]
            }
        ]
    }

    # Build tailored CV data
    tailored = build_tailored_cv_data(mock_opt, cv, company="TestGmbH")
    assert tailored["summary"] == "Data Analyst specializing in SQL and Python."
    assert len(tailored["experience"]) >= 1
    assert tailored["experience"][0]["bullets"][0] == "Enhanced automated data pipelines achieving 99.8% SLA."

    # Test PDF generation
    pdf_bytes = generate_cv_pdf(tailored)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")

    # Test DOCX generation
    docx_bytes = generate_cv_docx(tailored)
    assert len(docx_bytes) > 500
    assert docx_bytes.startswith(b"PK")  # ZIP header for docx
