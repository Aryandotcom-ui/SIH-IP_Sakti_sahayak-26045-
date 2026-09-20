"""Shared test defaults for the real (non-demo) production configuration.

The application deliberately defaults DEMO_MODE off. The test suite still
exercises the deterministic fallback in several integration-style tests, so
tests opt into that mode explicitly without changing the production default.
Individual generation-mode tests override this setting when they need to
exercise the unavailable path.
"""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings


@pytest.fixture(autouse=True)
def demo_mode_for_legacy_integration_tests(monkeypatch):
    """Keep legacy integration assertions deterministic without changing prod."""
    monkeypatch.setattr(settings, "demo_mode", True)
