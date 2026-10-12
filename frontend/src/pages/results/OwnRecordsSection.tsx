/**
 * Own records check — engine plan phases 4-5.
 *
 * What the organisation's own registers, procedures and minutes state,
 * checked against the records in the pack (register vs certificate, training
 * matrix vs attendance sheets, "minutes are kept" vs minutes present), plus
 * activity-based expectations. Inconsistencies and missing records are
 * evidence-based; "To verify" points could not be confirmed either way.
 */
import { useState } from 'react';
import type { SelfCheck } from '@/lib/api';

interface Props {
  checks: SelfCheck[];
}

function ChevronIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function lastPathSegment(path: string): string {
  const normalised = (path || '').replace(/\\/g, '/');
  const idx = normalised.lastIndexOf('/');
  return idx >= 0 ? normalised.slice(idx + 1) : normalised;
}

const ORDER: Record<string, number> = { INCONSISTENT: 0, MISSING: 1, TO_VERIFY: 2 };

function statusBadge(status: SelfCheck['status']) {
  // Severity-semantic colours only for evidence-based outcomes; "To verify" is neutral.
  if (status === 'INCONSISTENT') return <span className="badge badge-minor">Inconsistent</span>;
  if (status === 'MISSING') return <span className="badge badge-minor">Missing record</span>;
  return <span className="badge badge-neutral">To verify</span>;
}

function displayClause(attached?: string | null): string {
  const id = (attached || '').split(' ').pop() || '';
  const m = id.match(/^(\d+)_(\d+)(?:_(\d+))?(?:_(\d+))?$/);
  if (!m) return id;
  const [, std, a, b, c] = m;
  return `${std} §${[a, b, c].filter(Boolean).join('.')}`;
}

export function OwnRecordsSection({ checks }: Props) {
  const shown = checks.filter((c) => c.status in ORDER);
  const evidenced = shown.filter((c) => c.status !== 'TO_VERIFY').length;
  const [expanded, setExpanded] = useState(evidenced > 0);
  if (shown.length === 0) return null;
  const sorted = [...shown].sort((a, b) => ORDER[a.status] - ORDER[b.status]);

  return (
    <section className={`expiry-section${expanded ? ' expanded' : ''}`}>
      <button type="button" className="expiry-head" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>
        <span className="expiry-head-title">Own records check</span>
        <span className="expiry-head-counts">
          {evidenced > 0 && (
            <span className="expiry-count expiry-count-expired">
              {evidenced} inconsistenc{evidenced === 1 ? 'y' : 'ies'} or missing record{evidenced === 1 ? '' : 's'}
            </span>
          )}
          {shown.length - evidenced > 0 && <span className="expiry-count">{shown.length - evidenced} to verify</span>}
        </span>
        <ChevronIcon />
      </button>

      {expanded && (
        <div className="expiry-body">
          <p style={{ fontSize: 12.5, color: 'var(--text-secondary)', margin: '4px 0 8px' }}>
            What your own registers, procedures and minutes state, checked against the records in the pack.
          </p>
          {sorted.map((c, i) => (
            <article key={`${c.kind}-${i}`} style={{ padding: '10px 0', borderBottom: '1px solid var(--border-subtle)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                {statusBadge(c.status)}
                <span style={{ fontSize: 13.5 }}>{c.description}</span>
                {c.attached_to && (
                  <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-tertiary)' }}>
                    {displayClause(c.attached_to)}
                  </span>
                )}
              </div>
              {c.cites.length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 12, color: 'var(--text-secondary)' }}>
                  {c.cites.map((x, j) => (
                    <span key={j}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-tertiary)' }}>
                        {lastPathSegment(x.file_name || '')}
                      </span>
                      {x.quote ? ` — “${x.quote}”` : ''}
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
