import pytest
from src.database import (
    init_db,
    ensure_default_profile,
    get_profiles,
    get_active_profile,
    set_active_profile,
    save_profile,
    delete_profile,
    delete_job,
    insert_job,
    get_job_by_db_id,
)
from src.models import Job
from datetime import datetime, timezone

def test_profile_lifecycle(tmp_path, monkeypatch):
    test_db = tmp_path / "test_jobs.db"
    monkeypatch.setattr("src.database.DB_PATH", test_db)
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


def test_delete_job(tmp_path, monkeypatch):
    test_db = tmp_path / "test_jobs.db"
    monkeypatch.setattr("src.database.DB_PATH", test_db)
    init_db()

    job = Job(
        job_id="test_del_123",
        source="test",
        title="Working Student Data",
        company="Acme Corp",
        location="Berlin, Germany",
        url="https://example.com/job/123",
        description="Great data role",
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    db_id = insert_job(job)
    assert db_id > 0
    assert get_job_by_db_id(db_id) is not None

    # Delete job
    deleted = delete_job(db_id)
    assert deleted is True
    assert get_job_by_db_id(db_id) is None

    # Deleting non-existent job returns False
    assert delete_job(999999) is False


def test_cross_platform_deduplication(tmp_path, monkeypatch):
    from src.database import (
        normalize_company,
        normalize_title,
        is_duplicate,
        deduplicate_database,
    )

    test_db = tmp_path / "test_dedup.db"
    monkeypatch.setattr("src.database.DB_PATH", test_db)
    init_db()

    # 1. Normalization tests
    assert normalize_company("1KOMMA5˚ GmbH & Co. KG") == "1komma5"
    assert normalize_company("acemate.ai") == "acemate"
    assert normalize_company("IMTF - Excellence in RegTech Solutions") == "imtf"
    assert normalize_company("SAP Careers") == "sap"

    assert normalize_title("Working Student (m/f/d) - Software Engineer - Berlin") == "working student software engineer"
    assert normalize_title("Software Engineering Intern - Fullstack (x/f/m)") == "software engineer intern fullstack"
    assert normalize_title("Working Student QA in Mobile App Development (m|w|d)") == "working student qa in mobile app development"
    assert normalize_title("Werkstudent (w/m/d) IT Support [gn]") == "working student it support"

    # 2. Insert initial job
    job1 = Job(
        job_id="job_linkedin_1",
        source="linkedin",
        title="Software Engineer Intern - Fullstack (x/f/m) - Berlin",
        company="Doctolib",
        location="Berlin, Germany",
        url="https://linkedin.com/jobs/view/1001",
        status="new",
    )
    insert_job(job1)

    # 3. Same job from another platform (different gender tag, no 'Berlin', different URL)
    assert is_duplicate(
        url="https://workingstudentjobs.de/jobs/doctolib-2002",
        title="Software Engineering Intern - Fullstack (m/w/d)",
        company="Doctolib GmbH",
    ) is True

    # 4. Distinct job at the same company must NOT be considered duplicate
    assert is_duplicate(
        url="https://workingstudentjobs.de/jobs/doctolib-3003",
        title="Working Student Data Engineering",
        company="Doctolib",
    ) is False

    # 5. Deduplication preserves applied jobs
    job2 = Job(
        job_id="job_join_2",
        source="join.com",
        title="Software Engineer Intern - Fullstack (w/m/d)",
        company="Doctolib",
        location="Berlin",
        url="https://join.com/jobs/doctolib-fullstack",
        status="applied",
    )
    insert_job(job2)

    removed = deduplicate_database()
    assert removed == 1

    remaining = get_job_by_db_id(2)
    assert remaining is not None
    assert remaining["status"] == "applied"


