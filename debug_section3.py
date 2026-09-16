import sys

import numpy as np
from pathlib import Path

from ai.embedder import TfidfEmbedder
from ai.store import VectorStore


QUERY = "What kinds of subject matter cannot be patented in India?"

SECTION_ID = "the-patents-act-1970--s3"

CHROMA_DIR = Path("data/chroma")


print("=" * 80)
print("SECTION 3 DIRECT EMBEDDING TEST")
print("=" * 80)

# This must use the same embedding backend the index was actually built
# with. Production currently builds with TF-IDF (see scripts/run.sh /
# render.yaml), so embedding the query with BGE here would compare it
# against Section 3's TF-IDF vector in a completely different vector
# space -- a meaningless number at best, a dimension mismatch at worst.
artifact = CHROMA_DIR / TfidfEmbedder.ARTIFACT_NAME
if not artifact.exists():
    print(
        f"\nERROR: TF-IDF artifact not found at {artifact}. "
        "Build the corpus before running retrieval diagnostics.",
        file=sys.stderr,
    )
    raise SystemExit(1)

embedder = TfidfEmbedder.load(CHROMA_DIR)

store = VectorStore(CHROMA_DIR)

# ------------------------------------------------------------
# Get Section 3 directly from Chroma
# ------------------------------------------------------------

result = store.collection.get(
    ids=[SECTION_ID],
    include=[
        "documents",
        "metadatas",
        "embeddings",
    ],
)

if not result.get("ids"):
    # Long sections get split into multiple chunks (--p1, --p2, ...) by
    # chunk_sections() in ai/sectioner.py, so the bare section id is not
    # always a literal chunk id. Fall back to the first part.
    all_ids = store.collection.get(include=[])["ids"]
    part_ids = sorted(i for i in all_ids if i == SECTION_ID or i.startswith(f"{SECTION_ID}--p"))
    if part_ids:
        result = store.collection.get(
            ids=[part_ids[0]],
            include=["documents", "metadatas", "embeddings"],
        )

if not result.get("ids"):
    print("ERROR: Section 3 was not found in Chroma.")
    raise SystemExit(1)

section_text = result["documents"][0]
section_metadata = result["metadatas"][0]
section_embedding = np.array(
    result["embeddings"][0],
    dtype=float,
)

# ------------------------------------------------------------
# Embed the natural-language query
# ------------------------------------------------------------

query_embedding = np.array(
    embedder.encode_query([QUERY])[0],
    dtype=float,
)

# ------------------------------------------------------------
# Calculate cosine similarity directly
# ------------------------------------------------------------

query_norm = np.linalg.norm(query_embedding)
section_norm = np.linalg.norm(section_embedding)

similarity = float(
    np.dot(query_embedding, section_embedding)
    / (query_norm * section_norm)
)

print("\nQUERY:")
print(QUERY)

print("\nSECTION:")
print(section_metadata.get("section"))

print("ACT:")
print(section_metadata.get("act_name"))

print("\nEMBEDDER:")
print(embedder.name)

print("\nCOSINE SIMILARITY:")
print(f"{similarity:.6f}")

print("\nSECTION TEXT:")
print(section_text[:2000])

print("\n" + "=" * 80)
