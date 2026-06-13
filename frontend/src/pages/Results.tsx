import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useAnalysis } from '@/lib/hooks';
import { compliance, runReanalyse, triggerBrowserDownload, ApiError } from '@/lib/api';
import type { ClauseGap, RemediationPlan, RequirementCheck, SseEvent, TraceabilityLink } from '@/lib/api';
import { useChatDrawer } from '@/lib/useChatStore';
import { CompanySnapshotCard } from '@/pages/results/CompanySnapshotCard';
import { ExecutiveNarrative } from '@/pages/results/ExecutiveNarrative';
import { ExpiryTable } from '@/pages/results/ExpiryTable';
import { PriorityIntegrationsList } from '@/pages/results/PriorityIntegrationsList';
import { DocumentedInfoSection } from '@/pages/results/DocumentedInfoSection';
import { CrossClauseSection } from '@/pages/results/CrossClauseSection';
import { RiskRegisterSection } from '@/pages/results/RiskRegisterSection';

// Sprint G.1: Finding interface estesa con i dati REALI di ClauseGap
// (excerpt, pages, remediation). Niente più stub statico nell'expand.
// Sprint R6: requirement checks, confidence, hedging, dual remediation.
interface Finding {
  clauseId: string;        // human-readable, es. "45001 §10.2"
  title: string;
  severity: 'major' | 'minor' | 'obs' | 'conf';
  isSpof?: boolean;
  text: string;            // il "finding" del ClauseGap (max ~150 parole)
  sources: TraceabilityLink[];  // tutte le sources, non solo la prima
  remediation: RemediationPlan;
  confidence?: number | null;
  requirementChecks: RequirementCheck[];
  hedged: boolean;
  hedgeNote?: string | null;
  deepVerified: boolean;
}

function mapClause(c: ClauseGap): Finding {
  const sev: Finding['severity'] =
    c.severity === 'MAJOR' ? 'major'
    : c.severity === 'MINOR' ? 'minor'
    : c.severity === 'CONFORMANT' ? 'conf'
    : 'obs';
  return {
    // Sprint R6: handle 2-4 segment ids ("14001_6_1_2" → "14001 §6.1.2")
    clauseId: c.clause_id.replace(/^(\d+)_(\d+)(?:_(\d+))?(?:_(\d+))?$/i, (_m, std, a, b, cc) =>
      `${std} §${[a, b, cc].filter(Boolean).join('.')}`,
    ),
    title: c.clause_title,
    severity: sev,
    isSpof: c.is_spof,
    text: c.finding,
    sources: c.sources ?? [],
    remediation: c.remediation,
    confidence: c.confidence,
    requirementChecks: c.requirement_checks ?? [],
    hedged: c.hedged ?? false,
    hedgeNote: c.hedge_note,
    deepVerified: c.deep_verified ?? false,
  };
}

function MajorIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" />
      <path d="M12 9v4" /><path d="M12 17h.01" />
    </svg>
  );
}

function FileIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

// Sprint G.1: helper UI per le sources (filename + opzionale "p.N, N")
function lastPathSegment(path: string): string {
  if (!path) return '';
  const normalised = path.replace(/\\/g, '/');
  const i = normalised.lastIndexOf('/');
  return i >= 0 ? normalised.slice(i + 1) : normalised;
}

function pagesLabel(pages: number[] | undefined): string {
  if (!pages || pages.length === 0) return '';
  if (pages.length === 1) return `p. ${pages[0]}`;
  return `p. ${pages.slice(0, 3).join(', ')}${pages.length > 3 ? '…' : ''}`;
}

function effortLabel(effort: RemediationPlan['effort']): string {
  if (effort === 'HIGH') return 'High';
  if (effort === 'MEDIUM') return 'Medium';
  return 'Low';
}

function checkStatusBadge(status: RequirementCheck['status']) {
  // Severity-semantic colours only: PRESENT=conformant, PARTIAL=minor, ABSENT=major
  if (status === 'PRESENT') return <span className="badge badge-conf">Present</span>;
  if (status === 'PARTIAL') return <span className="badge badge-minor">Partial</span>;
  return <span className="badge badge-major">Absent</span>;
}

function requirementLabel(id: string): string {
  // "9001_9_3.inputs.complete" → "inputs complete"
  const tail = id.split('.').slice(1).join(' · ');
  return tail.replace(/_/g, ' ') || id;
}

