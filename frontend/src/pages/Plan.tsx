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
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAddManualNC, useAnalysis, useDismissNC, useRestoreNC, useUpdateAction } from '@/lib/hooks';
import { compliance, triggerBrowserDownload, ApiError } from '@/lib/api';
import type { ActionStatus, ClauseGap, ManualNonconformity } from '@/lib/api';

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
  // Fase 4 — overlay dal registro NC
  ncId?: number;
  dismissed: boolean;
  dismissReason?: string | null;
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
      // Fase 4: preferisci la corrective action (sistemica) quando il deep
      // pass l'ha prodotta; `what` resta il fallback retro-compatibile.
      what: c.remediation.corrective_action || c.remediation.what,
      who: c.remediation.who,
      when: c.remediation.when,
      effort: c.remediation.effort,
    },
    sourceFile,
    status,
    ncId: c.nc_id,
    dismissed: c.dismissed ?? false,
    dismissReason: c.dismiss_reason,
  };
}

function ActionCard({
  a,
  onUpdate,
  onDismiss,
}: {
  a: PlanAction;
  onUpdate: (clauseId: string, status: ActionStatus) => void;
  onDismiss?: (ncId: number, reason: string) => void;
}) {
  const [status, setStatus] = useState<Status>(a.status);
  // Fase 4: lo status ora arriva DAVVERO dal server (merge registro NC) —
  // risincronizza lo stato locale quando il refetch lo aggiorna.
  useEffect(() => setStatus(a.status), [a.status]);

  const [dismissOpen, setDismissOpen] = useState(false);
  const [dismissReason, setDismissReason] = useState('');

  const advance = () => {
    const next = NEXT[status];
    setStatus(next);
    onUpdate(a.clauseId, TO_API[next]);
  };

  const confirmDismiss = () => {
    if (a.ncId != null && dismissReason.trim() && onDismiss) {
      onDismiss(a.ncId, dismissReason.trim());
      setDismissOpen(false);
      setDismissReason('');
    }
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

        {/* Fase 4 (PRD 1.4.8): set aside con motivazione obbligatoria */}
        {onDismiss && a.ncId != null && (
          dismissOpen ? (
            <div style={{ marginTop: 10, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                className="input"
                style={{ flex: 1, minWidth: 220, fontSize: 12.5 }}
                placeholder="Reason for setting this finding aside (required)"
                value={dismissReason}
                onChange={(e) => setDismissReason(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') confirmDismiss(); }}
              />
              <button className="btn btn-secondary" type="button" disabled={!dismissReason.trim()} onClick={confirmDismiss}>
                Set aside
              </button>
              <button className="btn btn-link" type="button" onClick={() => setDismissOpen(false)}>Cancel</button>
            </div>
          ) : (
            <button
              className="btn btn-link"
              type="button"
              style={{ marginTop: 8, fontSize: 12, color: 'var(--text-tertiary)' }}
              onClick={() => setDismissOpen(true)}
              title="Exclude this finding from the plan, keeping it on record with a reason"
            >
              Set aside…
            </button>
          )
        )}
      </div>
      <div className="action-side">
        <span className="effort-pill">{effortLabel(a.remediation.effort)}</span>
      </div>
    </article>
  );
}

/**
 * Sprint G.3: stesso pattern fetch+Blob auth per "Export plan".
 * Per ora il payload è il DOCX completo (riusa /download). Un plan-only DOCX
 * è un futuro backend ticket.
 */
function ExportPlanButton({ analysisId }: { analysisId: string }) {
  const [state, setState] = useState<'idle' | 'downloading' | 'error'>('idle');
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const handleClick = async () => {
    if (state === 'downloading') return;
    setState('downloading');
    setErrMsg(null);
    try {
      const { blob, filename } = await compliance.downloadReport(analysisId);
      triggerBrowserDownload(blob, filename);
      setState('idle');
    } catch (e) {
      const msg = e instanceof ApiError ? `${e.status} ${e.message}` : (e as Error).message;
      setErrMsg(msg);
      setState('error');
      window.setTimeout(() => setState('idle'), 4000);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`btn btn-secondary${state === 'error' ? ' btn-error' : ''}`}
      title={state === 'error' ? errMsg ?? 'Export failed' : 'Export the gap analysis report (DOCX)'}
      disabled={state === 'downloading'}
    >
      <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="7 10 12 15 17 10" />
        <line x1="12" y1="15" x2="12" y2="3" />
      </svg>
      {state === 'downloading' ? 'Exporting…' : state === 'error' ? 'Export failed' : 'Export plan'}
    </button>
  );
}


export function Plan() {
  const { id } = useParams();
  const analysisQuery = useAnalysis(id);
  const updateMut = useUpdateAction(id ?? '');
  const dismissMut = useDismissNC(id ?? '');
  const restoreMut = useRestoreNC(id ?? '');
  const addNCMut = useAddManualNC(id ?? '');

  const handleUpdate = (clauseId: string, status: ActionStatus) => {
    if (!id) return;
    updateMut.mutate({ clauseId, status });
  };
  const handleDismiss = (ncId: number, reason: string) => {
    if (!id) return;
    dismissMut.mutate({ ncId, reason });
  };
  const handleRestore = (ncId: number) => {
    if (!id) return;
    restoreMut.mutate({ ncId });
  };

  const result = analysisQuery.data?.result;
  const manualNCs: ManualNonconformity[] = analysisQuery.data?.manual_nonconformities ?? [];

  const { critical, improvements, setAside, openCount, inProgressCount, closedCount, spofCount, totalActions } = useMemo(() => {
    if (!result) {
      return { critical: [], improvements: [], setAside: [], openCount: 0, inProgressCount: 0, closedCount: 0, spofCount: 0, totalActions: 0 };
    }
    const allClauses = result.norms.flatMap((n) => n.clauses);
    const actionableClauses = allClauses.filter((c) => c.severity === 'MAJOR' || c.severity === 'MINOR');
    const all = actionableClauses.map(clauseToAction);
    // Fase 4: i finding messi da parte escono dal piano operativo
    const actions = all.filter((a) => !a.dismissed);
    return {
      critical: actions.filter((a) => a.severity === 'major'),
      improvements: actions.filter((a) => a.severity === 'minor'),
      setAside: all.filter((a) => a.dismissed),
      openCount: actions.filter((a) => a.status === 'open').length,
      inProgressCount: actions.filter((a) => a.status === 'in-progress').length,
      closedCount: actions.filter((a) => a.status === 'closed').length,
      spofCount: actionableClauses.filter((c) => c.is_spof && c.severity === 'MAJOR' && !(c.dismissed ?? false)).length,
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
          <ExportPlanButton analysisId={id!} />
        </div>
      </header>

      <nav className="tabs">
        <Link className="tab" to={`/analyses/${id}`}>Findings <span className="tab-count">{result.norms.reduce((s, n) => s + n.clauses.length, 0)}</span></Link>
        <a className="tab active" href="#">Plan <span className="tab-count">{openCount} open</span></a>
        <Link className="tab" to={`/analyses/${id}/compare`}>Compare</Link>
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
            {critical.map((a) => <ActionCard key={a.clauseId} a={a} onUpdate={handleUpdate} onDismiss={handleDismiss} />)}
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
            {improvements.map((a) => <ActionCard key={a.clauseId} a={a} onUpdate={handleUpdate} onDismiss={handleDismiss} />)}
          </div>
        </>
      )}

      {totalActions === 0 && (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>
          No actionable findings in this analysis. Documentation is largely conformant.
        </div>
      )}

      {/* Fase 4 — NC manuali (PRD 1.4.8: "manually add-in their own") */}
      <ManualNCSection
        manualNCs={manualNCs}
        onAdd={(title, description, severity) => addNCMut.mutate({ title, description, severity })}
        onDismiss={handleDismiss}
        onRestore={handleRestore}
        adding={addNCMut.isPending}
      />

      {/* Fase 4 — Set aside (dismissed): mai cancellati, sempre ripristinabili */}
      {setAside.length > 0 && (
        <>
          <div className="section-break">
            <span className="section-title-text">
              Set aside
              <span className="count">{setAside.length} excluded from the plan</span>
            </span>
          </div>
          <div className="actions-list">
            {setAside.map((a) => (
              <article key={a.clauseId} className="action-card closed">
                <div className="action-body">
                  <div className="action-head">
                    <span className={`badge badge-${a.severity}`}>{a.severity === 'major' ? 'Major' : 'Minor'}</span>
                    <span className="action-clause-id">{a.displayClauseId}</span>
                  </div>
                  <h2 className="action-title" style={{ textDecoration: 'line-through', opacity: 0.7 }}>{a.title}</h2>
                  {a.dismissReason && (
                    <p className="action-desc" style={{ fontStyle: 'italic' }}>
                      Reason: {a.dismissReason}
                    </p>
                  )}
                  {a.ncId != null && (
                    <button className="btn btn-link" type="button" style={{ fontSize: 12 }} onClick={() => handleRestore(a.ncId!)}>
                      Restore to plan
                    </button>
                  )}
                </div>
              </article>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/**
 * Fase 4 — sezione NC manuali: form essenziale + lista. DESIGN.md-compliant:
 * niente card-grid, severity colors solo semantici, tono advisory.
 */
function ManualNCSection({
  manualNCs,
  onAdd,
  onDismiss,
  onRestore,
  adding,
}: {
  manualNCs: ManualNonconformity[];
  onAdd: (title: string, description: string, severity: string) => void;
  onDismiss: (ncId: number, reason: string) => void;
  onRestore: (ncId: number) => void;
  adding: boolean;
}) {
  const [formOpen, setFormOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [severity, setSeverity] = useState('MINOR');
  const [dismissFor, setDismissFor] = useState<number | null>(null);
  const [reason, setReason] = useState('');

  const submit = () => {
    if (!title.trim()) return;
    onAdd(title.trim(), description.trim(), severity);
    setTitle(''); setDescription(''); setSeverity('MINOR'); setFormOpen(false);
  };

  return (
    <>
      <div className="section-break">
        <span className="section-title-text">
          Recorded by you
          <span className="count">{manualNCs.length} manual finding{manualNCs.length === 1 ? '' : 's'}</span>
        </span>
      </div>

      {manualNCs.length > 0 && (
        <div className="actions-list">
          {manualNCs.map((nc) => (
            <article key={nc.id} className={`action-card${nc.dismissed ? ' closed' : ''}`}>
              <div className="action-body">
                <div className="action-head">
                  <span className={`badge badge-${nc.severity.toLowerCase() === 'observation' ? 'obs' : nc.severity.toLowerCase()}`}>
                    {nc.severity.charAt(0) + nc.severity.slice(1).toLowerCase()}
                  </span>
                  <span className="action-clause-id">manual</span>
                </div>
                <h2 className="action-title" style={nc.dismissed ? { textDecoration: 'line-through', opacity: 0.7 } : undefined}>
                  {nc.title}
                </h2>
                {nc.description && <p className="action-desc">{nc.description}</p>}
                {nc.dismissed ? (
                  <>
                    {nc.dismiss_reason && (
                      <p className="action-desc" style={{ fontStyle: 'italic' }}>Reason: {nc.dismiss_reason}</p>
                    )}
                    <button className="btn btn-link" type="button" style={{ fontSize: 12 }} onClick={() => onRestore(nc.id)}>
                      Restore
                    </button>
                  </>
                ) : dismissFor === nc.id ? (
                  <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <input
                      className="input"
                      style={{ flex: 1, minWidth: 200, fontSize: 12.5 }}
                      placeholder="Reason (required)"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                    <button className="btn btn-secondary" type="button" disabled={!reason.trim()}
                      onClick={() => { onDismiss(nc.id, reason.trim()); setDismissFor(null); setReason(''); }}>
                      Set aside
                    </button>
                    <button className="btn btn-link" type="button" onClick={() => setDismissFor(null)}>Cancel</button>
                  </div>
                ) : (
                  <button className="btn btn-link" type="button" style={{ fontSize: 12, color: 'var(--text-tertiary)' }}
                    onClick={() => setDismissFor(nc.id)}>
                    Set aside…
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      {formOpen ? (
        <div style={{
          marginTop: 12, padding: '16px 18px', background: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)', borderRadius: 10,
          display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <input
              className="input" style={{ flex: 2, minWidth: 240 }}
              placeholder="What did you find? (e.g. Forklift daily check not recorded)"
              value={title} onChange={(e) => setTitle(e.target.value)}
            />
            <select className="select" style={{ width: 150 }} value={severity} onChange={(e) => setSeverity(e.target.value)}>
              <option value="MAJOR">Major</option>
              <option value="MINOR">Minor</option>
              <option value="OBSERVATION">Observation</option>
            </select>
          </div>
          <input
            className="input"
            placeholder="Details (optional)"
            value={description} onChange={(e) => setDescription(e.target.value)}
          />
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-accent" type="button" disabled={!title.trim() || adding} onClick={submit}>
              {adding ? 'Recording…' : 'Record finding'}
            </button>
            <button className="btn btn-link" type="button" onClick={() => setFormOpen(false)}>Cancel</button>
          </div>
        </div>
      ) : (
        <button className="btn btn-secondary" type="button" style={{ marginTop: 12 }} onClick={() => setFormOpen(true)}>
          Record a finding of your own
        </button>
      )}
    </>
  );
}
