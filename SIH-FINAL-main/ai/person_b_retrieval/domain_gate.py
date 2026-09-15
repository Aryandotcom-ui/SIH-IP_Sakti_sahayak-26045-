"""
Domain/intent classification for incoming queries.

This runs *before* retrieval. The confidence/evidence layer in
confidence.py judges whether the chunks that came back actually support
an answer; this module judges something earlier and cheaper: whether the
query is the kind of thing IP-SAKTI Sahayak is for at all.

The two are complementary, not redundant:
- A query can be in-domain but still get "insufficient" evidence (a real
  IP question the corpus does not happen to cover).
- A query can be out-of-domain regardless of what the vector store would
  have returned ("how are you" will always have *some* nearest neighbour
  in the index; that neighbour being retrievable is not the same as it
  being relevant).

Keeping this as its own module means "how are you" never has to survive
long enough to call the embedder or the LLM at all — see
AIService.answer(), which checks this first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from ai.person_b_retrieval.confidence import _tokens as _confidence_tokens


class QueryDomain(str, Enum):
    IN_DOMAIN = "in_domain"
    AMBIGUOUS = "ambiguous"
    OUT_OF_DOMAIN = "out_of_domain"


# Vocabulary that plausibly relates to IP-SAKTI's supported domain: IP,
# AYUSH/Ayurveda, traditional knowledge, biodiversity/ABS, and the
# regulatory machinery around them. This is intentionally broad — it is a
# *gate*, not a classifier that has to guess the exact topic — and is
# matched against word stems/substrings so close morphological variants
# ("patentability", "patented", "patents") all match without listing every
# form individually.
DOMAIN_TERMS = {
    # Patents
    "patent", "patentab", "invent", "prior art", "claim", "section 3",
    "novelty", "inventive step", "specification", "pct", "wipo", "trips",
    "examiner", "examination", "grant", "opposition", "infring",
    # Other IP
    "trademark", "brand", "design", "copyright", "geographical indication",
    " gi ", "plant variet", "trade secret", "ip right", "intellectual propert",
    # Traditional knowledge / AYUSH
    "traditional knowledge", "tkdl", "ayush", "ayurved", "siddha", "unani",
    "homeopath", "formulation", "herbal", "medicine", "medicinal",
    "classical text", "folk remedy",
    # Biodiversity / ABS
    "biodiversity", "biological resource", "biological diversity",
    " abs ", "benefit shar", "nagoya", "bioprospect", "genetic resource",
    "access and benefit",
    # Regulatory / legal machinery
    "licens", "regist", "regulatory", "complian", "statute", "act,",
    "act ", "rule", "treaty", "jurisdiction", "ownership", "applicant",
    "protect", "law", "legal",
}

# Short, generic conversational openers/closers that carry no domain
# content but should not, by themselves, make an otherwise domain-rich
# message look thin. They are stripped before the emptiness check so
# "hi, can I patent this formulation" is not penalised for the "hi".
_GREETING_PREFIX = re.compile(
    r"^\s*(hi|hey|hello|thanks|thank you|please)[,!.\s]*", re.IGNORECASE
)

# Object-less "can I protect this" style phrasing: a real intent, but with
# nothing named yet for retrieval to search on.
_AMBIGUOUS_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bcan i protect (this|it|that)\b",
        r"\bis (this|it|that) patentable\b",
        r"\bhow do i (register|protect|patent) (this|it|that)\b",
        r"\bcan (this|it|that) be (patented|protected|registered)\b",
        r"^\s*(is|can) (this|it|that)\b.{0,25}$",
    ]
]

# Clearly off-topic small talk / general chit-chat, used only as a
# high-confidence shortcut to OUT_OF_DOMAIN; absence from this list never
# by itself makes something in-domain.
_OUT_OF_DOMAIN_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"^\s*(hi|hey|hello|how are you|what'?s up|good (morning|evening|night))\W*$",
        r"\bweather\b",
        r"\btell me a joke\b",
        r"\bwrite (me )?a poem\b",
        r"\bwho (won|is winning) (the )?(game|match|score)\b",
        r"\bwhat(?:'s| is) the score\b",
        r"\brecipe\b",
        r"\bhow'?s it going\b",
    ]
]


@dataclass
class DomainDecision:
    domain: QueryDomain
    reason: str
    # Populated only for AMBIGUOUS: short options a UI can render as
    # quick-reply buttons (see spec's clarification card).
    clarification_options: list[str] = field(default_factory=list)

    @property
    def is_out_of_domain(self) -> bool:
        return self.domain is QueryDomain.OUT_OF_DOMAIN

    @property
    def is_ambiguous(self) -> bool:
        return self.domain is QueryDomain.AMBIGUOUS


CLARIFICATION_OPTIONS = [
    "Invention", "Formulation", "Brand", "Design",
    "Creative work", "Traditional knowledge",
]


# The generic verbs/nouns that the _AMBIGUOUS_PATTERNS above are built
# out of. They are what makes a query *look* like an IP question; they
# are not what makes it answerable. "Can this be patented?" consists of
# nothing but these, which is exactly why it needs a clarifying question
# back. Subtracting them from the query's content tokens is how
# _is_object_less() below tells "nothing named yet" from "named, and
# phrased in the same shape".
_AMBIGUITY_GENERIC_TOKENS = {
    "patent", "patents", "patented", "patentable", "patentability",
    "protect", "protects", "protected", "protection",
    "register", "registers", "registered", "registration",
    "file", "filed", "filing", "apply", "applied",
    "get", "got", "make", "made", "want", "need", "know", "help",
    "anything", "something", "thing", "stuff", "idea", "one",
}


def _is_object_less(text: str) -> bool:
    """True when the query names nothing for retrieval to search on.

    The _AMBIGUOUS_PATTERNS match a *shape* — "can <pronoun> be
    patented" — and matching that shape is not the same as being
    under-specified. The patterns are unanchored, so before this check
    existed they also swallowed

        "Can this be patented if it is a classical Ayurvedic
         formulation described in the Charaka Samhita?"

    which names its subject three times over and had a clarification
    card thrown back at it anyway. Asking someone to specify what they
    mean when they have already said it is worse than the ambiguity the
    card exists to resolve: it reads as the system not having listened.

    So the shape only decides ambiguity when nothing substantive
    survives removing the generic vocabulary the shape is made of.
    """
    return not (_confidence_tokens(text) - _AMBIGUITY_GENERIC_TOKENS)


def _has_domain_terms(text: str) -> bool:
    lowered = f" {text.lower()} "
    return any(term in lowered for term in DOMAIN_TERMS)


def classify_domain(query: str) -> DomainDecision:
    """Classify a raw user query as IN_DOMAIN, AMBIGUOUS or OUT_OF_DOMAIN.

    This is deliberately conservative in both directions:
    - it never rejects a query purely for lacking recognised legal/IP
      vocabulary. An earlier version of this function did exactly that —
      rejecting anything without a DOMAIN_TERMS hit — and it broke on
      ordinary in-context follow-ups like "What is the deadline?", which
      has real content words but no legal jargon. That is precisely the
      simplistic-keyword-rejection failure mode the spec this module
      implements explicitly warns against. Only two things make a query
      OUT_OF_DOMAIN: matching a recognised chit-chat/greeting pattern, or
      having no meaningful content tokens at all after stopwords are
      removed (the same emptiness check confidence.py uses, reused here
      via `_confidence_tokens` so the two stay consistent). Anything else
      with real content is passed through to retrieval — the evidence
      layer (confidence.py) is what actually judges topical relevance,
      by seeing whether the corpus has anything that overlaps with it.
      DOMAIN_TERMS below is a fast-path IN_DOMAIN signal for logging
      clarity, never a rejection criterion.
    - it never lets a query through as in-domain just because it is long
      or grammatically well-formed. Domain vocabulary has to be present,
      or the query has to match a recognised ambiguous-intent pattern,
      for it to avoid OUT_OF_DOMAIN.
    """
    stripped = _GREETING_PREFIX.sub("", query or "").strip()

    if not stripped:
        return DomainDecision(QueryDomain.OUT_OF_DOMAIN, "empty_query")

    for pattern in _OUT_OF_DOMAIN_PATTERNS:
        if pattern.search(stripped):
            return DomainDecision(QueryDomain.OUT_OF_DOMAIN, "matched_chitchat_pattern")

    # Checked before the general domain-term scan: these patterns are
    # specifically the object-less "protect/register/patent *this*" shape,
    # which contains generic verbs ("protect", "register") that would
    # otherwise pass the domain-term check below without ever naming what
    # the user actually means. Ambiguity here is about a missing subject,
    # not missing vocabulary, so it has to be caught first.
    for pattern in _AMBIGUOUS_PATTERNS:
        if pattern.search(stripped) and _is_object_less(stripped):
            return DomainDecision(
                QueryDomain.AMBIGUOUS,
                "object_less_protect_intent",
                clarification_options=list(CLARIFICATION_OPTIONS),
            )

    if not _confidence_tokens(stripped):
        # Every remaining word was a stopword/filler ("just wondering",
        # "ok thanks") — nothing here for retrieval to search on, same
        # failure mode confidence.py's own empty-query-terms fix guards
        # against on the evidence side.
        return DomainDecision(QueryDomain.OUT_OF_DOMAIN, "no_meaningful_terms")

    if _has_domain_terms(stripped):
        return DomainDecision(QueryDomain.IN_DOMAIN, "domain_terms_present")

    # Real content words, just not ones on the recognised legal/IP list —
    # e.g. an in-context follow-up ("What is the deadline?") or a genuinely
    # unrelated but well-formed question ("What's the best pizza
    # topping?"). Neither should be pre-judged by a keyword list; let
    # retrieval run and let confidence.py's coverage check decide based on
    # whether the corpus actually has anything relevant. A real off-topic
    # question like the pizza example still costs one retrieval call, but
    # will correctly abstain with "insufficient_evidence" once it does —
    # trading a small amount of unnecessary retrieval for never wrongly
    # blocking a legitimate question, which is the more expensive mistake.
    return DomainDecision(QueryDomain.IN_DOMAIN, "no_domain_terms_but_has_content")
