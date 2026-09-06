import io
import pytest
from docx import Document
from src.cv_parser import extract_text_from_upload, normalize_parsed_cv

def test_extract_text_docx():
    doc = Document()
    doc.add_paragraph("Hazal Taş\nSoftware Engineer")
    buf = io.BytesIO()
    doc.save(buf)
    text = extract_text_from_upload(buf.getvalue(), "sample.docx")
    assert "Hazal Taş" in text
    assert "Software Engineer" in text

def test_normalize_parsed_cv():
    raw_dict = {
        "personal": {"name": "Test User"},
        "summary": "Summary test",
        "education": [{"degree": "B.Sc."}],
    }
    normalized = normalize_parsed_cv(raw_dict)
    assert "personal" in normalized
    assert normalized["personal"]["name"] == "Test User"
    assert "experience" in normalized
    assert isinstance(normalized["experience"], list)
    assert "projects" in normalized
    assert isinstance(normalized["projects"], list)
    assert "skills" in normalized
    assert isinstance(normalized["skills"], dict)
