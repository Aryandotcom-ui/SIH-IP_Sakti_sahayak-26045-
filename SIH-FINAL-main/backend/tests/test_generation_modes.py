"""
Tests for the generation-mode matrix (master prompt section 16/39):

  CASE A: GROQ_API_KEY present               -> generation_mode = "live"
  CASE B: GROQ_API_KEY missing, DEMO_MODE=1  -> "mock", clearly labelled
  CASE C: GROQ_API_KEY missing, DEMO_MODE=0  -> "unavailable", no
          misleading "live AI" appearance

Groq itself is never called — CASE A mocks ai.person_c_generation.generate.
call_llm so this stays a fast, offline unit test rather than a live API
call, matching the master prompt's "mock external Groq calls in unit
tests" instruction.
"""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.services.ai_service import AIService  # noqa: E402
from app.config import settings  # noqa: E402
from ai.person_b_retrieval.schema import Classification  # noqa: E402


class FakeStore:
    """Minimal store returning one clearly relevant chunk, so retrieval
    and evidence evaluation pass and generation is actually reached —
    the point of these tests is what happens *after* that, not whether
    retrieval itself works (that is test_adversarial.py's job)."""

    def __init__(self):
        class Collection:
            name = "test"
        self.collection = Collection()

    def query(self, query, embedder, jurisdiction=None, formulation_type=None, top_k=5):
        text = (
            "Section 3 of the Patents Act 1970 lists what is not an "
            "invention and cannot be patented in India."
        )
        return {"matches": [{
            "chunk_id": "patents-act:section-3",
            "text": text,
            "act_name": "The Patents Act, 1970",
            "section": "Section 3",
            "jurisdiction": "india",
            "similarity_score": 0.92,
            "source_url": None,
            "instrument_type": "statute",
        }]}

    def count(self):
        return 1


@pytest.fixture
def service(tmp_path):
    from ai.audit import AuditLog
    from ai.translation import NullTranslator

    svc = AIService()
    svc._store = FakeStore()
    svc._embedder = object()  # never used: FakeStore ignores it
    svc._audit = AuditLog(tmp_path / "audit.sqlite3")
    svc._translator = NullTranslator()
    return svc


IN_DOMAIN_QUERY = "What kinds of subject matter cannot be patented in India?"


def test_case_a_live_generation_when_groq_key_is_configured(service, monkeypatch):
    """GROQ_API_KEY present -> generation_mode = "live", and the real LLM
    call path is exercised (mocked at the network boundary only)."""
    monkeypatch.setattr(settings, "groq_api_key", "fake-test-key")
    monkeypatch.setattr(settings, "demo_mode", True)  # irrelevant when a key exists

    def fake_call_llm(prompt, model, api_key=None):
        assert api_key == "fake-test-key"
        return (
            '{"answer_text": "Section 3 excludes certain subject matter.", '
            '"citations": [{"act_name": "The Patents Act, 1970", "section": "Section 3"}], '
            '"abstained": false}'
        )

    monkeypatch.setattr(
        "ai.person_c_generation.generate.call_llm", fake_call_llm
    )

    result = service.answer(IN_DOMAIN_QUERY, Classification(), top_k=5, scope="IN")

    assert result["generation"] == "live"
    assert result["generation_provider"] == "groq"
    assert not result["abstained"]


def test_case_b_demo_fallback_when_key_missing_and_demo_mode_on(service, monkeypatch):
    """No key, DEMO_MODE=true -> deterministic mock fallback, clearly
    labelled — never silently presented as a live answer."""
    monkeypatch.setattr(settings, "groq_api_key", None)
    monkeypatch.setattr(settings, "demo_mode", True)

    result = service.answer(IN_DOMAIN_QUERY, Classification(), top_k=5, scope="IN")

    assert result["generation"] == "mock"
    assert result["generation_provider"] == "demo"
    # The prose exists (retrieval + evidence still worked) but is
    # explicitly not attributed to a live model.
    assert result["answer_text"]


def test_case_c_generation_unavailable_when_key_missing_and_demo_mode_off(service, monkeypatch):
    """No key, DEMO_MODE=false -> explicit "unavailable", not demo prose
    dressed up as a real answer. This is the state a production
    deployment relying on live generation should see instead of silently
    getting canned text."""
    monkeypatch.setattr(settings, "groq_api_key", None)
    monkeypatch.setattr(settings, "demo_mode", False)

    result = service.answer(IN_DOMAIN_QUERY, Classification(), top_k=5, scope="IN")

    assert result["generation"] == "unavailable"
    assert result["generation_provider"] is None
    assert result["abstained"] is True
    # No misleading "live AI" appearance: the answer text says generation
    # is unavailable rather than presenting fabricated legal content.
    assert "not configured" in result["answer_text"].lower() or \
        "unavailable" in result["answer_text"].lower()


def test_never_reports_live_without_a_key(service, monkeypatch):
    """Defensive regression: generation_mode must never read "live" when
    there is no key to have used, regardless of DEMO_MODE."""
    for demo_mode in (True, False):
        monkeypatch.setattr(settings, "groq_api_key", None)
        monkeypatch.setattr(settings, "demo_mode", demo_mode)
        result = service.answer(IN_DOMAIN_QUERY, Classification(), top_k=5, scope="IN")
        assert result["generation"] != "live"
        assert result["generation_provider"] != "groq"
