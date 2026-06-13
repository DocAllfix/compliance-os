/**
 * Compare — Fase 5 (PRODUCT.md aha moment #3, PRD §2.7 uso ricorrente).
 *
 * Confronta l'analisi corrente con una run precedente: "47% → 64%, two
 * Majors closed, one new Minor". Vista essenziale e sobria (DESIGN.md):
 * overall per norma, contatori, lista clausole regressed→new→improved,
 * unchanged collassati. Il restyling arriverà con la brand identity.
 */
import { useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useAnalyses, useAnalysis, useDelta } from '@/lib/hooks';
import type { ClauseDelta, Severity } from '@/lib/api';

function displayClause(id: string): string {
  const m = id.match(/^(\d+)_(\d+)(?:_(\d+))?(?:_(\d+))?$/);
  if (!m) return id;
  const [, std, a, b, c] = m;
  return `${std} §${[a, b, c].filter(Boolean).join('.')}`;
}

function sevBadge(sev: Severity | null) {
  if (!sev) return <span style={{ color: 'var(--text-tertiary)' }}>—</span>;
  const cls =
    sev === 'MAJOR' ? 'badge-major'
    : sev === 'MINOR' ? 'badge-minor'
    : sev === 'CONFORMANT' ? 'badge-conf'
    : 'badge-obs';
  return <span className={`badge ${cls}`}>{sev.charAt(0) + sev.slice(1).toLowerCase()}</span>;
}

function DirectionLabel({ d }: { d: ClauseDelta['direction'] }) {
  const map: Record<ClauseDelta['direction'], { label: string; color: string }> = {
    improved:  { label: 'Improved',  color: 'var(--severity-conformant-fg, #16a34a)' },
    regressed: { label: 'Regressed', color: 'var(--severity-major-fg, #dc2626)' },
    unchanged: { label: 'Unchanged', color: 'var(--text-tertiary)' },
    new:       { label: 'New',       color: 'var(--text-secondary)' },
    removed:   { label: 'Removed',   color: 'var(--text-tertiary)' },
  };
  const v = map[d];
  return <span style={{ color: v.color, fontWeight: 600, fontSize: 12 }}>{v.label}</span>;
}

const ORDER: Record<ClauseDelta['direction'], number> = {
  regressed: 0, new: 1, improved: 2, removed: 3, unchanged: 4,
};

