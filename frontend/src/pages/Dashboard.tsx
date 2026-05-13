/**
 * Dashboard — landing surface for the compliance manager.
 *
 * All numbers, the sparkline, and the severity breakdown are derived from
 * the real list of completed analyses (useAnalyses). Empty state shown when
 * the user has not run any analysis yet. No hard-coded mocks.
 */
import { Link } from 'react-router-dom';
import { useAnalyses } from '@/lib/hooks';
import { useAuth } from '@/lib/auth';
import type { AnalysisSummary } from '@/lib/api';

interface RecentItem {
  id: string;
  name: string;
  company: string;
  date: string;
  clauses: number;
  counts: { maj: number; min: number; obs: number; conf: number };
  score: number;
}

interface DashboardKpis {
  overall_score: number | null;     // weighted average over latest 5 analyses
  open_major_total: number;
  spof_total: number;
  documents_total: number;          // sum over latest 5
  trend_pp: number | null;          // percentage points latest vs prior
}

function mapSummary(a: AnalysisSummary): RecentItem {
  const date = new Date(a.analysis_date).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
  const clauses =
    (a.major_count ?? 0) +
    (a.minor_count ?? 0) +
    (a.observation_count ?? 0) +
    (a.conformant_count ?? 0);
  return {
    id: a.id,
    name: 'Compliance review',
    company: a.company,
    date,
    clauses,
    counts: {
      maj: a.major_count ?? 0,
      min: a.minor_count ?? 0,
      obs: a.observation_count ?? 0,
      conf: a.conformant_count ?? 0,
    },
    score: a.overall_score ?? 0,
  };
}

function computeKpis(analyses: AnalysisSummary[]): DashboardKpis {
  if (analyses.length === 0) {
    return {
      overall_score: null,
      open_major_total: 0,
      spof_total: 0,
      documents_total: 0,
      trend_pp: null,
    };
  }

  // Sort descending by analysis_date so [0] is the latest.
  const sorted = [...analyses].sort(
    (a, b) => new Date(b.analysis_date).getTime() - new Date(a.analysis_date).getTime(),
  );
  const latestFive = sorted.slice(0, 5);

  const sumScores = latestFive.reduce((acc, a) => acc + (a.overall_score ?? 0), 0);
  const validScoreCount = latestFive.filter((a) => typeof a.overall_score === 'number').length;
  const overall_score = validScoreCount > 0 ? Math.round(sumScores / validScoreCount) : null;

  // Trend: latest vs previous, in percentage points
  const trend_pp =
    sorted.length >= 2 && sorted[0].overall_score != null && sorted[1].overall_score != null
      ? sorted[0].overall_score - sorted[1].overall_score
      : null;

  return {
    overall_score,
    open_major_total: latestFive.reduce((acc, a) => acc + (a.major_count ?? 0), 0),
    spof_total: 0, // SPoF count is per-analysis; the AnalysisSummary doesn't expose it.
                   // Future: extend API or compute from result_json on hover.
    documents_total: latestFive.length,
    trend_pp,
  };
}

function buildSparklinePath(scores: Array<{ x: number; y: number }>, width: number, height: number) {
  if (scores.length === 0) return { line: '', area: '' };
  if (scores.length === 1) {
    // Single-point fallback: horizontal line at that score
    const y = height - (scores[0].y / 100) * (height - 20) - 10;
    return {
      line: `M 0 ${y} L ${width} ${y}`,
      area: `M 0 ${y} L ${width} ${y} L ${width} ${height} L 0 ${height} Z`,
    };
  }
  const stepX = width / (scores.length - 1);
  const points = scores.map((p, i) => ({
    x: i * stepX,
    y: height - (p.y / 100) * (height - 20) - 10,
  }));
  const line = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ');
  const area = `${line} L ${width} ${height} L 0 ${height} Z`;
  return { line, area };
}

function greetingFor(displayName: string | undefined): string {
  const hour = new Date().getHours();
  const period =
    hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  const name = displayName?.split(' ')[0];
  return name ? `${period}, ${name}.` : `${period}.`;
}

function formatTrend(pp: number | null): string {
  if (pp == null) return '—';
  if (pp === 0) return 'unchanged';
  return pp > 0 ? `+${pp} vs previous` : `${pp} vs previous`;
}

