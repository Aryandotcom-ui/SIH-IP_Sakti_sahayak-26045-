import { useState, useRef, useEffect } from 'react';
import { Chevron, Info, Alert, Plug, Refresh, Globe, Pin, Check } from './Icons.jsx';
import { SCOPES } from '../lib/api.js';

/** Small explanatory tooltip — this product is full of terms of art
 *  (abstention, ABS, TKDL) that a first-time user will not know. */
export function Explain({ children }) {
  const [open, setOpen] = useState(false);
  return (
    <span style={{ position: 'relative', display: 'inline-block' }}>
      <span
        className="info-dot"
        tabIndex={0}
        role="button"
        aria-label="What does this mean?"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >i</span>
      {open && (
        <span
          role="tooltip"
          className="fade"
          style={{
            position: 'absolute', bottom: 'calc(100% + 9px)', left: '50%',
            transform: 'translateX(-50%)', width: 260, zIndex: 60,
            background: 'var(--ink-900)', color: 'var(--paper)',
            padding: '11px 13px', borderRadius: 10, fontSize: 13,
            lineHeight: 1.5, fontWeight: 400, boxShadow: 'var(--shadow-lg)',
            textTransform: 'none', letterSpacing: 0,
          }}
        >{children}</span>
      )}
    </span>
  );
}

/** Accordion with a measured height transition (no layout jank). */
export function Disclose({ title, meta, children, defaultOpen = false, className = '' }) {
  const [open, setOpen] = useState(defaultOpen);
  const inner = useRef(null);
  const [h, setH] = useState(defaultOpen ? 'auto' : 0);

  useEffect(() => {
    if (!inner.current) return;
    setH(open ? inner.current.scrollHeight : 0);
  }, [open, children]);

  return (
    <div className={className}>
      <button className="source-head" aria-expanded={open} onClick={() => setOpen(o => !o)}>
        <Chevron dir={open ? 'up' : 'down'} size={17} style={{ color: 'var(--text-faint)', flexShrink: 0 }} />
        <span style={{ flex: 1, minWidth: 0 }}>{title}</span>
        {meta}
      </button>
      <div style={{ height: h, overflow: 'hidden', transition: 'height 260ms cubic-bezier(.2,.7,.3,1)' }}>
        <div ref={inner} className="source-body">{children}</div>
      </div>
    </div>
  );
}

/** Confidence as a visible meter. The number alone means nothing to a
 *  non-specialist, so it is always paired with a plain-language reading. */
// Evidence strength is a semantic label ("strong"/"moderate"/"weak"/
// "insufficient"), not a percentage. A raw similarity score — whether
// from the TF-IDF fallback or an embedding model's cosine similarity —
// is not a calibrated probability that the answer is legally correct, so
// it is no longer the headline number here. The percentage is kept as a
// small secondary diagnostic for people who want it, always labelled as
// uncalibrated evidence rather than confidence.
const STRENGTH_LABEL = {
  strong: 'Strong',
  moderate: 'Moderate',
  weak: 'Weak',
  insufficient: 'Insufficient',
};

const STRENGTH_NOTE = {
  strong: 'Multiple relevant sources closely match your question.',
  moderate: 'Some relevant sources match — read them before relying on this.',
  weak: 'Only weak overlap with the cited sources. Treat this as a lead, not an answer.',
  insufficient: 'Too little relevant evidence to answer from. Treat nothing here as settled.',
};

export function EvidenceStatus({ value, abstained, calibrated = true, evidenceStrength }) {
  const pct = Math.round((value ?? 0) * 100);
  const band = abstained ? 'low' : pct >= 70 ? 'high' : pct >= 45 ? 'medium' : 'low';
  const strength = evidenceStrength
    ?? (abstained ? 'insufficient' : band === 'high' ? 'strong' : band === 'medium' ? 'moderate' : 'weak');
  const color = strength === 'strong' ? 'var(--ok)'
    : strength === 'moderate' ? 'var(--warn)' : 'var(--stop)';
  const note = !calibrated
    ? 'Running on the offline stand-in search backend, whose score does not indicate topical relevance — it rates unrelated questions as highly as real ones. Read the cited sources; do not read this label as a probability.'
    : STRENGTH_NOTE[strength];

  return (
    <div className="conf">
      <div className="conf-top">
        <span className="conf-label">
          Evidence strength
          <Explain>
            Reflects semantic relevance, lexical overlap, jurisdiction match and agreement
            among retrieved sources. It is not a probability that the legal answer is correct.
            Below a minimum bar the system abstains instead of guessing.
          </Explain>
        </span>
        <span className="conf-val" style={{ color }}>
          {STRENGTH_LABEL[strength] ?? strength}
        </span>
      </div>
      <div className="conf-track">
        <div className="conf-fill" style={{ width: `${Math.max(pct, 2)}%`, background: color }} />
      </div>
      <p className="conf-note">
        {note}
        {calibrated && (
          <span style={{ opacity: 0.6 }}> ({pct}% uncalibrated evidence score)</span>
        )}
      </p>
    </div>
  );
}

