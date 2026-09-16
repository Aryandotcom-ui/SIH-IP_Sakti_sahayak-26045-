# Implementation history

Accumulated notes from successive work sessions on IP-SAKTI Sahayak.
This is a changelog, not a description of the system — for what the
system currently does and does not do, see the "How it works" and
"Known limitations" sections of [README.md](README.md).

Entries are kept because the *reason* a behaviour exists is usually
harder to recover than the behaviour itself, and several of the
decisions below were made after a bug proved the obvious approach
wrong.

---

## Multilingual domain gate (current session)

**The domain gate refused every non-English query.** The gate ran on the
raw query text, before translation. Its vocabulary list, its chit-chat
patterns and its emptiness check are all English, and the tokeniser
underneath it used `[a-zA-Z0-9]+` — ASCII only. Every Devanagari,
Kannada, Tamil, Telugu, Bengali, Gujarati, Odia, Gurmukhi, Malayalam and
Urdu query therefore tokenised to the empty set, hit
`no_meaningful_terms`, and came back as "Outside supported scope" before
Bhashini was ever consulted. Every language this product exists to serve
except English, refused at the door. The gate's early return then
reported `translated: true` and `translation_status: "not_required"`,
telling a Hindi speaker that nothing needed translating while handing
them an English refusal.

Three fixes, all of which have regression tests:

- `_tokens()` in `confidence.py` is Unicode-aware, including Indic
  combining marks. A first attempt using a bare `[^\W_]+` was still
  wrong: vowel signs, anusvara and virama are Unicode combining marks
  (categories Mn/Mc), not alphanumerics, so that pattern shattered
  `ಪೇಟೆಂಟ್` into one-character fragments that the length floor then
  discarded — an empty token set again, by a subtler route.
- `AIService.answer()` translates *before* it classifies. Translation is
  not the expensive step the gate was placed early to avoid (that is
  embedding, retrieval and the LLM, all still downstream), and for an
  English query it is an identity no-op.
- Gate-readability is decided from the actual script of the text via
  `detect_language`, not from the caller's declared `language`, so
  mislabelled English still gets gated and a successfully translated
  query does too. A query that could *not* be translated passes through
  to retrieval and is left to the evidence layer, which abstains
  honestly on no coverage rather than claiming the question was
  off-topic.

**Ambiguity patterns over-triggered.** The object-less-intent patterns
are unanchored, so `can this be patented` matched anywhere in a string —
including in "Can this be patented if it is a classical Ayurvedic
formulation described in the Charaka Samhita?", which names its subject
three times and got a clarification card thrown back at it anyway.
Ambiguity now additionally requires the query to *be* object-less:
nothing substantive survives removing the generic vocabulary the
patterns are built from.

## Retrieval ranking

Authority and jurisdiction previously adjusted only the confidence
score, which tells a user how much to trust the top result but cannot
change which result is on top. They now re-rank candidates in
`store.py`, as a bounded multiplier — see README point 2 for why the
bound matters more than the reordering. `AUTHORITY_WEIGHT` lives in
`confidence.py` and is imported by `store.py` rather than duplicated:
the two consume it for different purposes, and two copies that drifted
apart would have the system ranking by one notion of authority and
explaining itself by another.

## API contract

`evidence_score` (the raw uncalibrated number, named so it does not read
as a probability) and a top-level `jurisdiction` field were added at
both the flat and per-scope levels. Both are defaulted, so response
dicts built to the older shape still validate.

## Performance

Audited empirically rather than by inspection. The embedder, vector
store and translator are all correctly cached on the module-level
`AIService` singleton — one construction across repeated requests — and
Bhashini pipeline resolution caches per-instance on that reused
translator. `corpus_jurisdictions()` does run per request, at ~10ms
against a 2,274-chunk index versus a ~2,200ms full request (0.5%). It
was deliberately left uncached: the saving is not measurable and a cache
would introduce a staleness bug, since a re-ingest changes those counts
while the process keeps running.

