import pytest
from src.database import (
    init_db,
    ensure_default_profile,
    get_profiles,
    get_active_profile,
    set_active_profile,
    save_profile,
    delete_profile,
)

def test_profile_lifecycle():
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
