/**
 * NCR Plan view — actionable remediation list for a single analysis.
 *
 * Builds the action cards directly from the analysis result's clause gaps
 * (MAJOR + MINOR), preserving severity, clause id, finding, source file,
 * and remediation template fields. Status transitions persist through
 * useUpdateAction (PATCH /api/compliance/analyses/:id/actions/:clauseId).
 *
 * Sprint F4: no more hard-coded "Acme Manufacturing", "Q2 2026 review",
 * "9 open · 2 in progress · 5 closed" — all derived from the real result.
 */
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAnalysis, useUpdateAction } from '@/lib/hooks';
import type { ActionStatus, ClauseGap } from '@/lib/api';

type Status = 'open' | 'in-progress' | 'closed';
const NEXT: Record<Status, Status> = { open: 'in-progress', 'in-progress': 'closed', closed: 'open' };
const LABEL: Record<Status, string> = { open: 'Open', 'in-progress': 'In progress', closed: 'Closed' };
const TO_API: Record<Status, ActionStatus> = { open: 'open', 'in-progress': 'in_progress', closed: 'closed' };
const FROM_API: Record<ActionStatus, Status> = { open: 'open', in_progress: 'in-progress', closed: 'closed' };

interface PlanAction {
  clauseId: string;         // backend canonical id, e.g. "9001_8_4"
  displayClauseId: string;  // human, e.g. "9001 §8.4"
  severity: 'major' | 'minor';
  title: string;
  desc: string;
  remediation: { what: string; who: string; when: string; effort: 'LOW' | 'MEDIUM' | 'HIGH' };
  sourceFile?: string;
  status: Status;
}

function effortLabel(effort: 'LOW' | 'MEDIUM' | 'HIGH'): string {
  if (effort === 'HIGH') return 'High effort';
  if (effort === 'MEDIUM') return 'Medium effort';
  return 'Low effort';
}

function displayClause(id: string): string {
  // Match "9001_7_5" -> "9001 §7.5", "14001_6_1_2" -> "14001 §6.1.2"
  const m = id.match(/^(\d+)_(\d+)(?:_(\d+))?(?:_(\d+))?$/);
  if (!m) return id;
  const [, std, a, b, c] = m;
  const parts = [a, b, c].filter(Boolean).join('.');
  return `${std} §${parts}`;
}

function clauseToAction(c: ClauseGap): PlanAction {
  const severity: 'major' | 'minor' = c.severity === 'MAJOR' ? 'major' : 'minor';
  const sourceFile = c.sources[0]?.file_name;
  const status: Status = c.status ? FROM_API[c.status] : 'open';
  return {
    clauseId: c.clause_id,
    displayClauseId: displayClause(c.clause_id),
    severity,
    title: c.clause_title,
    desc: c.finding,
    remediation: {
      what: c.remediation.what,
      who: c.remediation.who,
      when: c.remediation.when,
      effort: c.remediation.effort,
    },
    sourceFile,
    status,
  };
}

function ActionCard({ a, onUpdate }: { a: PlanAction; onUpdate: (clauseId: string, status: ActionStatus) => void }) {
  const [status, setStatus] = useState<Status>(a.status);
  const advance = () => {
    const next = NEXT[status];
    setStatus(next);
    onUpdate(a.clauseId, TO_API[next]);
  };

  return (
    <article className={`action-card${status === 'closed' ? ' closed' : ''}`}>
      <button className={`status-pill ${status}`} onClick={advance} type="button">{LABEL[status]}</button>
      <div className="action-body">
        <div className="action-head">
          <span className={`badge badge-${a.severity}`}>{a.severity === 'major' ? 'Major' : 'Minor'}</span>
          <span className="action-clause-id">{a.displayClauseId}</span>
        </div>
        <h2 className="action-title">{a.title}</h2>
        <p className="action-desc">{a.desc}</p>

        <div className="action-meta-row">
          <span>
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></svg>
            <b>{a.remediation.who}</b>
          </span>
          <span>
            <span className="meta-sep" style={{ marginRight: 8 }}>·</span>
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" /></svg>
            Due in <b>{a.remediation.when}</b>
          </span>
          {a.sourceFile && (
            <span>
              <span className="meta-sep" style={{ marginRight: 8 }}>·</span>
              <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></svg>
              {a.sourceFile.split(/[/\\]/).pop()}
            </span>
          )}
        </div>

        <p className="action-remediation"><b>Action:</b> {a.remediation.what}</p>
      </div>
      <div className="action-side">
        <span className="effort-pill">{effortLabel(a.remediation.effort)}</span>
      </div>
    </article>
  );
}

