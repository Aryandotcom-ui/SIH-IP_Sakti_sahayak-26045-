"""
Regression tests for the relevance/abstention behaviour described in the
implementation prompt: irrelevant questions must not surface confident-
looking legal evidence, and the domain gate must catch them before
retrieval or generation ever run.

These tests check the *behavioural decision* (IN_DOMAIN / AMBIGUOUS /
OUT_OF_DOMAIN, should_abstain True/False), not one exact internal score,
so they stay valid if the underlying weighting in confidence.py is tuned
later.
"""

from dataclasses import dataclass

import pytest

from ai.person_b_retrieval.confidence import (
    compute_confidence,
    evidence_strength,
)
from ai.person_b_retrieval.domain_gate import QueryDomain, classify_domain


# ---------------------------------------------------------------------
# Domain gate
# ---------------------------------------------------------------------

SHOULD_ABSTAIN_QUERIES = [
    "how are you",
    "what is the weather today",
    "tell me a joke",
    "write me a poem",
    "what is the score today",
]

SHOULD_BE_IN_DOMAIN_QUERIES = [
    "What kinds of subject matter cannot be patented in India?",
    "Can a classical Ayurvedic formulation be patented in India?",
    "What is Section 3 of the Patents Act?",
    "How does TKDL affect patent examination?",
    "What is ABS compliance for biological resources?",
    "Can I register my brand as a trademark?",
]

SHOULD_BE_AMBIGUOUS_QUERIES = [
    "Can I protect this?",
    "Is this patentable?",
    "How do I register it?",
]


@pytest.mark.parametrize("query", SHOULD_ABSTAIN_QUERIES)
def test_out_of_domain_queries_are_rejected_before_retrieval(query):
    decision = classify_domain(query)
    assert decision.domain is QueryDomain.OUT_OF_DOMAIN
    assert decision.is_out_of_domain


@pytest.mark.parametrize("query", SHOULD_BE_IN_DOMAIN_QUERIES)
def test_in_domain_queries_are_recognised(query):
    decision = classify_domain(query)
    assert decision.domain is QueryDomain.IN_DOMAIN, (
        f"expected IN_DOMAIN for {query!r}, got {decision.domain} "
        f"({decision.reason})"
    )


@pytest.mark.parametrize("query", SHOULD_BE_AMBIGUOUS_QUERIES)
def test_ambiguous_queries_trigger_clarification(query):
    decision = classify_domain(query)
    assert decision.domain is QueryDomain.AMBIGUOUS
    assert decision.clarification_options, "ambiguous decision needs options to offer"


def test_domain_terms_are_not_a_single_keyword_check():
    """A question with no literal 'patent' substring but clear patent-law
    intent must not be rejected just because it lacks that one keyword."""
    decision = classify_domain(
        "What inventions cannot be protected in India?"
    )
    assert decision.domain is QueryDomain.IN_DOMAIN


def test_greeting_prefix_does_not_defeat_a_real_question():
    decision = classify_domain(
        "Hi, can a classical Ayurvedic preparation be protected?"
    )
    assert decision.domain is QueryDomain.IN_DOMAIN


# ---------------------------------------------------------------------
# Confidence / evidence layer
# ---------------------------------------------------------------------

@dataclass
class _FakeChunk:
    text: str
    similarity_score: float
    jurisdiction: str = "india"
    instrument_type: str | None = None


def test_empty_query_terms_never_produce_full_coverage_or_high_confidence():
    """The core bug this prompt exists to fix: previously, a query with no
    meaningful (non-stopword) terms set coverage=1.0, so an arbitrary
    retrieved document could still read as fully confident."""
    chunks = [
        _FakeChunk(text="Guidelines for examination of AYUSH related inventions.",
                   similarity_score=0.9),
        _FakeChunk(text="Patents Act, 1970 section 3.", similarity_score=0.85),
    ]
    confidence, should_abstain = compute_confidence("how are you", chunks)
    assert confidence < 0.20, f"expected near-zero confidence, got {confidence}"
    assert should_abstain is True
    assert evidence_strength(confidence) == "insufficient"


def test_weak_lexical_overlap_is_weak_or_insufficient():
    chunks = [
        _FakeChunk(text="This document discusses unrelated administrative rules.",
                   similarity_score=0.55),
    ]
    confidence, should_abstain = compute_confidence(
        "What is Section 3 of the Patents Act?", chunks
    )
    assert evidence_strength(confidence) in ("weak", "insufficient")


