import re
from typing import Sequence


# Words that do not carry much evidence about the subject of a legal question.
STOPWORDS = {
    "a", "an", "the", "i", "me", "my", "we", "our", "you", "your",
    "can", "could", "would", "should", "may", "might",
    "is", "are", "am", "be", "been", "being",
    "do", "does", "did",
    "what", "which", "who", "when", "where", "how", "why",
    "to", "of", "for", "in", "on", "at", "by", "with", "from",
    "and", "or", "but", "if", "then",
    "it", "this", "that", "these", "those",
    "tell", "please", "kind", "kinds",
}


# Word characters in ANY script, not just ASCII. The earlier
# `[a-zA-Z0-9]+` pattern returned the empty set for every Devanagari,
# Kannada, Tamil, Telugu, Bengali, Gujarati, Odia, Gurmukhi, Malayalam
# and Urdu query — i.e. for every language this product exists to serve
# except English. Two things consumed that empty set and drew the wrong
# conclusion from it:
#
#   * compute_confidence()'s coverage check, whose empty-terms guard
#     treats "no query terms" as "no coverage" (correct in itself, but it
#     was firing on perfectly good Hindi);
#   * domain_gate.classify_domain()'s emptiness check, which reads "no
#     meaningful terms" as OUT_OF_DOMAIN and refused the query outright.
#
# `[^\W_]` under Python's default Unicode semantics covers the letters
# of all of those scripts (`_` is excluded explicitly so snake_case
# identifiers in a pasted code fragment do not read as one long content
# word). That alone is still not enough for Indic text: vowel signs,
# anusvara and virama are Unicode *combining marks* (categories Mn/Mc),
# not alphanumerics, so `[^\W_]+` alone shatters ಪೇಟೆಂಟ್ into five
# one-character fragments that the length floor below then discards —
# an empty token set again, by a subtler route. The explicit ranges add
# the Indic (U+0900–U+0DFF) and Arabic (U+0600–U+06FF) blocks back as
# word characters, minus danda U+0964 and double danda U+0965, which are
# sentence punctuation and should still split.
#
# The stopword list and the length floor are unchanged, and every ASCII
# character classifies exactly as it did before, so English behaviour is
# byte-for-byte identical to the previous implementation.
_WORD = re.compile(
    r"(?:[^\W_]|[\u0600-\u06FF\u0900-\u0963\u0966-\u0DFF])+",
    re.UNICODE,
)


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in _WORD.findall(text or "")
        if token.lower() not in STOPWORDS
        and len(token) > 2
    }


# How much weight each kind of legal instrument carries, keyed by the
# `instrument_type` metadata ai/corpus.yaml assigns. Primary sources (a
# statute or treaty text) sit slightly above secondary commentary
# (rules, guidance). An instrument type not listed here — including None,
# which is what an index built before this metadata existed returns —
# gets 1.0, i.e. no adjustment rather than a guessed one.
#
# Module-level, and imported by ai/store.py rather than duplicated
# there, because the two consume it for different purposes: store.py
# reorders retrieval candidates with it, this module scales the
# confidence reported for whichever candidate won. Two copies that
# drifted apart would have the system ranking by one notion of
# authority and explaining itself by another.
AUTHORITY_WEIGHT = {
    "statute": 1.0,
    "treaty": 1.0,
    "rule": 0.97,
    "guideline": 0.93,
}


# The default abstention threshold for this module. The application passes
# its own configured value (settings.abstain_threshold) rather than relying
# on this, so the two can legitimately differ — but a caller that does not
# pass one should get a single named default, not two literals that can
# drift apart.
ABSTAIN_THRESHOLD = 0.50


