# IP-SAKTI Sahayak

Multilingual, citation-grounded AI assistant for Ayurvedic intellectual
property and regulatory guidance.

## Smart India Hackathon Problem Statement

> **IP-SAKTI Sahayak a multilingual, RAG-based (source-cited) AI assistant for Intellectual Property and regulatory guidance in Ayurveda, across national and international regimes.**

Ask a question in plain language and get an answer that names the sections
it rests on, shows you their verbatim text, and screens your facts against
the access-and-benefit-sharing duties that Ayurvedic IP filings trigger —
the ones applicants usually do not know to ask about.

## What runs today

Working end to end, in this repository, today:

| | |
|---|---|
| **Corpus** | 3,300 chunks from 31 statutes, rules and treaties — Patents, GI, Trade Marks, Designs, Copyright, PPVFR, Biological Diversity (2002 + 2023 amendment + 2024 Rules), Drugs & Cosmetics, Drugs & Magic Remedies, FSSAI Ayurveda Aahar, Cosmetics Rules; TRIPS, CBD, Nagoya, WIPO GRATK 2024, PCT, Paris, Madrid, Hague, Budapest, EU THMPD |
| **Jurisdiction separation** | India / International / Both, filtered at the index before ranking. "Both" is two retrievals and two generations rendered as two labelled blocks — never one merged ranking |
| **Formulation routing** | All six regulatory categories (classical, proprietary, new drug, phytopharmaceutical, Ayurveda Aahar, cosmetic) mapped through a regulatory graph to the regimes that govern them |
| **ABS compliance engine** | 14 obligations with legal basis, triggering conditions, defeating exemptions, authority, form and deadline — rule-driven, so it answers where retrieval cannot |
| **Citation verification** | Every citation a model returns is checked against an actually-retrieved `(act_name, section)` pair and dropped if it was invented |
| **Abstention** | Three distinct refusals — out of domain, ambiguous intent, insufficient evidence — each with its own next step for the reader |
| **Audit & consent** | Per-query audit trail, per-act consent gating for licensed sources, retention bound, JWT + bcrypt role gating on the reviewer console |
| **Tests** | 354 passing, green both with and without a prebuilt index; CI runs corpus-integrity, index build, the suite and the frontend build |

### Measured results

Both figures come from the same runner over the same 37-question set
(`ai/person_c_generation/eval/`), and both are reproducible:

```
$ python -m ai.person_c_generation.eval.eval_runner

generation: 37/37 passed  (100.0%)

  category                   passed
  abs                      7/7   100.0%
  gi                       1/1   100.0%
  jurisdiction_intl        4/4   100.0%
  labelling                2/2   100.0%
  patentability            8/8   100.0%
  temporal                 2/2   100.0%
  tk                       3/3   100.0%
  unanswerable            10/10  100.0%
```

That is the **generation contract**: given the right passages, does the
answer cite the provision it should, and does it abstain when handed
nothing to work with? 37/37, including all ten deliberately unanswerable
questions. It is not a claim about search quality, because the passages
are supplied by the fixtures.

Search quality is the second number, and it is the honest one to read
next — same runner, `--retrieval`, against the real index:

```
$ python -m ai.person_c_generation.eval.eval_runner --retrieval

Recall@5                    12/17   70.6%
abstention accuracy         17/22   77.3%
  correctly abstained       0/5    0.0%
  correctly answered        17/17  100.0%
```

