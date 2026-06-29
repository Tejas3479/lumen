"""Tests: Input sanitization."""
import pytest
from app.utils.sanitize import sanitize_text, sanitize_issue, sanitize_comment


def test_strips_script_tags():
    result = sanitize_text("<script>alert('xss')</script>Pothole on road")
    assert "<script>" not in result
    assert "Pothole on road" in result


def test_strips_html_entities():
    result = sanitize_text("<b>Bold</b> pothole <i>here</i>")
    assert "<b>" not in result
    assert "Bold" in result
    assert "pothole" in result


def test_allows_plain_text():
    text = "Large pothole on MG Road near the signal. Cars swerving dangerously."
    result = sanitize_text(text)
    assert result == text


def test_truncates_to_max_length():
    long_text = "a" * 300
    result = sanitize_text(long_text, max_length=256)
    assert len(result) == 256


def test_handles_none():
    assert sanitize_text(None) is None


def test_sanitize_issue_returns_tuple():
    title, desc = sanitize_issue(
        "<h1>Pothole</h1>",
        "<p>Large pothole with <script>evil()</script> damage</p>"
    )
    assert "<h1>" not in title
    assert "<script>" not in desc
    assert "Large pothole with" in desc


def test_sanitize_comment():
    result = sanitize_comment("<img src=x onerror=alert(1)>I confirm this issue exists.")
    assert "<img" not in result
    assert "I confirm this issue exists." in result
