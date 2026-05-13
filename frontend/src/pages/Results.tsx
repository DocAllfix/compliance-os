import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAnalysis } from '@/lib/hooks';
import type { ClauseGap } from '@/lib/api';
import { CompanySnapshotCard } from '@/pages/results/CompanySnapshotCard';
import { ExecutiveNarrative } from '@/pages/results/ExecutiveNarrative';
import { ExpiryTable } from '@/pages/results/ExpiryTable';
import { PriorityIntegrationsList } from '@/pages/results/PriorityIntegrationsList';

interface Finding {
  clauseId: string;
  title: string;
  severity: 'major' | 'minor' | 'obs';
  isSpof?: boolean;
  text: string;
  source: { file: string; page?: string };
}

function mapClause(c: ClauseGap): Finding {
  const sev: Finding['severity'] =
    c.severity === 'MAJOR' ? 'major' : c.severity === 'MINOR' ? 'minor' : 'obs';
  const src = c.sources[0];
  return {
    clauseId: c.clause_id.replace(/^(\d+)_(\d+)(?:_(\d+))?$/i, (_m, std, sec, sub) =>
      sub ? `${std} §${sec}.${sub}` : `${std} §${sec}`,
    ),
    title: c.clause_title,
    severity: sev,
    isSpof: c.is_spof,
    text: c.finding,
    source: src
      ? { file: src.file_name, page: src.pages?.[0] ? `p${src.pages[0]}` : undefined }
      : { file: '' },
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

function FindingCard({ f, defaultExpanded = false }: { f: Finding; defaultExpanded?: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  return (
    <article className={`finding${expanded ? ' expanded' : ''}`}>
      <div className="finding-head">
        {f.severity === 'major' && (
          <span className="badge badge-major"><MajorIcon />Major</span>
        )}
        {f.severity === 'minor' && <span className="badge badge-minor">Minor</span>}
        {f.severity === 'obs' && <span className="badge badge-obs">Obs.</span>}
        {f.isSpof && (
          <span className="spof-badge">
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <circle cx="12" cy="12" r="9" /><path d="M12 7v5" /><path d="M12 16h.01" />
            </svg>
            Single point of failure
          </span>
        )}
        <span className="finding-clause-id" style={{ marginLeft: 'auto' }}>{f.clauseId}</span>
      </div>
      <h2 className="finding-title">{f.title}</h2>
      <p className="finding-text">{f.text}</p>
      <a className="finding-source" href="#" onClick={(e) => e.preventDefault()}>
        <FileIcon />
        {f.source.file} {f.source.page && <span className="page">· {f.source.page}</span>}
      </a>
      <button className="finding-toggle" onClick={() => setExpanded(!expanded)}>
        <span className="label-collapsed">Show evidence and remediation</span>
        <span className="label-expanded">Hide evidence and remediation</span>
        <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9" /></svg>
      </button>
      {expanded && (
        <div className="finding-detail">
          <div className="pdf-excerpt">
            <span className="pdf-excerpt-meta">
              <FileIcon />
              {f.source.file} · page {f.source.page?.replace('p', '') ?? '?'}
            </span>
            <div className="pdf-excerpt-body">
              <h4>Excerpt</h4>
              <p><span className="highlight">L'azienda mantiene aggiornato un elenco delle prescrizioni legali applicabili alle proprie attività, prodotti e servizi.</span> L'elenco viene rivisto in caso di cambiamenti normativi o operativi.</p>
            </div>
            <div className="pdf-actions">
              <a className="pdf-action-link" href="#" onClick={(e) => e.preventDefault()}>
                <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" /></svg>
                Open full document
              </a>
            </div>
          </div>
          <div className="gap-explainer">
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><path d="M12 8v4" /><path d="M12 16h.01" /></svg>
            <div>
              <span className="gap-explainer-label">Why this is a gap</span>
              <p>The policy <strong>commits to maintaining</strong> a legal register but no register document is part of this submission. Clause 6.1.3 requires the register itself.</p>
            </div>
          </div>
          <div className="remediation">
            <div className="remediation-header">
              <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="20 6 9 17 4 12" /></svg>
              Remediation plan
            </div>
            <div className="rem-grid">
              <div className="rem-label">Action</div>
              <div className="rem-value">Establish a formal compliance obligations register listing all applicable environmental regulations, monitoring frequencies, evaluation outcomes, and review dates.</div>
              <div className="rem-label">Owner</div>
              <div className="rem-value"><b>HSE Manager</b>, with input from Operations Director and Legal Counsel.</div>
              <div className="rem-label">Timescale</div>
              <div className="rem-value"><b>30 days</b> for an initial draft. <b>90 days</b> for a fully populated register.</div>
              <div className="rem-label">Effort</div>
              <div className="rem-value"><span className="rem-pill">High</span></div>
            </div>
          </div>
        </div>
      )}
    </article>
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
  const findings: Finding[] = result.norms.flatMap((n) => n.clauses).map(mapClause);

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

  const downloadHref = `${import.meta.env.VITE_API_BASE_URL ?? ''}/api/compliance/analyses/${id}/download`;
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
            <Link
              to={`/analyses/${id}/chat`}
              className="btn btn-link"
              title="Ask grounded questions about this analysis"
            >
              <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
              </svg>
              Ask the analyst
            </Link>
            <a href={downloadHref} className="btn btn-link" target="_blank" rel="noopener noreferrer">
              <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>
              Download
            </a>
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
                {' '}One is a <span className="num spof">single point of failure</span>.
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
        <span className="tab tab-disabled" title="Available once a second analysis exists">Compare</span>
      </nav>

      {hasExpiry && <ExpiryTable report={result.expiry_report!} />}
      {hasIntegrations && (
        <PriorityIntegrationsList items={result.executive_summary!.top_priority_integrations} />
      )}

      <div id="findings" className="section-break">
        <div className="section-title">
          By severity<span className="count">{findings.length} total</span>
        </div>
        <div className="filter-group">
          <button className="filter-chip active">All</button>
          <button className="filter-chip"><span className="dot major"></span>Major <span style={{ color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', fontSize: 11, marginLeft: 3 }}>{totals.major}</span></button>
          <button className="filter-chip"><span className="dot minor"></span>Minor <span style={{ color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', fontSize: 11, marginLeft: 3 }}>{totals.minor}</span></button>
          <button className="filter-chip"><span className="dot obs"></span>Obs. <span style={{ color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', fontSize: 11, marginLeft: 3 }}>{totals.obs}</span></button>
        </div>
      </div>

      {analysisQuery.isLoading && !isDemo && (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>Loading analysis…</div>
      )}

      {findings.map((f, i) => (
        <FindingCard key={f.clauseId} f={f} defaultExpanded={i === 0} />
      ))}
    </div>
  );
}
