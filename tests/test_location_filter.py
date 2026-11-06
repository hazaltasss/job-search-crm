"""
Unit tests for strict location and remote filtering rules.
"""
from src.models import Job
from src.filters import _check_location


def test_berlin_job_passes():
    job = Job(
        job_id="test_1",
        source="test",
        title="Working Student Data Analyst",
        company="Tech Co",
        location="Berlin, Germany",
        url="https://example.com/1",
        description="Join our team in Berlin. Hybrid working model.",
    )
    passes, is_berlin, is_remote = _check_location(job)
    assert passes is True
    assert is_berlin is True


def test_hamburg_job_with_home_office_perk_is_rejected():
    # This was the exact bug with RWE in Hamburg
    job = Job(
        job_id="test_2",
        source="linkedin",
        title="Working Student Asset Risk and Lifetime Optimization d/f/m",
        company="RWE",
        location="Hamburg, Hamburg, Germany",
        url="https://example.com/2",
        description="We offer flexible hours and home office possibilities at our Hamburg office.",
    )
    passes, is_berlin, is_remote = _check_location(job)
    assert passes is False
    assert is_berlin is False


def test_munich_hybrid_job_is_rejected():
    job = Job(
        job_id="test_3",
        source="personio",
        title="Working Student Machine Learning",
        company="AI Labs",
        location="München, Bayern",
        url="https://example.com/3",
        description="Hybrid role: 2-3 Tage pro Woche im Büro in München erforderlich.",
    )
    passes, is_berlin, is_remote = _check_location(job)
    assert passes is False


def test_genuine_full_remote_job_passes():
    job = Job(
        job_id="test_4",
        source="arbeitnow",
        title="Junior Python Developer (100% Remote)",
        company="Cloud Scale",
        location="Germany",
        url="https://example.com/4",
        description="This position is 100% remote across Germany. Work from anywhere.",
    )
    passes, is_berlin, is_remote = _check_location(job)
    assert passes is True
    assert is_remote is True
    assert is_berlin is False


def test_remote_location_field_passes():
    job = Job(
        job_id="test_5",
        source="hiringcafe",
        title="Data Engineering Intern",
        company="Data Corp",
        location="Remote, Germany",
        url="https://example.com/5",
        description="Autonomous distributed data team.",
    )
    passes, is_berlin, is_remote = _check_location(job)
    assert passes is True
    assert is_remote is True


def test_buxtehude_onsite_job_is_rejected():
    job = Job(
        job_id="test_6",
        source="workingstudentjobs",
        title="Working Student (d/f/m) as Software Development Assistant",
        company="Airbus Aircraft",
        location="Buxtehude, Germany",
        url="https://example.com/6",
        description="Join Airbus in Buxtehude. On-site role.",
    )
    passes, is_berlin, is_remote = _check_location(job)
    assert passes is False
    assert is_berlin is False


def test_job_tagged_berlin_but_standort_nurnberg_is_rejected():
    job = Job(
        job_id="test_7",
        source="linkedin",
        title="Working Student Data Analytics",
        company="Innomotics",
        location="Berlin",
        url="https://example.com/7",
        description="Standort Nürnberg, DE. Join our team in Nuremberg.",
    )
    passes, is_berlin, is_remote = _check_location(job)
    assert passes is False


def test_job_tagged_berlin_but_office_in_munich_is_rejected():
    job = Job(
        job_id="test_8",
        source="linkedin",
        title="Working Student Software Engineering",
        company="QPLIX",
        location="Berlin",
        url="https://example.com/8",
        description="You should be based in Munich or nearby and able to come to the office.",
    )
    passes, is_berlin, is_remote = _check_location(job)
    assert passes is False


def test_job_tagged_berlin_but_based_in_frankfurt_is_rejected():
    job = Job(
        job_id="test_9",
        source="linkedin",
        title="Working Student Software Engineer (Flutter)",
        company="Maple Tales",
        location="Berlin",
        url="https://example.com/9",
        description="Ideally, you are based in Frankfurt am Main or the surrounding area.",
    )
    passes, is_berlin, is_remote = _check_location(job)
def test_job_tagged_berlin_but_actually_in_stuttgart():
    job = Job(
        job_id="test_fraunhofer",
        source="workingstudentjobs",
        title="Student Assistant for HPC Systems Administration and Quantum Service Engineering (all genders)",
        company="Fraunhofer Karriere",
        location="Berlin",
        url="https://www.workingstudentjobs.de/jobs/fraunhofer-karriere-student-assistant-for-hpc-systems-and-1898ee35",
        description="The Quantum Machine Learning team at Fraunhofer Institute IAO in Stuttgart conducts research... Sports facilities at the University of Stuttgart.",
    )
    passes, is_berlin, is_remote = _check_location(job)
    assert passes is False
    assert is_berlin is False