export function Dashboard() {
  const { user } = useAuth();
  const analysesQuery = useAnalyses();
  const analyses = analysesQuery.data ?? [];
  const sortedAnalyses = [...analyses].sort(
    (a, b) => new Date(b.analysis_date).getTime() - new Date(a.analysis_date).getTime(),
  );
  const kpis = computeKpis(analyses);
  const recentAnalyses: RecentItem[] = sortedAnalyses.slice(0, 5).map(mapSummary);
  const todayLong = new Date().toLocaleDateString('en-GB', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });

  // Empty state — no analyses yet
  if (!analysesQuery.isLoading && analyses.length === 0) {
    return (
      <div className="main-wide-inner">
        <header className="greeting">
          <div>
            <div className="eyebrow">{todayLong}</div>
            <h1 className="greeting-title">{greetingFor(user?.display_name)}</h1>
            <p className="greeting-sub">
              Welcome to ComplianceOS. Start your first analysis to see your compliance posture.
            </p>
          </div>
          <Link className="btn btn-accent" to="/new-analysis">
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
            Start your first analysis
          </Link>
        </header>

        <div className="empty-dashboard">
          <p>
            Upload a ZIP of your company documents to get a clause-by-clause gap report against
            ISO 9001 / 14001 / 45001, with source-cited evidence and an actionable plan.
          </p>
        </div>
      </div>
    );
  }

  // Loading state
  if (analysesQuery.isLoading) {
    return (
      <div className="main-wide-inner">
        <header className="greeting">
          <div>
            <div className="eyebrow">{todayLong}</div>
            <h1 className="greeting-title">{greetingFor(user?.display_name)}</h1>
            <p className="greeting-sub" style={{ color: 'var(--text-tertiary)' }}>Loading your analyses…</p>
          </div>
        </header>
      </div>
    );
  }

  const latestAnalysis = sortedAnalyses[0];
  const latestCompanyLine = latestAnalysis
    ? `${latestAnalysis.company} is at ${latestAnalysis.overall_score ?? '—'}% overall conformance.`
    : 'No analyses yet.';

  // Sparkline scores (chronological order)
  const sparkPoints = [...sortedAnalyses]
    .reverse()
    .map((a, i) => ({ x: i, y: a.overall_score ?? 0 }));
  const sparkPath = buildSparklinePath(sparkPoints, 600, 120);
  const latestScore = latestAnalysis?.overall_score ?? null;

  // By-severity breakdown from the latest analysis
  const latestCounts = {
    maj: latestAnalysis?.major_count ?? 0,
    min: latestAnalysis?.minor_count ?? 0,
    obs: latestAnalysis?.observation_count ?? 0,
    conf: latestAnalysis?.conformant_count ?? 0,
  };
  const latestTotal = latestCounts.maj + latestCounts.min + latestCounts.obs + latestCounts.conf;
  const pct = (n: number) => (latestTotal > 0 ? Math.round((n / latestTotal) * 100) : 0);

  return (
    <div className="main-wide-inner">
      <header className="greeting">
        <div>
          <div className="eyebrow">{todayLong}</div>
          <h1 className="greeting-title">{greetingFor(user?.display_name)}</h1>
          <p className="greeting-sub">{latestCompanyLine}</p>
        </div>
        <Link className="btn btn-accent" to="/new-analysis">
          <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
          New analysis
        </Link>
      </header>

      <div className="kpi-grid">
        <div className="kpi">
          <div className="kpi-label">Overall conformance</div>
          <div className="kpi-value">
            {kpis.overall_score ?? '—'}<span className="unit">{kpis.overall_score != null ? '%' : ''}</span>
          </div>
          <div className={`kpi-trend${kpis.trend_pp != null && kpis.trend_pp > 0 ? ' up' : ''}${kpis.trend_pp != null && kpis.trend_pp < 0 ? ' down' : ''}`}>
            {kpis.trend_pp != null && kpis.trend_pp > 0 && (
              <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="18 15 12 9 6 15" /></svg>
            )}
            {kpis.trend_pp != null && kpis.trend_pp < 0 && (
              <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="6 9 12 15 18 9" /></svg>
            )}
            {formatTrend(kpis.trend_pp)}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Open major findings</div>
          <div className="kpi-value">{kpis.open_major_total}</div>
          <div className="kpi-trend">
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="5" y1="12" x2="19" y2="12" /></svg>
            across {analyses.length} analys{analyses.length === 1 ? 'is' : 'es'}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Analyses run</div>
          <div className="kpi-value">{analyses.length}</div>
          <div className="kpi-trend">
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="5" y1="12" x2="19" y2="12" /></svg>
            in this workspace
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Latest analysis</div>
          <div className="kpi-value" style={{ fontSize: '24px' }}>
            {latestAnalysis
              ? new Date(latestAnalysis.analysis_date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
              : '—'}
          </div>
          <div className="kpi-trend">
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="5" y1="12" x2="19" y2="12" /></svg>
            {latestAnalysis ? latestAnalysis.company : 'no analyses yet'}
          </div>
        </div>
      </div>

      <div className="trend-row">
        <div className="chart-card">
          <div className="chart-card-h">Overall conformance trend<span className="chart-card-sub">{sortedAnalyses.length} analys{sortedAnalyses.length === 1 ? 'is' : 'es'}</span></div>
          <div className="sparkline">
            {sparkPoints.length === 0 ? (
              <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 13 }}>No trend yet — run a second analysis to compare.</div>
            ) : (
              <svg viewBox="0 0 600 120" width="100%" height="120" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="grad-line" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.18" />
                    <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
                  </linearGradient>
                </defs>
                <line x1="0" y1="30" x2="600" y2="30" stroke="var(--border-subtle)" strokeDasharray="2 4" />
                <line x1="0" y1="60" x2="600" y2="60" stroke="var(--border-subtle)" strokeDasharray="2 4" />
                <line x1="0" y1="90" x2="600" y2="90" stroke="var(--border-subtle)" strokeDasharray="2 4" />
                <path d={sparkPath.area} fill="url(#grad-line)" />
                <path d={sparkPath.line} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
                {sparkPoints.length > 0 && latestScore != null && (
                  <>
                    <circle cx="600" cy={120 - (latestScore / 100) * 100 - 10} r="4" fill="var(--accent)" />
                    <text x="588" y={120 - (latestScore / 100) * 100 - 20} fontFamily="JetBrains Mono" fontSize="10" fill="var(--text-secondary)" textAnchor="end">
                      {latestScore}%
                    </text>
                  </>
                )}
              </svg>
            )}
          </div>
        </div>
        <div className="chart-card">
          <div className="chart-card-h">By severity<span className="chart-card-sub">latest analysis</span></div>
          {latestTotal === 0 ? (
            <div style={{ padding: 24, fontSize: 13, color: 'var(--text-tertiary)' }}>Run an analysis to see the severity breakdown.</div>
          ) : (
            <div className="breakdown-list">
              <div className="breakdown-row">
                <span className="breakdown-name"><span className="dot major" />Major</span>
                <div className="breakdown-bar"><div className="breakdown-bar-fill major" style={{ width: `${pct(latestCounts.maj)}%` }} /></div>
                <span className="breakdown-num">{latestCounts.maj}</span>
              </div>
              <div className="breakdown-row">
                <span className="breakdown-name"><span className="dot minor" />Minor</span>
                <div className="breakdown-bar"><div className="breakdown-bar-fill minor" style={{ width: `${pct(latestCounts.min)}%` }} /></div>
                <span className="breakdown-num">{latestCounts.min}</span>
              </div>
              <div className="breakdown-row">
                <span className="breakdown-name"><span className="dot obs" />Observation</span>
                <div className="breakdown-bar"><div className="breakdown-bar-fill obs" style={{ width: `${pct(latestCounts.obs)}%` }} /></div>
                <span className="breakdown-num">{latestCounts.obs}</span>
              </div>
              <div className="breakdown-row">
                <span className="breakdown-name"><span className="dot conf" />Conformant</span>
                <div className="breakdown-bar"><div className="breakdown-bar-fill conf" style={{ width: `${pct(latestCounts.conf)}%` }} /></div>
                <span className="breakdown-num">{latestCounts.conf}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="section-h">
        <h2>Recent analyses<span className="count">{recentAnalyses.length} of {analyses.length}</span></h2>
      </div>

      <div className="analysis-list">
        {recentAnalyses.map((a) => (
          <Link key={a.id} className="analysis-item" to={`/analyses/${a.id}`}>
            <div>
              <div className="analysis-name">{a.name}</div>
              <div className="analysis-meta">
                {a.company}<span className="sep">·</span>{a.date}<span className="sep">·</span>{a.clauses} clauses
              </div>
            </div>
            <div className="analysis-counts">
              <span><b>{a.counts.maj}</b>maj</span>
              <span><b>{a.counts.min}</b>min</span>
              <span><b>{a.counts.obs}</b>obs</span>
              <span><b>{a.counts.conf}</b>conf</span>
            </div>
            <div className="analysis-score">{a.score}<span className="pct">%</span></div>
            <span className="analysis-arrow">
              <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" /></svg>
            </span>
          </Link>
        ))}
      </div>

      <div className="new-cta">
        <div className="new-cta-title">Time for the next assessment?</div>
        <div className="new-cta-sub">Upload a fresh ZIP to see what's moved since {latestAnalysis ? new Date(latestAnalysis.analysis_date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : 'last time'}.</div>
        <Link className="btn btn-secondary" to="/new-analysis">
          <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 3v4a1 1 0 0 0 1 1h4" /><path d="M5 8a2 2 0 0 1 2-2h7l5 5v9a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z" /></svg>
          Start new analysis
        </Link>
      </div>
    </div>
  );
}
