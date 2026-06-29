"""
Lumen Custom Exceptions
All domain exceptions with HTTP status codes and structured messages.
"""
from fastapi import HTTPException, status


class LumenException(HTTPException):
    """Base exception for all Lumen domain errors."""
    def __init__(self, status_code: int, detail: str, error_code: str = "LUMEN_ERROR"):
        super().__init__(status_code=status_code, detail={
            "error_code": error_code,
            "message": detail,
        })


class NotFoundError(LumenException):
    def __init__(self, resource: str, resource_id: str = ""):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} not found" + (f": {resource_id}" if resource_id else ""),
            error_code="NOT_FOUND",
        )


class UnauthorizedError(LumenException):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            error_code="UNAUTHORIZED",
        )


class ForbiddenError(LumenException):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message,
            error_code="FORBIDDEN",
        )


class ValidationError(LumenException):
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=message,
            error_code="VALIDATION_ERROR",
        )


class ConflictError(LumenException):
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=message,
            error_code="CONFLICT",
        )


class RateLimitError(LumenException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please slow down.",
            error_code="RATE_LIMIT_EXCEEDED",
        )


class SpamDetectedError(LumenException):
    def __init__(self, reason: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Report rejected: {reason}",
            error_code="SPAM_DETECTED",
        )


class AIUnavailableError(LumenException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service temporarily unavailable. Your report was saved.",
            error_code="AI_UNAVAILABLE",
        )