## Earlier sessions

- **13 of the 17 corpus documents have no `source_url`**, so their citations
  cannot link out to the official text. The UI marks these "no public link".
  They are fully ingested and quoted verbatim; there is just no verified URL
  on file. Filling these in needs a machine that can reach the official
  sites.
- **The offline embedder is lexical.** `--model tfidf` is character-ngram
  TF-IDF, so it matches wording rather than meaning: a question phrased far
  from the statute's language can retrieve the wrong Act. It exists so the
  system runs with no model download. For better retrieval, install
  `sentence-transformers`, uncomment it in `ai/requirements.txt`, and rebuild
  with `./scripts/run.sh --rebuild` — queries must be encoded in the same
  space as the chunks, so switching embedders *requires* a rebuild.
- **Out-of-scope abstention is now handled by an explicit domain gate**
  (`ai/person_b_retrieval/domain_gate.py`), not by the confidence threshold
  alone. A query is classified `IN_DOMAIN` / `AMBIGUOUS` / `OUT_OF_DOMAIN`
  *before* retrieval or generation run, so chit-chat like "how are you" or
  "what is the weather today" never reaches the vector store or the LLM —
  see `abstention_reason` in the API response. Separately, the confidence
  layer's own bug — an empty (all-stopword) query used to read as 100%
  evidence *coverage*, letting the top TF-IDF match look confidently
  correct for a completely unrelated question — is fixed: an empty
  meaningful-term set now reads as zero coverage and hard-caps confidence
  near zero (`ai/person_b_retrieval/confidence.py`). The previous
  five-question eval sample and threshold-disagreement note below still
  describe a real, separate issue (borderline-but-genuine out-of-scope
  questions like GST rates) that the domain gate does not by itself solve;
  raising `abstain_threshold` as described remains open.
- **The user-facing "confidence" percentage is being retired in favour of
  an `evidence_strength` label** (`strong`/`moderate`/`weak`/`insufficient`)
  precisely because the underlying score is uncalibrated similarity, not a
  probability of legal correctness. The raw number is still returned
  (`confidence`, `confidence_calibrated`) as a diagnostic, but the UI now
  leads with the label.
- **Evidence scoring considers jurisdiction and top-result quality, not
  just similarity.** `compute_confidence()` accepts an optional
  `expected_jurisdiction` — defense-in-depth, since `store.query()`
  already hard-filters by jurisdiction at the Chroma metadata level, so
  a mismatched chunk should never actually reach this function in normal
  operation; if it ever did, it can no longer read as strong evidence
  just because its similarity score is high. It also weighs the margin
  between the top and second-best score and how many chunks clear a
  relevance floor, so a single weak match no longer carries the same
  weight as several corroborating ones.
- **Structured logs at the decision points**: every query logs
  `query_domain=<in_domain|ambiguous|out_of_domain>` and, for in-domain
  queries that reach a decision, `evidence_strength=...
  generation_mode=... translation_status=... abstained=...` — greppable,
  and deliberately without the query text or any credentials in the log
  line itself (the query text is still recorded in the audit database,
  which is access-controlled separately).
- **`DEMO_MODE` (default `true`) formalizes the mock-generation fallback.**
  With no `GROQ_API_KEY`, `DEMO_MODE=true` behaves as before (clearly
  labelled `generation: "mock"`); `DEMO_MODE=false` instead returns an
  explicit `generation: "unavailable"` result rather than silently serving
  demo prose in a deployment that expected live answers.
- **Translation status is now four explicit states, not a bool.**
  `ai/translation.py`'s `translation_status()` returns `not_required`,
  `translated`, `unavailable` (no Bhashini credentials configured), or
  `failed` (Bhashini is configured but this specific request broke) —
  `translated: true/false` is kept only for backward compatibility.