/**
 * Backwards-compatible alias.
 *
 * `Confidence` was the original name and is still what Evidence.jsx and
 * any external consumer import. Keeping it pointed at EvidenceStatus
 * means the rename does not silently change what those call sites
 * render — but new code should use EvidenceStatus, because the old name
 * is the misleading one: the component deliberately does not present a
 * confidence, it presents an evidence strength.
 */
export const Confidence = EvidenceStatus;

/**
 * How the prose in front of you was produced.
 *
 * Split out of the Confidence component, which had grown to carry three
 * unrelated statuses because it happened to be the thing already sitting
 * in the answer header. They are separate facts about an answer —
 * evidence is about retrieval, this is about generation, translation is
 * about the language edge — and a component that conflates them makes it
 * easy to render one while silently dropping another.
 *
 * "unavailable" is the case worth being careful about: it means no key
 * was configured AND demo mode is off, so there is no prose at all
 * rather than canned prose. Collapsing it into "none" was a real bug
 * fixed earlier in this codebase; showing it as "mock" would be worse.
 */
const GENERATION_COPY = {
  live: null, // the normal case needs no badge
  mock: {
    tone: 'warn',
    label: 'Canned prose — no API key',
    help: 'The retrieved sections, citations and compliance screening below are real. Only the wording of the answer is a deterministic stand-in, because no GROQ_API_KEY is configured. Set one to get a generated answer.',
  },
  unavailable: {
    tone: 'stop',
    label: 'No answer generated',
    help: 'No generation key is configured and demo mode is off, so no prose was produced at all. The citations and sources below are still real retrieval output — read those.',
  },
  none: {
    tone: 'info',
    label: 'No generation run',
    help: 'The system abstained before generating, so no model was called. This is the intended behaviour when the evidence does not support an answer.',
  },
  failed: {
    tone: 'warn',
    label: 'Answer wording failed',
    help: 'A generation backend is configured but this request to it failed, so no prose was produced for this query. The citations and retrieved passages below are real retrieval output and are unaffected. This is a transient backend problem, not a limit of the corpus — retrying may work.',
  },
};

export function GenerationStatus({ generation, provider }) {
  const copy = GENERATION_COPY[generation];
  if (!copy) return null;
  return (
    <Badge tone={copy.tone}>
      {copy.label}
      {provider && provider !== 'groq' ? ` (${provider})` : ''}
      <Explain>{copy.help}</Explain>
    </Badge>
  );
}

/**
 * Whether the answer is actually in the language that was asked for.
 *
 * The only state that must never be shown wrongly is "translated": a
 * reader who asked for Hindi and is looking at English needs to know
 * that, and the text alone cannot tell them, because a failed
 * translation and a successful one return the same field. So
 * "unavailable" and "failed" are rendered distinctly and visibly, and
 * the successful case renders nothing at all — a badge on every correct
 * answer is noise that trains people to ignore the badge.
 */
const TRANSLATION_COPY = {
  not_required: null,
  translated: null,
  unavailable: {
    tone: 'warn',
    label: 'Not translated',
    help: 'No translation backend is configured (BHASHINI_API_KEY / BHASHINI_USER_ID are unset), so this answer is in English rather than the language you asked for. The legal content is unaffected.',
  },
  failed: {
    tone: 'warn',
    label: 'Translation failed',
    help: 'A translation backend is configured but this request to it failed, so this answer fell back to English. This is a transient backend problem, not a limit of the corpus — retrying may work.',
  },
};

export function TranslationStatus({ status, language }) {
  const copy = TRANSLATION_COPY[status];
  if (!copy) return null;
  return (
    <Badge tone={copy.tone}>
      {copy.label}{language ? ` — asked for ${language}` : ''}
      <Explain>{copy.help}</Explain>
    </Badge>
  );
}

/**
 * The answer the system gives when it will not give an answer.
 *
 * Three distinct reasons, three distinct messages. Collapsing them into
 * one "I don't know" would be the easy thing and the wrong one: "your
 * question is outside what I cover", "I need you to tell me what you
 * mean" and "I looked and the corpus does not cover this" call for three
 * different next actions from the reader, and only the third is about
 * the corpus at all.
 */
