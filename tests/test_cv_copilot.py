import pytest
from src.ai_assistant import build_copilot_prompt, build_micro_action_prompt

def test_build_copilot_prompt():
    cv = {"personal": {"name": "Hazal"}, "summary": "Data student", "experience": []}
    prompt = build_copilot_prompt(
        current_cv=cv,
        user_prompt="Make it shorter",
        chat_history=[{"role": "user", "content": "hello"}],
        job_title="Data Analyst",
        company="Acme Corp",
        description="SQL required",
    )
    assert "Hazal" in prompt
    assert "Data Analyst" in prompt
    assert "Acme Corp" in prompt
    assert "Make it shorter" in prompt

def test_build_micro_action_prompt():
    prompt = build_micro_action_prompt(
        bullet="Built APIs with Python",
        action="technical",
        job_context="FastAPI developer",
    )
    assert "Built APIs with Python" in prompt
    assert "FastAPI developer" in prompt
    assert "technical" in prompt.lower()