export function Compare() {
  const { id } = useParams();
  const analysisQuery = useAnalysis(id);
  const analysesQuery = useAnalyses();
  // Fase A: il Re-analyse arriva qui con ?against=<analisi di partenza>
  const [searchParams] = useSearchParams();
  const [against, setAgainst] = useState<string>(searchParams.get('against') ?? '');
  const [showUnchanged, setShowUnchanged] = useState(false);

  const company = analysisQuery.data?.result?.company;

  // Candidate runs: tutte le altre analisi, prima quelle della stessa azienda,
  // ordinate dalla più recente.
  const candidates = useMemo(() => {
    const all = (analysesQuery.data ?? []).filter((a) => a.id !== id);
    return [...all].sort((a, b) => {
      const sameA = a.company === company ? 0 : 1;
      const sameB = b.company === company ? 0 : 1;
      if (sameA !== sameB) return sameA - sameB;
      return new Date(b.analysis_date).getTime() - new Date(a.analysis_date).getTime();
    });
  }, [analysesQuery.data, id, company]);

  const deltaQuery = useDelta(id, against || undefined);
  const delta = deltaQuery.data;

  const sortedClauses = useMemo(() => {
    if (!delta) return [];
    return [...delta.clauses].sort(
      (a, b) => ORDER[a.direction] - ORDER[b.direction] || a.clause_id.localeCompare(b.clause_id),
    );
  }, [delta]);

  const visible = sortedClauses.filter((c) => showUnchanged || c.direction !== 'unchanged');

  const fmtDate = (iso: string) =>
    iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';

  return (
    <div className="main-inner">
      <header className="compact-header">
        <div>
          <div className="eyebrow">
            <Link to="/dashboard">Analyses</Link>
            <span className="sep">/</span>
            <Link to={`/analyses/${id}`}>{company ?? id}</Link>
          </div>
          <h1 className="page-title">Compare</h1>
          <div className="page-meta">
            How this assessment moved against a previous run.
          </div>
        </div>
      </header>

      <nav className="tabs">
        <Link className="tab" to={`/analyses/${id}`}>Findings</Link>
        <Link className="tab" to={`/analyses/${id}/plan`}>Plan</Link>
        <a className="tab active" href="#">Compare</a>
      </nav>

      <div style={{ margin: '18px 0', display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <label className="field-label" style={{ margin: 0 }}>Compare against</label>
        <select
          className="select"
          style={{ minWidth: 320 }}
          value={against}
          onChange={(e) => setAgainst(e.target.value)}
        >
          <option value="">Select a previous analysis…</option>
          {candidates.map((a) => (
            <option key={a.id} value={a.id}>
              {a.company} — {fmtDate(a.analysis_date)} ({a.overall_score ?? '—'}%)
            </option>
          ))}
        </select>
      </div>

      {!against && (
        <div style={{ padding: 36, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>
          {candidates.length === 0
            ? 'No other analyses to compare against yet. Re-run the assessment to track progress.'
            : 'Pick a previous run to see what improved and what regressed.'}
        </div>
      )}

      {against && deltaQuery.isLoading && (
        <div style={{ padding: 36, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>Comparing…</div>
      )}

      {against && deltaQuery.isError && (
        <div style={{ padding: 16, fontSize: 13, color: 'var(--severity-major-fg)' }}>
          The comparison could not be loaded.
        </div>
      )}

      {delta && (
        <>
          {/* Overall per norma */}
          <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap', margin: '10px 0 22px' }}>
            {delta.norms.map((n) => (
              <div key={n.norm}>
                <div style={{ fontSize: 11.5, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                  {n.norm.replace(/:\d{4}$/, '')}
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 26, fontWeight: 600 }}>
                  {n.overall_old ?? '—'}%
                  <span style={{ color: 'var(--text-tertiary)', margin: '0 8px' }}>→</span>
                  {n.overall_new ?? '—'}%
                  {n.overall_delta != null && n.overall_delta !== 0 && (
                    <span style={{
                      fontSize: 14, marginLeft: 10,
                      color: n.overall_delta > 0 ? 'var(--severity-conformant-fg, #16a34a)' : 'var(--severity-major-fg, #dc2626)',
                    }}>
                      {n.overall_delta > 0 ? '+' : ''}{n.overall_delta} pts
                    </span>
                  )}
                </div>
              </div>
            ))}
            <div style={{ marginLeft: 'auto', alignSelf: 'center', fontSize: 12.5, color: 'var(--text-secondary)' }}>
              {delta.summary.improved} improved · {delta.summary.regressed} regressed · {delta.summary.new} new
              {delta.summary.removed > 0 && <> · {delta.summary.removed} removed</>}
            </div>
          </div>

          {/* Documented-info delta */}
          {delta.documented_info && (delta.documented_info.resolved.length > 0 || delta.documented_info.newly_missing.length > 0) && (
            <div style={{ marginBottom: 20, fontSize: 13, lineHeight: 1.7 }}>
              {delta.documented_info.resolved.length > 0 && (
                <div>
                  <b>Now present:</b>{' '}
                  <span style={{ color: 'var(--text-secondary)' }}>{delta.documented_info.resolved.join('; ')}</span>
                </div>
              )}
              {delta.documented_info.newly_missing.length > 0 && (
                <div>
                  <b style={{ color: 'var(--severity-major-fg)' }}>Newly missing:</b>{' '}
                  <span style={{ color: 'var(--text-secondary)' }}>{delta.documented_info.newly_missing.join('; ')}</span>
                </div>
              )}
            </div>
          )}

          {/* Tabella clausole */}
          <div className="expiry-table-wrap">
            <table className="expiry-table">
              <thead>
                <tr>
                  <th>Clause</th>
                  <th>Then</th>
                  <th>Now</th>
                  <th>Score</th>
                  <th>Movement</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((c) => (
                  <tr key={c.clause_id}>
                    <td>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--text-tertiary)', marginRight: 8 }}>
                        {displayClause(c.clause_id)}
                      </span>
                      {c.clause_title}
                    </td>
                    <td>{sevBadge(c.severity_old)}</td>
                    <td>{sevBadge(c.severity_new)}</td>
                    <td className="expiry-days">
                      {c.score_old ?? '—'} → {c.score_new ?? '—'}
                      {c.delta != null && c.delta !== 0 && (
                        <span style={{ marginLeft: 6, color: c.delta > 0 ? 'var(--severity-conformant-fg)' : 'var(--severity-major-fg)' }}>
                          ({c.delta > 0 ? '+' : ''}{c.delta})
                        </span>
                      )}
                    </td>
                    <td><DirectionLabel d={c.direction} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {delta.summary.unchanged > 0 && (
            <button
              className="btn btn-link"
              type="button"
              style={{ marginTop: 10, fontSize: 12.5 }}
              onClick={() => setShowUnchanged(!showUnchanged)}
            >
              {showUnchanged
                ? 'Hide unchanged clauses'
                : `Show ${delta.summary.unchanged} unchanged clause${delta.summary.unchanged === 1 ? '' : 's'}`}
            </button>
          )}
        </>
      )}
    </div>
  );
}