def test_strong_semantic_and_lexical_match_is_strong():
    text = (
        "Section 3 of the Patents Act 1970 lists what is not an invention "
        "and cannot be patented in India, including certain formulations."
    )
    chunks = [
        _FakeChunk(text=text, similarity_score=0.95),
        _FakeChunk(text=text, similarity_score=0.9),
        _FakeChunk(text=text, similarity_score=0.88),
    ]
    confidence, should_abstain = compute_confidence(
        "What kinds of subject matter cannot be patented in India under "
        "Section 3 of the Patents Act?",
        chunks,
    )
    assert should_abstain is False
    assert evidence_strength(confidence) in ("strong", "moderate")


def test_no_matched_chunks_always_abstains():
    confidence, should_abstain = compute_confidence("patent Section 3", [])
    assert confidence == 0.0
    assert should_abstain is True
    assert evidence_strength(confidence) == "insufficient"


def test_multiple_supporting_sources_increase_evidence_over_a_single_weak_one():
    text = "Traditional knowledge and TKDL affect patent examination in India."
    single = [_FakeChunk(text=text, similarity_score=0.7)]
    multiple = [
        _FakeChunk(text=text, similarity_score=0.72),
        _FakeChunk(text=text, similarity_score=0.7),
        _FakeChunk(text=text, similarity_score=0.68),
    ]
    query = "How does TKDL affect patent examination?"
    single_conf, _ = compute_confidence(query, single)
    multi_conf, _ = compute_confidence(query, multiple)
    assert multi_conf >= single_conf


def test_jurisdiction_mismatch_reduces_evidence():
    """Signal D: expected_jurisdiction is a defense-in-depth backstop —
    retrieval already hard-filters by jurisdiction at the store layer, so
    this should never fire in normal operation, but if a wrong-
    jurisdiction chunk ever reaches this function it must not be scored
    as if it were correct just because its similarity is high."""
    text = (
        "Section 3 of the Patents Act 1970 lists what is not an invention "
        "and cannot be patented in India, including certain formulations."
    )
    query = (
        "What kinds of subject matter cannot be patented in India under "
        "Section 3 of the Patents Act?"
    )
    matching = [
        _FakeChunk(text=text, similarity_score=0.95, jurisdiction="india"),
        _FakeChunk(text=text, similarity_score=0.9, jurisdiction="india"),
    ]
    mismatched = [
        _FakeChunk(text=text, similarity_score=0.95, jurisdiction="international"),
        _FakeChunk(text=text, similarity_score=0.9, jurisdiction="international"),
    ]
    matching_conf, _ = compute_confidence(query, matching, expected_jurisdiction="india")
    mismatched_conf, _ = compute_confidence(query, mismatched, expected_jurisdiction="india")
    assert mismatched_conf < matching_conf


def test_no_expected_jurisdiction_does_not_penalise():
    """Omitting expected_jurisdiction (the normal call shape, since the
    caller has already guaranteed it via the store filter) must not
    silently discount confidence."""
    text = "Section 3 of the Patents Act 1970 lists what is not an invention."
    chunks = [_FakeChunk(text=text, similarity_score=0.95, jurisdiction="international")]
    conf, _ = compute_confidence("What is Section 3 of the Patents Act?", chunks)
    conf_with_none, _ = compute_confidence(
        "What is Section 3 of the Patents Act?", chunks, expected_jurisdiction=None
    )
    assert conf == conf_with_none


def test_authority_weighting_prefers_statute_over_guideline_but_stays_capped():
    """Signal (spec section 33): a primary legal source scores slightly
    above secondary commentary at the same similarity — but the effect is
    small enough that it can never be mistaken for the dominant factor,
    since it multiplies a confidence already driven by relevance."""
    text = (
        "Section 3 of the Patents Act 1970 lists what is not an invention "
        "and cannot be patented in India, including certain formulations."
    )
    query = (
        "What kinds of subject matter cannot be patented in India under "
        "Section 3 of the Patents Act?"
    )
    statute = [_FakeChunk(text=text, similarity_score=0.9, instrument_type="statute")]
    guideline = [_FakeChunk(text=text, similarity_score=0.9, instrument_type="guideline")]
    unknown = [_FakeChunk(text=text, similarity_score=0.9, instrument_type=None)]

    c_statute, _ = compute_confidence(query, statute)
    c_guideline, _ = compute_confidence(query, guideline)
    c_unknown, _ = compute_confidence(query, unknown)

    assert c_statute > c_guideline
    assert c_unknown == c_statute, "unrecognised/missing instrument_type must not be penalised"
    # Capped: the gap between the best and worst authority weighting must
    # stay small relative to the confidence itself, so a merely official
    # document can never leapfrog a genuinely more relevant one.
    assert (c_statute - c_guideline) / c_statute < 0.1