function FindingCard({ f, defaultExpanded = false }: { f: Finding; defaultExpanded?: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const firstSource = f.sources[0];
  const headerPage = pagesLabel(firstSource?.pages);
  return (
    <article className={`finding${expanded ? ' expanded' : ''}`}>
      <div className="finding-head">
        {f.severity === 'major' && (
          <span className="badge badge-major"><MajorIcon />Major</span>
        )}
        {f.severity === 'minor' && <span className="badge badge-minor">Minor</span>}
        {f.severity === 'obs' && <span className="badge badge-obs">Obs.</span>}
        {f.severity === 'conf' && <span className="badge badge-conf">Conformant</span>}
        {f.isSpof && (
          <span className="spof-badge">
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <circle cx="12" cy="12" r="9" /><path d="M12 7v5" /><path d="M12 16h.01" />
            </svg>
            Single point of failure
          </span>
        )}
        <span className="finding-clause-id" style={{ marginLeft: 'auto' }}>{f.clauseId}</span>
        {f.confidence != null && (
          <span
            title={f.deepVerified
              ? 'Verdict confidence — this clause was verified against the full document text'
              : 'Verdict confidence from the screening pass'}
            style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-tertiary)' }}
          >
            {f.deepVerified ? '✓ ' : ''}conf. {Math.round(f.confidence * 100)}%
          </span>
        )}
      </div>
      <h2 className="finding-title">{f.title}</h2>
      <p className="finding-text">{f.text}</p>
      {f.hedged && f.hedgeNote && (
        <p style={{ fontSize: 12.5, fontStyle: 'italic', color: 'var(--text-tertiary)', margin: '4px 0 0' }}>
          Note of caution: {f.hedgeNote}
        </p>
      )}
      {firstSource && (
        <span className="finding-source">
          <FileIcon />
          {lastPathSegment(firstSource.file_name)}
          {headerPage && <span className="page"> · {headerPage}</span>}
        </span>
      )}
      <button className="finding-toggle" onClick={() => setExpanded(!expanded)}>
        <span className="label-collapsed">Show evidence and remediation</span>
        <span className="label-expanded">Hide evidence and remediation</span>
        <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9" /></svg>
      </button>
      {expanded && (
        <div className="finding-detail">
          {/* Sprint R6: per-requirement verification checklist from the deep
              pass — PRESENT/PARTIAL/ABSENT with verbatim quote and page. */}
          {f.requirementChecks.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div className="remediation-header" style={{ marginBottom: 8 }}>
                <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
                </svg>
                Requirement verification
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {f.requirementChecks.map((chk) => (
                  <div
                    key={chk.requirement_id}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '90px 1fr',
                      gap: 10,
                      alignItems: 'start',
                      fontSize: 12.5,
                    }}
                  >
                    <div>{checkStatusBadge(chk.status)}</div>
                    <div>
                      <span style={{ fontWeight: 600 }}>{requirementLabel(chk.requirement_id)}</span>
                      {chk.note && (
                        <span style={{ color: 'var(--text-secondary)' }}> — {chk.note}</span>
                      )}
                      {chk.evidence_quote && (
                        <div
                          style={{
                            marginTop: 3,
                            fontFamily: 'var(--font-serif)',
                            fontStyle: 'italic',
                            color: 'var(--text-secondary)',
                          }}
                        >
                          “{chk.evidence_quote}”
                          {chk.file_name && (
                            <span style={{ fontFamily: 'var(--font-mono)', fontStyle: 'normal', fontSize: 11, color: 'var(--text-tertiary)' }}>
                              {' '}[{lastPathSegment(chk.file_name)}{chk.pages.length > 0 ? `, p.${chk.pages.join(', ')}` : ''}]
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Sprint G.1: excerpts REALI dalle sources del backend.
              Nessuna stub italiana hard-coded. Se non ci sono sources, la
              sezione excerpt viene omessa e mostriamo solo la remediation. */}
          {f.sources.length > 0 ? (
            <div className="evidence-stack">
              {f.sources.slice(0, 3).map((src, i) => {
                const pageLbl = pagesLabel(src.pages);
                const excerpt = (src.excerpt || '').trim();
                const summary = (src.summary || '').trim();
                // Hide summary if it's just a duplicate of the excerpt
                const showSummary = summary && summary !== excerpt;
                return (
                  <div key={src.evidence_id || i} className="pdf-excerpt">
                    <span className="pdf-excerpt-meta">
                      <FileIcon />
                      {lastPathSegment(src.file_name)}
                      {pageLbl && <span className="page"> · {pageLbl}</span>}
                    </span>
                    {excerpt ? (
                      <div className="pdf-excerpt-body">
                        <h4>Excerpt</h4>
                        <p>{excerpt}</p>
                      </div>
                    ) : (
                      <div className="pdf-excerpt-empty">
                        No verbatim excerpt was indexed for this evidence card.
                      </div>
                    )}
                    {showSummary && (
                      <div className="pdf-excerpt-summary">
                        <span className="pdf-excerpt-summary-label">Summary</span>
                        <p>{summary}</p>
                      </div>
                    )}
                  </div>
                );
              })}
              {f.sources.length > 3 && (
                <div className="evidence-more">
                  + {f.sources.length - 3} more source{f.sources.length - 3 === 1 ? '' : 's'} cited in the full report.
                </div>
              )}
            </div>
          ) : (
            <div className="evidence-none">
              No evidence was cited for this clause — the verdict was reached because no
              pertinent documentation was retrieved from the package.
            </div>
          )}

          <div className="remediation">
            <div className="remediation-header">
              <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="20 6 9 17 4 12" /></svg>
              Remediation plan
            </div>
            <div className="rem-grid">
              {/* Sprint R6 (PRD 1.4.7): correction = immediate fix,
                  corrective action = systemic fix. Falls back to the single
                  "Action" row for analyses that predate the deep pass. */}
              {f.remediation.correction || f.remediation.corrective_action ? (
                <>
                  {f.remediation.correction && (
                    <>
                      <div className="rem-label">Correction</div>
                      <div className="rem-value">{f.remediation.correction}</div>
                    </>
                  )}
                  {f.remediation.corrective_action && (
                    <>
                      <div className="rem-label">Corrective action</div>
                      <div className="rem-value">{f.remediation.corrective_action}</div>
                    </>
                  )}
                </>
              ) : (
                <>
                  <div className="rem-label">Action</div>
                  <div className="rem-value">{f.remediation.what}</div>
                </>
              )}
              <div className="rem-label">Owner</div>
              <div className="rem-value"><b>{f.remediation.who}</b></div>
              <div className="rem-label">Timescale</div>
              <div className="rem-value"><b>{f.remediation.when}</b></div>
              <div className="rem-label">Effort</div>
              <div className="rem-value">
                <span className={`rem-pill rem-pill-${f.remediation.effort.toLowerCase()}`}>
                  {effortLabel(f.remediation.effort)}
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}

/**
 * Sprint G.4.4: pulsante "Ask the analyst" nel header Results.
 * Apre il ChatDrawer scoped sull'analisi corrente invece di navigare a
 * una route separata (l'utente non perde più il contesto del finding).
 */
function AskAnalystButton({ analysisId }: { analysisId: string }) {
  const { open } = useChatDrawer();
  return (
    <button
      type="button"
      className="btn btn-link"
      onClick={() => open(analysisId)}
      title="Ask grounded questions about this analysis"
    >
      <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
      </svg>
      Ask the analyst
    </button>
  );
}

/**
 * Sprint G.3: button Download che chiama il backend con auth header
 * via fetch+Blob. Sostituisce l'href statico che causava 401.
 *
 * Stati gestiti: idle / downloading / error. L'errore appare inline come
 * tooltip + classe `btn-error`, niente toast / alert popup.
 */
function DownloadReportButton({ analysisId }: { analysisId: string }) {
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
      // Reset to idle dopo 4s così il bottone torna cliccabile
      window.setTimeout(() => setState('idle'), 4000);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`btn btn-link${state === 'error' ? ' btn-error' : ''}`}
      title={state === 'error' ? errMsg ?? 'Download failed' : 'Download the gap analysis report (DOCX)'}
      disabled={state === 'downloading'}
    >
      <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="7 10 12 15 17 10" />
        <line x1="12" y1="15" x2="12" y2="3" />
      </svg>
      {state === 'downloading' ? 'Downloading…' : state === 'error' ? 'Download failed' : 'Download'}
    </button>
  );
}


/**
 * Fase A — Re-analyse: re-runs the pipeline on the saved corpus of this
 * analysis (no re-upload). Streams SSE progress inline on the button label,
 * then navigates to the freshly created analysis so Compare has material.
 */
function ReanalyseButton({ analysisId }: { analysisId: string }) {
  const [state, setState] = useState<'idle' | 'running' | 'error'>('idle');
  const [pct, setPct] = useState(0);
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const handleClick = async () => {
    if (state === 'running') return;
    if (!window.confirm('Re-analyse this documentation set? This runs the full analysis again on the stored documents and creates a new result you can compare against this one.')) return;
    setState('running');
    setErrMsg(null);
    setPct(0);
    try {
      let newId: string | null = null;
      await runReanalyse(analysisId, (ev: SseEvent) => {
        if ('pct' in ev) setPct(Math.round(ev.pct));
        if ('done' in ev && ev.done) newId = ev.analysis_id;
        if ('error' in ev) throw new Error(ev.error);
      });
      if (newId) {
        await queryClient.invalidateQueries({ queryKey: ['analyses'] });
        navigate(`/analyses/${newId}/compare?against=${analysisId}`);
      } else {
        throw new Error('The analysis did not complete.');
      }
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
      className={`btn btn-link${state === 'error' ? ' btn-error' : ''}`}
      title={state === 'error' ? errMsg ?? 'Re-analyse failed' : 'Run the analysis again on the stored documents'}
      disabled={state === 'running'}
    >
      <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M21 12a9 9 0 1 1-2.64-6.36" />
        <polyline points="21 3 21 9 15 9" />
      </svg>
      {state === 'running' ? `Re-analysing… ${pct}%` : state === 'error' ? 'Re-analyse failed' : 'Re-analyse'}
    </button>
  );
}

function EmptyState() {
  return (
    <div className="main-inner">
      <header className="compact-header">
        <div>
          <div className="eyebrow">
            <Link to="/dashboard">Analyses</Link>
          </div>
          <h1 className="page-title">No analysis to display</h1>
          <div className="page-meta">
            Start a new analysis to see findings, expiries and a priority plan.
          </div>
        </div>
        <div className="header-right">
          <div className="header-actions">
            <Link to="/new-analysis" className="btn btn-accent">
              <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              Start a new analysis
            </Link>
          </div>
        </div>
      </header>
    </div>
  );
}

export function Results() {
  const { id } = useParams();
  const isDemo = !id || id === 'demo';
  const analysisQuery = useAnalysis(isDemo ? undefined : id);
  const result = analysisQuery.data?.result;
  // Sprint R6 — severity filter state (hooks must precede the early returns)
  const [severityFilter, setSeverityFilter] = useState<'all' | 'major' | 'minor' | 'obs'>('all');
  const findings: Finding[] = useMemo(
    () => (result ? result.norms.flatMap((n) => n.clauses).map(mapClause) : []),
    [result],
  );
  const visibleFindings = useMemo(
    () => (severityFilter === 'all' ? findings : findings.filter((f) => f.severity === severityFilter)),
    [findings, severityFilter],
  );

  if (analysisQuery.isLoading && !isDemo) {
    return (
      <div className="main-inner">
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>
          Loading analysis…
        </div>
      </div>
    );
  }

  if (!result) {
    return <EmptyState />;
  }

  const company = result.company;
  const sector = result.context.sector;
  const totalClauses = result.norms.reduce((sum, n) => sum + n.clauses.length, 0);
  const date = new Date(result.analysis_date).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });

  const norms = result.norms;

  const totals = result.norms.reduce(
    (acc, n) => ({
      major: acc.major + n.major_count,
      minor: acc.minor + n.minor_count,
      obs: acc.obs + n.observation_count,
      conf: acc.conf + n.conformant_count,
      spof: acc.spof + n.spof_count,
    }),
    { major: 0, minor: 0, obs: 0, conf: 0, spof: 0 },
  );

  const hasExpiry =
    result.expiry_report &&
    (result.expiry_report.expired_documents.length > 0 ||
      result.expiry_report.expiring_soon.length > 0);
  const hasIntegrations =
    result.executive_summary && result.executive_summary.top_priority_integrations.length > 0;
  const hasNarrative =
    result.executive_summary && result.executive_summary.executive_narrative.trim().length > 0;
  const hasSnapshot = !!result.executive_summary?.company_snapshot;

  return (
    <div className="main-inner">
      <header className="compact-header">
        <div>
          <div className="eyebrow">
            <Link to="/dashboard">Analyses</Link>
            <span className="sep">/</span>
            <span>{company}</span>
          </div>
          <h1 className="page-title">Compliance review</h1>
          <div className="page-meta">
            {company}
            <span className="sep">·</span>{sector}
            <span className="sep">·</span>{totalClauses} clauses
            <span className="sep">·</span>{date}
          </div>
        </div>
        <div className="header-right">
          <div className="score-row">
            {norms.map((n) => (
              <div key={n.norm} className="score-item">
                <span className="score-name">{n.norm.replace(':2015', '').replace(':2018', '')}</span>
                <span className="score-value">{n.overall_score}<span className="pct">%</span></span>
              </div>
            ))}
          </div>
          <div className="header-actions">
            <AskAnalystButton analysisId={id!} />
            <ReanalyseButton analysisId={id!} />
            <DownloadReportButton analysisId={id!} />
          </div>
        </div>
      </header>

      {/* Overview section — Phase 4 outputs */}
      {hasSnapshot && (
        <CompanySnapshotCard snapshot={result.executive_summary!.company_snapshot} />
      )}
      {hasNarrative && (
        <ExecutiveNarrative text={result.executive_summary!.executive_narrative} />
      )}

      <p className="summary">
        {totals.major > 0 ? (
          <>
            {totals.major === 1 ? 'One' : `${totals.major}`} <span className="num major">{totals.major === 1 ? 'major finding' : 'major findings'}</span> need addressing.
            {totals.spof > 0 && (
              <>
                {' '}{totals.spof === 1 ? 'One is a' : `${totals.spof} are`} <span className="num spof">{totals.spof === 1 ? 'single point of failure' : 'single points of failure'}</span>.
              </>
            )}
          </>
        ) : (
          <>No major findings. Documentation is largely conformant.</>
        )}
      </p>

      <nav className="tabs">
        <a className="tab active" href="#findings">Findings <span className="tab-count">{findings.length}</span></a>
        <Link className="tab" to={`/analyses/${id}/plan`}>Plan <span className="tab-count">{totals.major + totals.minor} open</span></Link>
        <Link className="tab" to={`/analyses/${id}/compare`}>Compare</Link>
      </nav>

      {hasExpiry && <ExpiryTable report={result.expiry_report!} />}
      {result.documented_info_report && (
        <DocumentedInfoSection report={result.documented_info_report} />
      )}
      {(result.cross_clause_findings?.length ?? 0) > 0 && (
        <CrossClauseSection findings={result.cross_clause_findings!} />
      )}
      {result.risk_register_extract && result.risk_register_extract.total_risks > 0 && (
        <RiskRegisterSection register={result.risk_register_extract} />
      )}
      {hasIntegrations && (
        <PriorityIntegrationsList items={result.executive_summary!.top_priority_integrations} />
      )}

      <div id="findings" className="section-break">
        <div className="section-title">
          By severity<span className="count">{visibleFindings.length} of {findings.length}</span>
        </div>
        <div className="filter-group">
          {/* Sprint R6: filters are live (previously decorative) */}
          <button
            className={`filter-chip${severityFilter === 'all' ? ' active' : ''}`}
            onClick={() => setSeverityFilter('all')}
            type="button"
          >All</button>
          <button
            className={`filter-chip${severityFilter === 'major' ? ' active' : ''}`}
            onClick={() => setSeverityFilter('major')}
            type="button"
          ><span className="dot major"></span>Major <span style={{ color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', fontSize: 11, marginLeft: 3 }}>{totals.major}</span></button>
          <button
            className={`filter-chip${severityFilter === 'minor' ? ' active' : ''}`}
            onClick={() => setSeverityFilter('minor')}
            type="button"
          ><span className="dot minor"></span>Minor <span style={{ color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', fontSize: 11, marginLeft: 3 }}>{totals.minor}</span></button>
          <button
            className={`filter-chip${severityFilter === 'obs' ? ' active' : ''}`}
            onClick={() => setSeverityFilter('obs')}
            type="button"
          ><span className="dot obs"></span>Obs. <span style={{ color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', fontSize: 11, marginLeft: 3 }}>{totals.obs}</span></button>
        </div>
      </div>

      {analysisQuery.isLoading && !isDemo && (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>Loading analysis…</div>
      )}

      {visibleFindings.length === 0 && (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>
          No findings match this filter.
        </div>
      )}

      {visibleFindings.map((f, i) => (
        <FindingCard key={f.clauseId} f={f} defaultExpanded={i === 0 && severityFilter === 'all'} />
      ))}
    </div>
  );
}