def compute_confidence(
    query: str,
    matched_chunks,
    threshold: float = ABSTAIN_THRESHOLD,
    expected_jurisdiction: str | None = None,
) -> tuple[float, bool]:
    """
    Confidence measures whether the retrieved evidence actually covers
    the subject of the question, not merely whether the embeddings
    are semantically similar.

    `expected_jurisdiction` is defense-in-depth, not the primary
    jurisdiction control: retrieval already hard-filters chunks by
    jurisdiction at the Chroma metadata level (see
    AIService._answer_for_scope, which passes `jurisdiction=...` into
    `store.query()`), so a mismatched chunk should never actually reach
    this function in normal operation. This parameter exists so that if
    it ever does — a caller bypassing the filter, a metadata error, a
    future code path that merges scopes before scoring — an authoritative
    but wrong-jurisdiction document cannot still read as strong evidence
    just because its similarity score is high. When omitted (the default)
    jurisdiction is not scored at all, since the caller has usually
    already guaranteed it structurally.

    Returns:
        (confidence, should_abstain)
    """

    if not matched_chunks:
        return 0.0, True

    # ---------------------------------------------------------
    # 1. Base retrieval confidence
    # ---------------------------------------------------------
    similarities = [
        max(0.0, min(1.0, float(chunk.similarity_score)))
        for chunk in matched_chunks
    ]

    top_score = similarities[0]

    # Agreement between the best few sources.
    if len(similarities) >= 2:
        agreement = sum(similarities[:3]) / min(3, len(similarities))
    else:
        agreement = top_score

    base_confidence = (
        0.70 * top_score +
        0.30 * agreement
    )

    # ---------------------------------------------------------
    # 1b. Jurisdiction compatibility (Signal D)
    # ---------------------------------------------------------
    # See the docstring above: this is a backstop, not the primary
    # control. jurisdiction_factor is 1.0 (no effect) whenever the caller
    # does not specify what jurisdiction was expected, or every chunk
    # already matches it — which is the normal case, since retrieval
    # itself is jurisdiction-filtered.
    jurisdiction_factor = 1.0
    if expected_jurisdiction:
        top_considered = matched_chunks[:5]
        matching = sum(
            1 for c in top_considered
            if str(getattr(c, "jurisdiction", "") or "").lower()
            == expected_jurisdiction.lower()
        )
        match_ratio = matching / len(top_considered)
        # A single mismatched chunk among several correct ones barely
        # moves this; a top result that is entirely wrong-jurisdiction
        # should meaningfully reduce confidence rather than being
        # ignored, so the floor sits at 0.5 rather than 0.0 — enough to
        # push a borderline answer toward abstention without also
        # zeroing out a mostly-correct BOTH-scope result over one
        # stray chunk.
        jurisdiction_factor = 0.5 + 0.5 * match_ratio
    base_confidence *= jurisdiction_factor

    # ---------------------------------------------------------
    # 1c. Top-result quality (Signal E)
    # ---------------------------------------------------------
    # A single weak, unconfirmed document should not carry an answer by
    # itself. score_margin rewards a top result that is clearly ahead of
    # the pack (a decisive match, not a coin-flip among similar chunks);
    # support_count rewards having more than one chunk clear a modest
    # relevance floor, since one thin match is weaker evidence than
    # several independent ones even at the same top score.
    second_score = similarities[1] if len(similarities) >= 2 else 0.0
    score_margin = max(0.0, top_score - second_score)
    support_count = sum(1 for s in similarities[:5] if s >= 0.4)
    support_factor = min(1.0, 0.6 + 0.1 * support_count)  # 1 source -> 0.7, 4+ -> 1.0
    base_confidence = base_confidence * (0.9 + 0.1 * min(score_margin * 2, 1.0)) * support_factor

    # ---------------------------------------------------------
    # 1d. Source authority (Signal, spec section 33)
    # ---------------------------------------------------------
    # A small, capped nudge only — never enough to let an authoritative
    # but unrelated document outrank a relevant one, since it multiplies
    # a base_confidence that has already been driven toward zero by weak
    # similarity/coverage/margin above. Primary legal sources (a statute
    # or treaty text) are weighted slightly above secondary commentary
    # (guidance/explanatory material) when the top result carries this
    # metadata; unknown instrument_type (None — e.g. an older persisted
    # index, or a source with no manifest entry) gets no adjustment rather
    # than a guessed one. This scales confidence in the top result's
    # evidence, not a re-ranking of candidates against each other — actual
    # retrieval ranking happens earlier, in store.py's fusion step, which
    # this pass did not touch (see README "Known limits").
    top_instrument = getattr(matched_chunks[0], "instrument_type", None)
    authority_factor = AUTHORITY_WEIGHT.get((top_instrument or "").lower(), 1.0)
    base_confidence *= authority_factor

    # ---------------------------------------------------------
    # 2. Evidence coverage
    # ---------------------------------------------------------
    query_terms = _tokens(query)

    if not query_terms:
        # A query with no meaningful (non-stopword) terms at all — "how are
        # you", "hi", "ok thanks" — has said nothing retrieval could have
        # covered. Treating that as full coverage was the root cause of
        # irrelevant chatter surfacing confident-looking legal evidence:
        # whatever the vector store happened to return got scored as if it
        # fully answered a question that was never actually asked. An empty
        # term set must read as *zero* evidence, not perfect evidence, so
        # this always drives should_abstain regardless of similarity.
        coverage = 0.0
    else:
        retrieved_text = " ".join(
            str(chunk.text)
            for chunk in matched_chunks[:5]
        ).lower()

        covered_terms = sum(
            1 for term in query_terms
            if term in retrieved_text
        )

        coverage = covered_terms / len(query_terms)

    # ---------------------------------------------------------
    # 3. Combine similarity + evidence coverage
    # ---------------------------------------------------------
    confidence = (
        0.55 * base_confidence +
        0.45 * coverage
    )

    # ---------------------------------------------------------
    # 4. Critical safety rule:
    # If the query contains important subject terms that the
    # retrieved evidence does not mention, do NOT allow a
    # high similarity score to produce high confidence.
    # ---------------------------------------------------------
    if query_terms and coverage < 0.50:
        confidence = min(confidence, 0.35)

    if query_terms and coverage < 0.34:
        confidence = min(confidence, 0.20)

    if not query_terms:
        # No content/domain words to check coverage against at all (see
        # above): never let base similarity alone carry this past the
        # abstain threshold. This is deliberately a hard ceiling, not just
        # a penalty folded into the weighted sum, because a sufficiently
        # high top_score could otherwise still clear a low threshold.
        confidence = min(confidence, 0.05)

    confidence = max(0.0, min(1.0, confidence))

    should_abstain = confidence < threshold

    return round(confidence, 4), should_abstain