# ---------------------------------------------------------------------
# Multilingual gating
#
# The gate is English: its vocabulary list, its chit-chat patterns and
# its emptiness check all are. It used to run on the RAW query, before
# translation, with an ASCII-only tokeniser underneath it — so every
# Devanagari, Kannada, Tamil, Telugu, Bengali, Gujarati, Odia, Gurmukhi,
# Malayalam and Urdu query tokenised to the empty set, hit
# "no_meaningful_terms", and came back as "Outside supported scope"
# before it ever reached Bhashini. Every language this product exists to
# serve except English, refused at the door.
#
# Two things fix that and both are tested here: the tokeniser now sees
# Indic script (including the combining marks that a naive \w+ shatters
# words on), and AIService.answer() translates before it classifies. The
# tests below pin the first; test_api.py pins the second.
# ---------------------------------------------------------------------

MULTILINGUAL_QUERIES = [
    ("hi", "क्या पारंपरिक आयुर्वेदिक फॉर्मूलेशन का पेटेंट कराया जा सकता है?"),
    ("kn", "ಪೇಟೆಂಟ್ ಎಂದರೇನು?"),
    ("ta", "இது தமிழ் மொழியில் ஒரு கேள்வி"),
    ("te", "ఇది తెలుగు భాషలో ఒక ప్రశ్న"),
    ("bn", "এটি বাংলা ভাষায় একটি প্রশ্ন"),
    ("ml", "ഇത് മലയാളത്തിൽ ഒരു ചോദ്യമാണ്"),
]


@pytest.mark.parametrize("lang,query", MULTILINGUAL_QUERIES)
def test_indic_script_queries_are_not_refused_as_out_of_domain(lang, query):
    """An untranslated Indic query must reach retrieval, not be refused.

    It may well abstain afterwards on insufficient evidence — the corpus
    is English and an untranslated query will not overlap it. That is the
    honest outcome. "Outside supported scope" is not: it tells the user
    their question was the wrong kind, when the truth is the system could
    not read it.
    """
    decision = classify_domain(query)
    assert decision.domain is not QueryDomain.OUT_OF_DOMAIN, (
        f"{lang}: {decision.reason}"
    )


@pytest.mark.parametrize("lang,query", MULTILINGUAL_QUERIES)
def test_indic_script_queries_produce_content_tokens(lang, query):
    """The regression underneath the one above: the tokeniser returning
    the empty set is what made the gate refuse these."""
    from ai.person_b_retrieval.confidence import _tokens

    assert _tokens(query), f"{lang}: tokenised to nothing"


def test_tokeniser_still_empties_on_genuinely_contentless_input():
    """The emptiness check is load-bearing — confidence.py's coverage fix
    depends on it — so widening the tokeniser must not blunt it."""
    from ai.person_b_retrieval.confidence import _tokens

    for text in ["", "   ", "!!! ???", "q", "a an the"]:
        assert _tokens(text) == set(), repr(text)


# ---------------------------------------------------------------------
# Ambiguity is about a missing subject, not a matching sentence shape
# ---------------------------------------------------------------------

def test_specified_query_in_ambiguous_shape_is_not_sent_to_clarification():
    """The _AMBIGUOUS_PATTERNS are unanchored, so they match "can this be
    patented" wherever it appears — including in a question that goes on
    to say exactly what "this" is. Throwing a clarification card at
    someone who already answered it reads as the system not listening."""
    decision = classify_domain(
        "Can this be patented if it is a classical Ayurvedic formulation "
        "described in the Charaka Samhita?"
    )
    assert decision.domain is QueryDomain.IN_DOMAIN, decision.reason


def test_specified_query_naming_a_section_is_not_ambiguous():
    decision = classify_domain(
        "Is this patentable under Section 3(p) of the Patents Act?"
    )
    assert decision.domain is QueryDomain.IN_DOMAIN, decision.reason


def test_bare_object_less_query_is_still_ambiguous():
    """The narrowing above must not disarm the check entirely."""
    decision = classify_domain("Can this be patented?")
    assert decision.domain is QueryDomain.AMBIGUOUS
    assert decision.clarification_options


def test_single_character_query_is_refused_before_retrieval():
    """Pinned because four scope tests in backend/tests/test_api.py used
    "q" as a placeholder query and were silently relying on it reaching
    retrieval. It does not, and should not."""
    decision = classify_domain("q")
    assert decision.domain is QueryDomain.OUT_OF_DOMAIN
    assert decision.reason == "no_meaningful_terms"
