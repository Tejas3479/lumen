"""
Lumen Input Sanitization
Strips all HTML from user-submitted text using bleach.
Civic platform text should be plain text only — no HTML allowed.
"""
import re
import bleach


# Allow NO HTML tags — strip everything
ALLOWED_TAGS: list = []
ALLOWED_ATTRIBUTES: dict = {}


def sanitize_text(text: str | None, max_length: int | None = None) -> str | None:
    """
    Strips all HTML tags from user-submitted text.
    Truncates to max_length if specified.
    Returns None if input is None.
    """
    if text is None:
        return None
    cleaned = bleach.clean(
        text,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        strip=True,
        strip_comments=True,
    )
    # Collapse excessive whitespace (3+ consecutive whitespace chars → double newline)
    cleaned = re.sub(r'\s{3,}', '\n\n', cleaned.strip())
    if max_length:
        cleaned = cleaned[:max_length]
    return cleaned


def sanitize_issue(title: str, description: str) -> tuple[str, str]:
    """Sanitizes issue title and description."""
    return (
        sanitize_text(title, max_length=256) or title,
        sanitize_text(description, max_length=5000) or description,
    )


def sanitize_comment(content: str) -> str:
    """Sanitizes comment content."""
    return sanitize_text(content, max_length=2000) or content