Recall@5 of 70.6% means the governing provision reached the top five for
12 of 17 answerable questions. The 0/5 is the one that matters and we are
not going to dress it up: with the offline TF-IDF backend and the shipped
abstention threshold, five out-of-scope questions ("what is the GST rate
on Ayurvedic medicines?") got answered instead of refused. Both numbers
are a property of the lexical fallback embedder described in **Known
limitations** below, not of the pipeline around it — the same eval is the
instrument for showing that, which is why it is published rather than
summarised.

## Run it

You need Python 3.11+, Node 18+, and this repository. One command:

```bash
./scripts/run.sh
```

Then open **<http://localhost:5173>**.

That installs dependencies, builds the search index from `data/pdfs` (about
a minute, first run only), and starts the API and the web UI together.

> **Open the URL, not the file.** Double-clicking `frontend/index.html` in a
> file manager cannot work. The page is compiled by the dev server when it is
> requested, and a `file://` page has no origin from which to reach the API.
> There is no sample-data fallback: if the UI says it cannot reach the API,
> the backend is not running — start it with the command above.

Other options:

```bash
./scripts/run.sh --backend    # API only; docs at localhost:8000/docs
./scripts/run.sh --rebuild    # discard and rebuild the search index
```

### Generated answer wording requires a Groq API key

Set `GROQ_API_KEY` to enable live answer generation:

```bash
export GROQ_API_KEY=gsk_...
./scripts/run.sh
```

Without a key, `DEMO_MODE` is **off by default** and the generation step is
reported as unavailable rather than returning canned prose. Retrieval,
citations, evidence scoring and compliance screening remain real; only the
LLM wording step is unavailable.

## Deploying it

The two halves deploy to different places, because they are different kinds
of thing. The UI is static files. The API is a long-running Python process
that memory-maps a ~200MB vector index — it cannot run as a serverless
function: Netlify Functions run JS/TS and Go rather than Python, and cap at
250MB unzipped, which the dependencies alone exceed.

**API — Render (free tier).** `render.yaml` is a blueprint: in the Render
dashboard choose New -> Blueprint and point it at this repository. It
installs the dependencies, builds the index from `data/pdfs` during the
build, and serves with uvicorn. Set two variables it deliberately does not
commit:

| Variable | Value |
|---|---|
| `CORS_ORIGINS` | your Netlify origin, no trailing slash, e.g. `https://your-site.netlify.app` |
| `GROQ_API_KEY` | optional; without it the prose is a labelled stand-in |

**UI — Netlify.** `netlify.toml` sets the build, the publish directory and
the single-page-app rewrite that makes `/ask` survive a reload. Set one
build variable, or every page will report that it cannot reach the API:

| Variable | Value |
|---|---|
| `VITE_API_BASE` | `https://<your-render-service>.onrender.com/api/v1` |

Deploy the API first: you need its URL for `VITE_API_BASE`, and it needs
the Netlify origin for `CORS_ORIGINS`, so the second deploy of each side is
the one that works.

### The free tier sleeps

Render's free tier stops an idle service and takes up to a minute to wake
it. The first request after a quiet spell is slow; every request after it
is not. The UI waits 60s and explains the delay after ten, so a cold start
reads as "starting" rather than "broken" — but someone clicking during a
demo still waits. Open the site once a few minutes beforehand.

## Jurisdiction scope

Every question is answered under a jurisdiction you pick: **India**,
**International**, or **Both**. This is a hard filter on retrieval, not a
label on the output — it decides which chunks are eligible before the
search runs.

The corpus is already tagged for it: each document's `jurisdiction` in
`ai/corpus.yaml` is copied onto every chunk's vector metadata at ingest, so
the filter is a `where` clause on the index rather than a post-hoc sort.

**"Both" is never one merged search.** It runs two separately filtered
retrievals and two separate generation calls, each grounded only in its own
jurisdiction and each told explicitly not to reach outside it — the
guardrail against the model topping an answer up from training knowledge
that retrieval deliberately excluded. The two answers are rendered as
separate labelled blocks, never run together, and every citation carries its
own jurisdiction tag.

If nothing in the selected jurisdiction matches well enough, the system says
so and names the other scope rather than generating an ungrounded answer —
"I don't have India-specific guidance on this in the corpus… try the
International scope, or Both."

## What is in the box

| Path | What it does |
|---|---|
| `ai/` | PDF extraction, sectioning, chunking, embedding, retrieval, abstention |
| `ai/compliance/` | Defeasible ABS / IP obligation graph; obligations suppressed by exemptions |
| `ai/patent_prep/` | Intake, prior-art precheck, Form 1/3/27 drafts, deadline tracking |
| `ai/updates/` | Source watcher and tiered review gate for amended law |
| `ai/audit.py` | DPDP-aligned audit trail and licensed-source citation gate |
| `ai/translation.py` | Bhashini translation; retrieval always runs on English. The source language is auto-detected from the query script — there is no language picker in the UI |
| `backend/` | FastAPI service over the above |
| `frontend/` | React web UI (Vite), proxied to the API in development |
| `data/pdfs/` | The physical legal corpus: 31 PDFs currently present, represented by a 34-document manifest with 31 ingested and 3 pending entries |

The search index (`data/chroma/`) is **not** in version control. It is
derived from `data/pdfs` and rebuilds in about a minute, so it is generated
rather than versioned.

## Tests

```bash
python3 -m pytest -q          # 354 passed
```

No prebuilt index is needed: the suite passes both on a fresh clone and
against a built corpus, so a reviewer can run it before running anything
else. The eval suite is separate and reported under
[Measured results](#measured-results) above — it is a scored benchmark to
run deliberately, not a gate on every commit.
## How it works

Ten points, in the order a question travels through the system.

1. **Hybrid retrieval.** Every query runs two retrievals over the same
   jurisdiction-filtered corpus and fuses them by rank, not by raw score:
   dense semantic search over the Chroma vector index, and corpus-wide
   BM25 lexical search with a small exact-phrase bonus. Cosine distance
   and BM25 are different scoring systems on incomparable scales, so
   adding them directly would be meaningless; reciprocal rank decay lets
   a strong lexical hit on exact statutory wording compete with a strong
   semantic hit without pretending the two numbers measure the same
   thing. A literal section reference ("Section 3(p)") short-circuits
   both and goes straight to an exact lookup.

2. **Authority re-ranking.** Fused candidates are then re-ranked by what
   kind of instrument they come from — a statute or treaty above a rule,
   a rule above explanatory guidance — and demoted if their jurisdiction
   does not match the scope being searched. This is a bounded multiplier
   (floor 0.90, so at most a 10% adjustment), never a ranking dimension
   of its own. That bound is the safety property: relevance still
   dominates by roughly an order of magnitude, so authority can resolve
   a near-tie but can never lift an authoritative *irrelevant* passage
   over a relevant one. An index with no `instrument_type` metadata
   ranks exactly as it did before, rather than being silently penalised.

3. **Evidence-strength evaluation.** What comes back is scored on
   whether it actually *covers* the question — term coverage, agreement
   between the top sources, the margin between the best hit and the
   pack, how many independent sources support it, and a capped source-
   authority nudge. The result is reported as a semantic label
   (`strong` / `moderate` / `weak` / `insufficient`), not as a
   percentage. The raw number is still available as `evidence_score`,
   deliberately under a name that does not read as a probability: a
   similarity score is not the probability that a legal answer is
   correct, and any interface that renders it as "87% confident" is
   claiming something this system cannot support.

4. **Abstention.** The system refuses to answer in three distinct ways,
   and says which. A **domain gate** runs before retrieval and
   classifies the query `IN_DOMAIN` / `AMBIGUOUS` / `OUT_OF_DOMAIN`, so
   chit-chat never reaches the vector store or the model
   (`out_of_domain`). An object-less intent — "can I protect this?" with
   nothing named — returns clarification options instead of a guess
   (`ambiguous`). And evidence below the threshold abstains rather than
   assembling a confident paragraph from weak matches
   (`insufficient_evidence`). Each carries a different next action for
   the reader, so collapsing them into one "I don't know" would be the
   easy thing and the wrong one.

5. **TF-IDF and BGE.** The repository's local and Render deployment path
   uses the fitted character-ngram TF-IDF embedder by default. `BAAI/bge-small-en-v1.5`
   remains the optional neural embedder when model weights are available;
   switching to it requires a full index rebuild because queries and chunks
   must share the same vector space. TF-IDF matches wording
   rather than meaning, so a question phrased far from the statute's
   language can retrieve the wrong Act, and it sets `CALIBRATED = False`
   so the interface says its scores are not meaningful rather than
   quietly presenting them as if they were. **Queries must be encoded in
   the same vector space as the chunks**, so switching embedders
   requires a full rebuild — `./scripts/run.sh --rebuild`. `get_embedder()`
   fails loudly on an unavailable model rather than silently degrading;
   only an explicit `--allow-fallback-embeddings` gets you placeholder
   vectors, and an index built that way is useless for retrieval.

6. **Groq live generation.** With `GROQ_API_KEY` set, answer prose is
   generated from the retrieved passages and every citation the model
   returns is verified against an actually-retrieved chunk's
   `(act_name, section)` pair before it is shown. A citation the model
   invented is dropped rather than displayed — a fabricated section
   number is the single most damaging output this system could produce,
   because it looks exactly like a real one.

7. **Generation safety.** `DEMO_MODE` is off by default. Without a key,
   generation reports `unavailable` — meaning no prose was produced at all.
   Retrieval, citations, evidence and compliance screening remain available.
   Demo mode can still be enabled explicitly for development/testing.

8. **Bhashini translation.** Non-English queries are translated to
   English before retrieval — not as a UX nicety, but because the
   embedding model is English-only and an untranslated query does not
   retrieve reliably. The answer translates back at the end. Citations
   and `act_name` are never translated: a citation is a legal
   identifier, and translating it would break the exact-match contract
   with `ai/corpus.yaml`. Translation reports one of four states —
   `not_required`, `translated`, `unavailable` (no credentials) or
   `failed` (configured but this request broke) — and **never reports
   `translated` unless a backend actually ran**. The success and failure
   paths return the same text; only the flag distinguishes them, so a
   reader who asked for Hindi and is looking at English depends entirely
   on that flag being honest.

9. **Language detection and translation.** The UI does not expose a language
   selector. The backend detects the language from the query when no explicit
   language is supplied, and Bhashini translation is used when its credentials
   are configured.

10. **Jurisdiction selection.** India, international, or both. "Both" is
    two separately filtered retrievals and two separate generation
    calls, rendered as two labelled blocks — never one merged ranking. A
    Patents Act clause and a PCT rule belong to different legal systems
    and must never be stitched into a single paragraph or allowed to
    crowd each other out of one similarity ranking.

## Known limitations

These are real and worth knowing before you rely on anything here.

- **Nothing here is legal advice.** Every obligation must be checked
  against the bare text of the cited provision and with a registered
  patent agent.
- **25 of the 34 manifest documents have no `source_url`**, so their
  provenance is recorded in the manifest's `acquisition` block instead.
  The manifest contains 31 `ingested` entries and 3 `pending` ones, and
  those two sets now match the filesystem exactly: every ingested entry
  has its PDF and no pending entry does.
- **Three instruments are cited but not held.** The Patents (Amendment)
  Rules, 2024 and the FDA botanical-drug guidance have never been
  acquired; the Designs Rules, 2001 copy was a page-image scan with no
  text layer, so it produced nothing and has been removed rather than
  left to fail every ingest. The 2024 patent rules are the consequential
  gap: three deadlines in `ai/patent_prep/deadlines.yaml` carry
  `review_status: draft` precisely because that text is missing.

- **The default TF-IDF embedder is lexical rather than neural-semantic** —
  see point 5 above. Its scores are explicitly treated as uncalibrated.
  The optional BGE backend provides neural embeddings when model weights
  are deliberately enabled and the index is rebuilt.
- **There is no cross-encoder rerank stage.** Ranking errors are mostly
  a neighbouring provision of the right Act outranking the governing
  one, so read the passages on the Evidence view rather than trusting
  the order.
- **Bhashini integration is written against the documented ULCA
  pipeline but has never been exercised against the live service.** The
  default pipeline id and endpoint shapes are best-effort; confirm them
  against current Bhashini documentation before relying on this in
  production.
- **Deadlines marked "unverified"** come from rules whose current
  figures were not confirmed against amended text; the
  request-for-examination window in particular changed in 2024.
- **The corpus is a snapshot.** Nothing here tracks amendments in real
  time except through the review queue, which requires a human to
  approve each change.

## Implementation history

Detailed, dated notes on how the system reached its current behaviour —
including the bugs found and what they were traced to — have moved to
[CHANGELOG.md](CHANGELOG.md).

## Licence and disclaimer

Informational only. Not legal advice. The corpus consists of public legal
instruments; each document's provenance is recorded in `ai/corpus.yaml`.
