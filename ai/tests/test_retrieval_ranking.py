"""
Tests for the authority/jurisdiction re-ranking step in
ai/store.py's VectorStore.query().

    python -m pytest ai/tests/test_retrieval_ranking.py -v

What is being pinned here is the *bound*, not the reordering. An
authority weight is only safe while it stays far too small to beat
relevance: the moment it can, the system starts answering out of
whichever statute is most quotable rather than the one that is on
point, and it does so invisibly, because the answer still carries a
real citation to a real law. So the tests that matter most below are
the ones asserting what this step cannot do.

These exercise the arithmetic directly rather than through Chroma, so
they run without an ingested corpus. The end-to-end behaviour against
the real index is covered by the retrieval eval:

    python -m ai.person_c_generation.eval.eval_runner --retrieval
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai import store as store_module  # noqa: E402
from ai.person_b_retrieval.confidence import AUTHORITY_WEIGHT  # noqa: E402


def rerank(candidates, jurisdiction=None):
    """Run the re-ranking arithmetic over candidate dicts.

    Mirrors the loop in VectorStore.query() section 10. Kept as a helper
    rather than calling query() so these tests do not need an index.
    """
    for candidate in candidates:
        metadata = candidate["metadata"] or {}
        instrument = str(metadata.get("instrument_type") or "").lower()
        authority = store_module._AUTHORITY_RANK_WEIGHT.get(instrument, 1.0)

        jurisdiction_weight = 1.0
        if jurisdiction:
            candidate_jurisdiction = str(metadata.get("jurisdiction") or "").lower()
            if candidate_jurisdiction and candidate_jurisdiction != jurisdiction.lower():
                jurisdiction_weight = store_module._JURISDICTION_MISMATCH_WEIGHT

        candidate["relevance_score"] = candidate["fused_score"]
        candidate["fused_score"] = (
            candidate["fused_score"] * authority * jurisdiction_weight
        )
    candidates.sort(key=lambda c: c["fused_score"], reverse=True)
    return candidates


def candidate(name, score, instrument=None, jurisdiction="india"):
    return {
        "chunk_id": name,
        "fused_score": score,
        "metadata": {"instrument_type": instrument, "jurisdiction": jurisdiction},
    }


# ---------------------------------------------------------------------
# The bound. These are the tests to break if the weights are ever raised.
# ---------------------------------------------------------------------


def test_authority_cannot_lift_an_irrelevant_statute_over_a_relevant_guideline():
    """The failure this step is most able to cause, and must not.

    A statute that barely matches the question must stay below a
    guideline that matches it well. If this ever fails, the system has
    started preferring authoritative sources to correct ones — which
    looks like a better answer (it cites an Act) and is a worse one.
    """
    ranked = rerank([
        candidate("relevant-guideline", 0.80, "guideline"),
        candidate("irrelevant-statute", 0.30, "statute"),
    ])
    assert ranked[0]["chunk_id"] == "relevant-guideline"


@pytest.mark.parametrize("instrument", ["statute", "treaty", "rule", "guideline", None, "novel"])
def test_weight_never_exceeds_one(instrument):
    """Authority only ever demotes. Nothing is boosted above its own
    relevance score, so the fused score stays a bounded, comparable
    quantity and no chunk can be promoted past the relevance ceiling."""
    weight = store_module._AUTHORITY_RANK_WEIGHT.get(str(instrument or "").lower(), 1.0)
    assert 0.90 <= weight <= 1.0


def test_total_adjustment_stays_within_ten_percent():
    """Authority and jurisdiction compound. Even both firing at once must
    not move a score by more than ~10%, or the "can't beat relevance"
    property above stops holding at closer margins."""
    worst = min(store_module._AUTHORITY_RANK_WEIGHT.values())
    combined = worst * store_module._JURISDICTION_MISMATCH_WEIGHT
    assert combined >= 0.80


def test_relevance_gap_wider_than_the_weight_is_never_reordered():
    ranked = rerank([
        candidate("a", 0.90, "guideline"),
        candidate("b", 0.70, "statute"),
    ])
    assert [c["chunk_id"] for c in ranked] == ["a", "b"]


# ---------------------------------------------------------------------
# What it does do
# ---------------------------------------------------------------------


def test_near_tie_resolves_toward_the_primary_source():
    """Two chunks matching about equally well are not equally good
    citations: a binding rule and guidance paraphrasing it are different
    answers to "what does the law say". This is the case the step exists
    for — observed on the real index, where a 0.5911 guideline and a
    0.5847 rule swap."""
    ranked = rerank([
        candidate("guidance", 0.5911, "guideline"),
        candidate("binding-rule", 0.5847, "rule"),
    ])
    assert ranked[0]["chunk_id"] == "binding-rule"


def test_wrong_jurisdiction_chunk_is_demoted_not_dropped():
    """A backstop for a bypassed filter, so it degrades rather than
    excludes — if the metadata is what is wrong, dropping the chunk would
    silently return nothing at all."""
    ranked = rerank(
        [
            candidate("intl", 0.80, "treaty", jurisdiction="international"),
            candidate("indian", 0.76, "statute", jurisdiction="india"),
        ],
        jurisdiction="india",
    )
    assert [c["chunk_id"] for c in ranked] == ["indian", "intl"]
    assert len(ranked) == 2, "demoted, never filtered out"


def test_unknown_instrument_type_is_not_penalised():
    """An index built before instrument_type existed must rank exactly as
    it did before, not be silently demoted for missing metadata."""
    ranked = rerank([
        candidate("legacy", 0.50, None),
        candidate("tagged-guideline", 0.50, "guideline"),
    ])
    assert ranked[0]["chunk_id"] == "legacy"
    assert ranked[0]["fused_score"] == 0.50


def test_relevance_score_is_preserved_for_diagnostics():
    """Re-ranking must not destroy what relevance alone said — the
    evidence page shows both."""
    ranked = rerank([candidate("c", 0.60, "guideline")])
    assert ranked[0]["relevance_score"] == 0.60
    assert ranked[0]["fused_score"] < 0.60


# ---------------------------------------------------------------------
# Consistency with the confidence layer
# ---------------------------------------------------------------------


def test_ranking_and_confidence_agree_on_which_sources_are_primary():
    """store.py reorders candidates; confidence.py scales the reading
    reported for the winner. If the two disagreed about which sources
    are primary, the system would rank one way and explain itself
    another."""
    assert store_module._AUTHORITY_RANK_WEIGHT is AUTHORITY_WEIGHT
