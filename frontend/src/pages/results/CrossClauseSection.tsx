/**
 * Cross-Clause Coherence — Phase 3.5 (Sprint R5/R6).
 *
 * The connective-tissue checks: risk → control → monitoring, objectives →
 * measurement → review, etc. Each chain is a short narrative verdict with
 * inline file citations. BROKEN/PARTIAL chains surface first.
 */
import { useState } from 'react';
import type { CrossClauseFinding } from '@/lib/api';

interface Props {
  findings: CrossClauseFinding[];
}

function ChevronIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function lastPathSegment(path: string): string {
  if (!path) return '';
  const normalised = path.replace(/\\/g, '/');
  const idx = normalised.lastIndexOf('/');
  return idx >= 0 ? normalised.slice(idx + 1) : normalised;
}

const STATUS_ORDER: Record<CrossClauseFinding['status'], number> = {
  BROKEN: 0,
  PARTIAL: 1,
  NOT_ASSESSABLE: 2,
  LINKED: 3,
};

function statusBadge(status: CrossClauseFinding['status']) {
  switch (status) {
    case 'LINKED':         return <span className="badge badge-conf">Linked</span>;
    case 'PARTIAL':        return <span className="badge badge-minor">Partial</span>;
    case 'BROKEN':         return <span className="badge badge-major">Broken</span>;
    default:               return <span className="badge badge-obs">Not assessable</span>;
  }
}

function displayClause(id: string): string {
  const m = id.match(/^(\d+)_(\d+)(?:_(\d+))?(?:_(\d+))?$/);
  if (!m) return id;
  const [, std, a, b, c] = m;
  return `${std} §${[a, b, c].filter(Boolean).join('.')}`;
}

export function CrossClauseSection({ findings }: Props) {
  const problematic = findings.filter((f) => f.status === 'BROKEN' || f.status === 'PARTIAL');
  const [expanded, setExpanded] = useState(problematic.length > 0);

  if (findings.length === 0) return null;

  const sorted = [...findings].sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status]);
  const linkedCount = findings.filter((f) => f.status === 'LINKED').length;

  return (
    <section className={`expiry-section${expanded ? ' expanded' : ''}`}>
      <button
        type="button"
        className="expiry-head"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <span className="expiry-head-title">Cross-clause coherence</span>
        <span className="expiry-head-counts">
          {problematic.length > 0 && (
            <span className="expiry-count expiry-count-expired">
              {problematic.length} chain{problematic.length === 1 ? '' : 's'} with gaps
            </span>
          )}
          {linkedCount > 0 && (
            <span className="expiry-count">
              {linkedCount} linked
            </span>
          )}
        </span>
        <ChevronIcon />
      </button>

      {expanded && (
        <div className="expiry-body">
          {sorted.map((f) => (
            <article
              key={f.chain_id}
              style={{
                padding: '12px 0',
                borderBottom: '1px solid var(--border-subtle)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                {statusBadge(f.status)}
                <span style={{ fontWeight: 600, fontSize: 13.5 }}>{f.title}</span>
                <span
                  style={{
                    marginLeft: 'auto',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--text-tertiary)',
                  }}
                >
                  {f.clause_ids.map(displayClause).join(' → ')}
                </span>
              </div>
              <p style={{ fontSize: 13, lineHeight: 1.6, color: 'var(--text-secondary)', margin: 0 }}>
                {f.narrative}
              </p>
              {f.sources.length > 0 && (
                <div
                  style={{
                    marginTop: 6,
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 10,
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    color: 'var(--text-tertiary)',
                  }}
                >
                  {f.sources.map((s) => (
                    <span key={s.evidence_id}>
                      {lastPathSegment(s.file_name)}
                      {s.pages.length > 0 && ` · p.${s.pages.slice(0, 3).join(', ')}`}
                    </span>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
