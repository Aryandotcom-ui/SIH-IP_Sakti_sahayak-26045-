"""Direct retrieval diagnostic.

This must exercise the *exact same* retrieval configuration as
production. Production currently builds its index with the TF-IDF
embedder (see scripts/run.sh / render.yaml), so this script loads the
persisted TF-IDF artifact from the same Chroma directory rather than
loading a sentence-transformer model that was never used to build the
index. Querying with a different embedding backend than the one used
at ingest time lands in a different vector space and silently produces
meaningless results (or an outright dimension mismatch) — so this
script fails loudly instead of falling back to BGE.

Usage:
    python debug_retrieval.py                      # built-in positive + negative cases
    python debug_retrieval.py "your query here"     # diagnose one query

Runs the full decision layer (domain gate -> retrieval -> confidence/
evidence), not just raw similarity scores, so this can be used to
diagnose both directions:
    valid query    -> relevant evidence, evidence_strength, not abstained
    irrelevant query -> domain-gate abstention, or insufficient evidence
"""

import sys
from pathlib import Path

from ai.embedder import TfidfEmbedder
from ai.store import VectorStore
from ai.person_b_retrieval.confidence import compute_confidence, evidence_strength
from ai.person_b_retrieval.domain_gate import QueryDomain, classify_domain
from ai.person_b_retrieval.schema import MatchedChunk

CHROMA_DIR = Path("data/chroma")
ARTIFACT_PATH = CHROMA_DIR / TfidfEmbedder.ARTIFACT_NAME

DEFAULT_QUERIES = [
    ("positive", "What kinds of subject matter cannot be patented in India?"),
    ("negative", "how are you"),
]

if not ARTIFACT_PATH.exists():
    print(
        "\nERROR: TF-IDF artifact not found. Build the corpus before "
        "running retrieval diagnostics.\n"
        f"  expected: {ARTIFACT_PATH}\n"
        "  run:      python -m ai.cli data/pdfs --manifest ai/corpus.yaml "
        "--model tfidf\n",
        file=sys.stderr,
    )
    sys.exit(1)

embedder = TfidfEmbedder.load(CHROMA_DIR)
store = VectorStore(CHROMA_DIR)

queries = [("manual", sys.argv[1])] if len(sys.argv) > 1 else DEFAULT_QUERIES

any_unexpected = False

for label, query in queries:
    print("\n" + "=" * 80)
    print(f"DIRECT RETRIEVAL DEBUG [{label}]")
    print("=" * 80)
    print("QUERY:", query)
    print("EMBEDDER:", embedder.name)

    decision = classify_domain(query)
    print(f"DOMAIN: {decision.domain.value} ({decision.reason})")

    if decision.domain is QueryDomain.OUT_OF_DOMAIN:
        print("-> abstained before retrieval (domain gate). No embedder/store call made.")
        if label == "positive":
            print("WARNING: expected this query to reach retrieval.", file=sys.stderr)
            any_unexpected = True
        continue

    result = store.query(query=query, embedder=embedder, jurisdiction="india", top_k=20)
    matched = [
        MatchedChunk(
            chunk_id=m["chunk_id"], text=m["text"], act_name=m["act_name"],
            section=m["section"], jurisdiction=m["jurisdiction"],
            similarity_score=m["similarity_score"],
        )
        for m in result["matches"]
    ]

    for i, match in enumerate(result["matches"], 1):
        print(
            f"\n{i}. "
            f"{match['act_name']} | "
            f"{match['section']} | "
            f"score={match['similarity_score']:.6f}"
        )
        print("   chunk:", match["chunk_id"])
        text = match["text"].replace("\n", " ")
        print("   text:", text[:300])

    confidence, should_abstain = compute_confidence(query, matched, expected_jurisdiction="india")
    print(f"\nCONFIDENCE: {confidence:.4f}  EVIDENCE_STRENGTH: {evidence_strength(confidence)}"
          f"  SHOULD_ABSTAIN: {should_abstain}")

    if not result["matches"]:
        print("WARNING: zero matches returned.", file=sys.stderr)
        any_unexpected = True
    if label == "positive" and should_abstain:
        print("WARNING: expected this query to produce sufficient evidence.", file=sys.stderr)
        any_unexpected = True
    if label == "negative" and not should_abstain:
        print("WARNING: expected this query to abstain on insufficient evidence.", file=sys.stderr)
        any_unexpected = True

print("\n" + "=" * 80)
sys.exit(1 if any_unexpected else 0)