export function AbstentionCard({
  reason, text, clarificationOptions = [], insufficient, intl, onPick,
}) {
  const title =
    reason === 'out_of_domain' ? 'Outside supported scope'
    : reason === 'ambiguous' ? 'I need a little more information'
    : insufficient ? `Nothing in the ${intl ? 'international' : 'Indian'} corpus covers this`
    : 'The corpus doesn’t clearly answer this';

  return (
    <div className="abstain">
      <Info size={21} style={{ color: 'var(--info)', flexShrink: 0, marginTop: 2 }} />
      <div>
        <h4>{title}</h4>
        <p>{text}</p>
        {reason === 'ambiguous' && clarificationOptions.length > 0 && (
          <div className="row-wrap" style={{ gap: 8, marginTop: 10 }}>
            {clarificationOptions.map(opt => (
              onPick
                ? <Chip key={opt} onClick={() => onPick(opt)}>{opt}</Chip>
                : <Badge key={opt} tone="neutral">{opt}</Badge>
            ))}
          </div>
        )}
        {(!reason || reason === 'insufficient_evidence') && (
          <p style={{ marginTop: 8 }}>
            Rather than assemble a confident-sounding paragraph from weak matches, the
            system stops here. Narrowing the question, or adding your formulation
            details above, often brings the right provisions into range.
          </p>
        )}
      </div>
    </div>
  );
}

export function Badge({ tone = 'neutral', children, ...p }) {
  return <span className={`badge badge-${tone}`} {...p}>{children}</span>;
}

export function Chip({ active, children, ...p }) {
  return <button type="button" className="chip" aria-pressed={!!active} {...p}>{children}</button>;
}

export function Empty({ icon, title, children }) {
  return (
    <div className="empty">
      <div className="empty-ico">{icon}</div>
      <h3 style={{ fontSize: 19, marginBottom: 8 }}>{title}</h3>
      <p className="muted" style={{ maxWidth: '46ch', margin: '0 auto', fontSize: 14.6 }}>{children}</p>
    </div>
  );
}

export function Disclaimer({ children }) {
  return (
    <div className="disclaimer">
      <Info size={17} style={{ flexShrink: 0, marginTop: 1, color: 'var(--text-faint)' }} />
      <span>{children}</span>
    </div>
  );
}

/**
 * A failed request, said plainly.
 *
 * This replaces the sample-data fallback the app used to show. Inventing a
 * legal answer to cover for an unreachable backend is the exact failure this
 * project exists to prevent, so an unreachable backend now looks like one —
 * with the cause named and a retry to hand.
 */
export function ErrorState({ error, onRetry, what = 'this' }) {
  const kind = error?.kind ?? 'server';
  const title = {
    offline: 'Can’t reach the API',
    timeout: 'The API didn’t answer in time',
    notready: 'The corpus isn’t ready yet',
    auth: 'Your session has ended',
    forbidden: 'Your account can’t do that',
    server: `Couldn’t load ${what}`,
  }[kind];
  const help = {
    offline: (
      <>
        Nothing is answering at the API address. Start the backend with{' '}
        <code>./scripts/run.sh</code>, or check that <code>VITE_API_BASE</code>{' '}
        points at a running service.
      </>
    ),
    timeout: 'A free-tier server sleeps when idle and can take up to a minute to wake. It stays fast once it is up.',
    notready: (
      <>
        The API is running but its search index is missing. Build it with{' '}
        <code>./scripts/run.sh --rebuild</code>.
      </>
    ),
    auth: 'Sign in again to continue. Reviewer sessions end when the browser tab closes.',
    forbidden: 'You are signed in, but this action needs a higher role. Approving corpus updates needs REVIEWER; publishing them needs ADMIN.',
    server: 'The API answered with an error. The message it gave is below.',
  }[kind];

  return (
    <div className="errorstate" role="alert">
      <div className="errorstate-ico">
        {kind === 'offline' ? <Plug size={22} /> : <Alert size={22} />}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <h3 className="errorstate-title">{title}</h3>
        <p className="errorstate-help">{help}</p>
        {error?.message && <p className="errorstate-detail mono">{error.message}</p>}
      </div>
      {onRetry && (
        <button className="btn btn-ghost btn-sm" onClick={onRetry}>
          <Refresh size={15} /> Try again
        </button>
      )}
    </div>
  );
}