def decide_abstain(confidence: float, threshold: float = ABSTAIN_THRESHOLD) -> bool:
    """Return True when confidence is too low to answer reliably."""
    return confidence < threshold


# Evidence-strength bands shown to users in place of a raw score. The
# thresholds are placed relative to ABSTAIN_THRESHOLD/the configured
# abstain_threshold so "insufficient" always lines up with should_abstain
# rather than drifting into its own separate cutoff.
EVIDENCE_STRONG = 0.75
EVIDENCE_MODERATE = 0.50


def evidence_strength(
    confidence: float, threshold: float = ABSTAIN_THRESHOLD
) -> str:
    """Map a raw (uncalibrated) similarity-derived score onto a semantic
    label: "strong" / "moderate" / "weak" / "insufficient".

    This exists because the underlying score — whether from the TF-IDF
    fallback or an embedding model's cosine similarity — is not a
    calibrated probability of legal correctness. A value of 0.66 does not
    mean "66% likely correct"; it is only useful for ranking and for
    deciding whether to answer at all. Surfacing the label instead of the
    number stops that number from being read as more than it is. See
    AIService.confidence_calibrated for the flag callers can use to decide
    whether the raw number is worth showing at all as a diagnostic.
    """
    if confidence < threshold:
        return "insufficient"
    if confidence >= EVIDENCE_STRONG:
        return "strong"
    if confidence >= EVIDENCE_MODERATE:
        return "moderate"
    return "weak"