"""Tests: Shared Celery DB engine is reused across calls."""
import pytest
from app.celery_db import _get_engine


def test_engine_is_singleton():
    """Same engine object returned on repeated calls."""
    engine1 = _get_engine()
    engine2 = _get_engine()
    assert engine1 is engine2


def test_engine_has_correct_pool_size():
    engine = _get_engine()
    assert engine.pool.size() <= 8  # pool_size=3 + max_overflow=5