/**
 * The jurisdiction scope control.
 *
 * Deliberately a segmented control rather than a dropdown: which legal system
 * an answer came from is not a setting to go hunting for, and the selected one
 * has to be readable at a glance while you type. `counts` is the real corpus
 * count per jurisdiction, so a scope with nothing ingested says so instead of
 * looking merely unhelpful when it returns nothing.
 */
export function ScopeToggle({ value, onChange, counts, disabled, compact = false }) {
  return (
    <div className={`scope${compact ? ' scope-compact' : ''}`} role="group" aria-label="Jurisdiction scope">
      {SCOPES.map(sc => {
        const n = sc.jurisdiction
          ? counts?.[sc.jurisdiction]
          : Object.values(counts ?? {}).reduce((a, b) => a + b, 0) || undefined;
        return (
          <button
            key={sc.value}
            type="button"
            className="scope-opt"
            aria-pressed={value === sc.value}
            disabled={disabled}
            onClick={() => onChange(sc.value)}
            title={sc.hint}
          >
            {sc.value === 'INTL' ? <Globe size={14} /> : sc.value === 'IN' ? <Pin size={14} /> : null}
            {sc.label}
            {n != null && <span className="scope-n">{n}</span>}
          </button>
        );
      })}
    </div>
  );
}

/** Which legal system a citation belongs to, shown on the citation itself so
 *  it is never ambiguous even inside a single-jurisdiction answer. */
export function JurisdictionTag({ jurisdiction }) {
  if (!jurisdiction) return null;
  const intl = jurisdiction === 'international';
  return (
    <span className={`jtag ${intl ? 'jtag-intl' : 'jtag-in'}`}>
      {intl ? <Globe size={11} /> : <Pin size={11} />}
      {intl ? 'International' : 'India'}
    </span>
  );
}

/**
 * A GREEN / AMBER / RED screening result.
 *
 * The reason line is not decoration. GREEN here means both that no
 * obligation fired and that the screening had enough facts to mean it —
 * "nothing triggered" and "nothing triggered because nobody answered the
 * question that decides it" are different findings, and only the first is
 * green. See _screening_status in backend/app/api/insight_routes.py.
 */
export function StatusBand({ status, reason }) {
  const tone = {
    GREEN: { cls: 'ok', label: 'No obligations triggered' },
    AMBER: { cls: 'warn', label: 'Obligations or open questions' },
    RED: { cls: 'stop', label: 'Blocking obligations' },
    UNKNOWN: { cls: 'neutral', label: 'Could not be screened' },
  }[status] ?? { cls: 'neutral', label: 'Could not be screened' };

  return (
    <div className={`band band-${tone.cls}`} role="status">
      <span className="band-dot" aria-hidden="true" />
      <div style={{ minWidth: 0 }}>
        <strong className="band-title">{tone.label}</strong>
        <p className="band-reason">{reason}</p>
      </div>
      <span className="band-tag">{status}</span>
    </div>
  );
}

/** A labelled figure. Shows a dash, never a zero, for a number that has not
 *  arrived — on a page whose whole claim is that its numbers are real, an
 *  invented placeholder is the wrong thing to fake. */
export function Stat({ value, label, hint }) {
  return (
    <div className="stat">
      <div className="stat-n">{value ?? '—'}</div>
      <div className="stat-l">{label}{hint && <Explain>{hint}</Explain>}</div>
    </div>
  );
}

/** A verified/unverified marker for a single citation. */
export function VerifyMark({ verified }) {
  return verified
    ? <span className="vmark vmark-ok"><Check size={12} /> supported by a retrieved passage</span>
    : <span className="vmark vmark-no"><Alert size={12} /> not found in the retrieved passages</span>;
}

/**
 * The index is missing.
 *
 * An unbuilt corpus abstains on every question at 0% confidence, which looks
 * exactly like a working product that cannot answer anything — the same
 * reply to every input, with no hint that the cause is a missing build step
 * rather than the question. This says which, before the user has typed
 * anything, because the alternative is watching them conclude the whole
 * system is broken.
 */
export function CorpusMissing() {
  return (
    <div className="notice notice-stop" role="alert" style={{ marginBottom: 20 }}>
      <Alert size={18} style={{ flexShrink: 0 }} />
      <span>
        <strong>The search index has not been built.</strong> There are no passages to
        search, so every question will abstain at 0% confidence regardless of what you
        ask — this is a missing build step, not a limit of the corpus. Build it with{' '}
        <code>./scripts/run.sh</code>, or directly:{' '}
        <code>python -m ai.cli data/pdfs --manifest ai/corpus.yaml --model tfidf</code>
      </span>
    </div>
  );
}