export function Plan() {
  const { id } = useParams();
  const analysisQuery = useAnalysis(id);
  const updateMut = useUpdateAction(id ?? '');

  const handleUpdate = (clauseId: string, status: ActionStatus) => {
    if (!id) return;
    updateMut.mutate({ clauseId, status });
  };

  const result = analysisQuery.data?.result;

  const { critical, improvements, openCount, inProgressCount, closedCount, spofCount, totalActions } = useMemo(() => {
    if (!result) {
      return { critical: [], improvements: [], openCount: 0, inProgressCount: 0, closedCount: 0, spofCount: 0, totalActions: 0 };
    }
    const allClauses = result.norms.flatMap((n) => n.clauses);
    const actionableClauses = allClauses.filter((c) => c.severity === 'MAJOR' || c.severity === 'MINOR');
    const actions = actionableClauses.map(clauseToAction);
    return {
      critical: actions.filter((a) => a.severity === 'major'),
      improvements: actions.filter((a) => a.severity === 'minor'),
      openCount: actions.filter((a) => a.status === 'open').length,
      inProgressCount: actions.filter((a) => a.status === 'in-progress').length,
      closedCount: actions.filter((a) => a.status === 'closed').length,
      spofCount: actionableClauses.filter((c) => c.is_spof && c.severity === 'MAJOR').length,
      totalActions: actions.length,
    };
  }, [result]);

  if (analysisQuery.isLoading) {
    return (
      <div className="main-inner">
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>
          Loading plan…
        </div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="main-inner">
        <header className="compact-header">
          <div>
            <div className="eyebrow"><Link to="/dashboard">Analyses</Link></div>
            <h1 className="page-title">No plan to display</h1>
            <div className="page-meta">Start an analysis to generate a remediation plan.</div>
          </div>
          <div className="header-right">
            <Link to="/new-analysis" className="btn btn-accent">Start a new analysis</Link>
          </div>
        </header>
      </div>
    );
  }

  const closedPct = totalActions > 0 ? Math.round((closedCount / totalActions) * 100) : 0;
  const company = result.company;
  const analysisDate = new Date(result.analysis_date).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });

  return (
    <div className="main-inner">
      <header className="compact-header">
        <div>
          <div className="eyebrow">
            <Link to="/dashboard">Analyses</Link>
            <span className="sep">/</span>
            <Link to={`/analyses/${id}`}>{company}</Link>
          </div>
          <h1 className="page-title">Plan</h1>
          <div className="page-meta">
            {company}
            <span className="sep">·</span>
            {openCount} open · {inProgressCount} in progress · {closedCount} closed
            <span className="sep">·</span>
            analysed {analysisDate}
          </div>
        </div>
        <div className="header-right">
          <a
            href={`${import.meta.env.VITE_API_BASE_URL ?? ''}/api/compliance/analyses/${id}/download`}
            className="btn btn-secondary"
            target="_blank"
            rel="noopener noreferrer"
          >
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>
            Export plan
          </a>
        </div>
      </header>

      <nav className="tabs">
        <Link className="tab" to={`/analyses/${id}`}>Findings <span className="tab-count">{result.norms.reduce((s, n) => s + n.clauses.length, 0)}</span></Link>
        <a className="tab active" href="#">Plan <span className="tab-count">{openCount} open</span></a>
        <span className="tab tab-disabled" title="Available once a second analysis exists">Compare</span>
      </nav>

      <div className="plan-overview">
        <div className="plan-pct">{closedPct}<span className="pct">%</span></div>
        <div className="plan-progress">
          <div className="plan-progress-label"><b>{closedCount} of {totalActions}</b> action{totalActions === 1 ? '' : 's'} closed since the assessment</div>
          <div className="plan-progress-bar"><div className="plan-progress-bar-fill" style={{ width: `${closedPct}%` }} /></div>
        </div>
        <div className="plan-counts">
          <div className="plan-count-item"><span className="plan-count-num">{openCount}</span><span className="plan-count-label">OPEN</span></div>
          <div className="plan-count-item"><span className="plan-count-num">{inProgressCount}</span><span className="plan-count-label">IN PROGRESS</span></div>
          <div className="plan-count-item"><span className="plan-count-num">{closedCount}</span><span className="plan-count-label">CLOSED</span></div>
        </div>
      </div>

      {critical.length > 0 && (
        <>
          <div className="section-break">
            <span className="section-title-text">
              Critical actions
              <span className="count">
                {critical.length} major{critical.length === 1 ? '' : 's'}
                {spofCount > 0 && `, ${spofCount} SPoF`}
              </span>
            </span>
          </div>
          <div className="actions-list">
            {critical.map((a) => <ActionCard key={a.clauseId} a={a} onUpdate={handleUpdate} />)}
          </div>
        </>
      )}

      {improvements.length > 0 && (
        <>
          <div className="section-break">
            <span className="section-title-text">
              Improvement actions
              <span className="count">{improvements.length} minor{improvements.length === 1 ? '' : 's'}</span>
            </span>
          </div>
          <div className="actions-list">
            {improvements.map((a) => <ActionCard key={a.clauseId} a={a} onUpdate={handleUpdate} />)}
          </div>
        </>
      )}

      {totalActions === 0 && (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>
          No actionable findings in this analysis. Documentation is largely conformant.
        </div>
      )}
    </div>
  );
}