- **The language picker is a searchable dropdown covering English plus all
  22 scheduled languages** (`frontend/src/lib/languages.js`,
  `ai/shared/languages.py`), not three header buttons. `GET
  /api/v1/languages` reports the catalog plus whether a real Bhashini
  backend is configured, without ever exposing credentials. Listing a
  language does not promise Bhashini can translate into it right now —
  the backend `configured` flag is the source of truth for that.
- **LLM citations are verified against retrieval, not trusted on the
  model's word.** `ai/person_c_generation/generate.py`'s
  `_verified_citations()` drops any citation whose (act_name, section)
  pair does not match a chunk retrieval actually returned, logging a
  warning — this is a code-level backstop for the system prompt's
  "never invent a citation" instruction, which is not itself an
  enforcement mechanism.
- **`/health` now reports three states** (`ok`/`degraded`/`down`) plus
  `retrieval_ready`, `generation_ready`, `translation_ready`, rather than
  a single ok/degraded boolean.
- **Already correct before this pass, and re-verified rather than
  re-built:** jurisdiction selection is already in the global header
  (`App.jsx`'s `ScopeToggle`); `ai/knowledge_graph` is already wired into
  `ai/compliance/abs.py` and runs on every query; reviewer identity
  (`decided_by`) already comes from the verified auth token, never the
  request body, with a regression test (`test_decided_by_in_the_body_cannot_override_the_token`)
  guarding it. These were mistakenly reported as open gaps earlier in this
  effort — they were not; no code changed for these three.
- **API contract additions**: `generation_provider` ("groq"/"demo"/None)
  and `retrieval_model` (the embedder actually used, e.g. "tfidf") are
  now in the response, alongside the existing `generation`/
  `evidence_strength`/`translation_status` fields — closer to the full
  field list the master prompt's Section 14 describes, though still
  missing `evidence_score` as a separate diagnostic and `jurisdiction`
  as its own top-level echo (it's inferable from `scope`/`answers`, not
  a dedicated field).
- **Source authority weighting exists, at the confidence layer, in a
  narrower form than "affects ranking."** `ai/store.py` now threads
  `instrument_type` (statute/treaty/rule/guideline, from
  `ai/corpus.yaml`'s manifest) through to `MatchedChunk`, and
  `compute_confidence()` applies a small, capped nudge — a statute/treaty
  scores slightly above a guideline at the same similarity, and the gap
  is capped under 10% of the confidence value specifically so an
  authoritative-but-unrelated document can never outrank a more relevant
  one. This is a confidence-level tie-breaker, not a re-ranking of
  retrieval order — the actual candidate ranking happens earlier, in
  `ai/store.py`'s fusion step, which this pass did not touch.
- **`backend/tests/test_generation_modes.py` (new)** covers the
  live/demo-fallback/unavailable matrix from Section 39, with Groq
  mocked at the `call_llm` boundary rather than called for real. Running
  it caught a real bug: the top-level `generation` field's combiner only
  checked for `"live"` and `"mock"` among per-scope modes, so
  `"unavailable"` (no key, `DEMO_MODE=false`) silently collapsed to
  `"none"` — erasing the distinction between "generation is turned off"
  and "there was nothing to answer" that Section 16 exists to make
  visible. Fixed in `ai_service.py`'s generation-mode combiner.
- **Not yet done, called out honestly rather than left silently missing:**
  dedicated `EvidenceStatus`/`GenerationStatus`/`TranslationStatus`
  components — the frontend still exposes these through the patched
  `Confidence` component rather than as separate components.
  `ai/tests/test_translation.py` was not extended with new Bhashini
  failure-path cases (the 4-state status function itself is new and
  covered by manual checks, just not by that file). No sweep of the rest
  of the frontend for other confidence-as-probability assumptions. This
  README section itself is not the clean 10-point rewrite the master
  prompt's Section 47 describes — it is an accumulated, dated log of
  changes and caveats instead.
- **Test verification in this environment used stand-ins, not the real
  tools — read this before trusting "tests pass" claims at face value.**
  This sandbox has no network access to `pip install pytest`,
  `pydantic`, `fastapi`, etc., or to `npm install`. Rather than only
  hand-picking assertions, a minimal pytest-compatible runner
  (fixtures, parametrize, monkeypatch, tmp_path, raises, approx) and
  minimal pydantic/pydantic_settings/fastapi stubs were built
  specifically to actually execute this repo's existing test files and
  call the real `AIService.answer()` / `/health` / `/api/v1/languages`
  code paths end-to-end. Results: `ai/tests/` — 155 passed, 1 failed
  (failure is a missing `openai` package changing an error message, not
  a logic bug). `backend/tests/test_adversarial.py` — 8/8 passed after
  a real bug this process caught was fixed (see below).
  `backend/tests/test_generation_modes.py` (new) — 4/4 passed, after a
  second real bug this process caught was fixed (also below).
  `backend/tests/test_api.py`, `test_auth.py`, `test_insight.py` have
  many failures that are stub limitations (no real ASGI stack, no HTTP
  form encoding, no dependency-injection semantics, `chromadb`/
  `sentence_transformers` genuinely absent) rather than confirmed code
  regressions — spot-checked several by hand (`test_health`,
  `test_query_success`) and traced each to a missing package or stub
  gap, not new code. Treat this as strong evidence for the
  domain-gate/confidence/schema/health/language-endpoint changes
  specifically, and as unverified for auth, patent-case, and
  update-review endpoints, which this pass did not touch and could not
  fully exercise. `pytest`, `npm run build`, and a real deployment run
  should still happen before this ships.
- **A real regression was found and fixed via this process, not just
  hand-picked assertions.** The domain gate's first draft rejected any
  query without recognised legal/IP vocabulary as `OUT_OF_DOMAIN` — which
  broke an existing adversarial test (`test_india_scope_never_retrieves_international_chunks`)
  by rejecting "What is the deadline?", a legitimate in-context follow-up
  with no domain jargon. Fixed in `ai/person_b_retrieval/domain_gate.py`:
  the gate now only rejects recognised chit-chat/greeting patterns or
  queries with zero meaningful content tokens at all (reusing
  confidence.py's own tokenizer for consistency) — everything else with
  real content is passed to retrieval, where the evidence layer decides
  based on what the corpus actually supports. This matches the master
  prompt's own explicit warning against simplistic keyword rejection
  (Section 5) more faithfully than the first draft did.
- **A second real bug was found the same way and fixed**: the domain
  gate's `OUT_OF_DOMAIN`/`AMBIGUOUS` early-return responses were reading
  `self.confidence_calibrated`, a property that lazily loads the
  embedder — defeating the entire point of abstaining before touching
  retrieval. Fixed to report `confidence_calibrated: true` directly in
  those paths without touching the embedder. Verified by calling
  `ai_service.answer("how are you")` directly and confirming no
  embedder/vector-store code executes.
- **Retrieval is hybrid, and Recall@5 is 82.4%.** Dense vector search plus a
  BM25-style lexical pass (`ai/store.py`), over chunks capped at 1200/1800
  characters. That cap is load-bearing: at the previous 2000/3500 the same
  questions scored 58.8%, because a long section dilutes its own decisive
  clause past the point the lexical pass can find it. The remaining misses
  are mostly a neighbouring provision of the right Act outranking the
  governing one, so read the passages on the Evidence view rather than
  trusting the ranking. There is no cross-encoder rerank stage.
- **Deadlines marked "unverified"** come from rules whose current figures
  were not confirmed against amended text; the request-for-examination
  window in particular changed in 2024. Confirm before relying on any date.
- **Nothing here is legal advice.** Every obligation must be checked against
  the bare text of the cited provision and with a registered patent agent.
