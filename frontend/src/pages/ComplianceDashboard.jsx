// @ts-nocheck
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/apiClient';
import { Button } from '@/components/ui/button';
import { PlusCircle, FileSearch, TrendingUp, AlertTriangle, Clock } from 'lucide-react';
import {
  ResponsiveContainer, LineChart, Line,
  XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts';

// ── Sub-components ────────────────────────────────────────────────────────────

function ScorePill({ score }) {
  const { color, label } =
    score >= 75 ? { color: 'bg-success/10 text-success',        label: 'Good' } :
    score >= 50 ? { color: 'bg-warning/10 text-warning',        label: 'At risk' } :
                  { color: 'bg-destructive/10 text-destructive', label: 'Critical' };
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      <span className="font-mono">{score}</span>
      <span className="opacity-70">{label}</span>
    </span>
  );
}

function MajorPill({ count }) {
  if (count === 0) return <span className="text-xs text-muted-foreground">None</span>;
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-destructive/10 text-destructive">
      <AlertTriangle className="w-3 h-3" />{count}
    </span>
  );
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-bg-elevated border border-border rounded-lg px-3 py-2 text-xs">
      <p className="text-muted-foreground mb-1">{label}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color }} className="font-mono">
          {p.name}: {p.value}
        </p>
      ))}
    </div>
  );
};

// ── Main component ────────────────────────────────────────────────────────────

export default function ComplianceDashboard() {
  const navigate = useNavigate();

  const { data: analyses = [], isLoading: loading } = useQuery({
    queryKey: ['compliance-analyses-dashboard'],
    queryFn: () => api.compliance.list(20),
    initialData: [],
  });

  const recent = analyses.slice(0, 5);

  const kpis = [
    {
      label: 'Total Analyses',
      value: loading ? '—' : String(analyses.length),
      icon: FileSearch,
      sub: 'All time',
    },
    {
      label: 'Avg. Compliance Score',
      value: loading ? '—' : analyses.length
        ? (analyses.reduce((s, a) => s + (a.overall_score ?? 0), 0) / analyses.length).toFixed(1)
        : '—',
      icon: TrendingUp,
      sub: 'Across all analyses',
    },
    {
      label: 'Open Major Gaps',
      value: loading ? '—' : String(analyses.reduce((s, a) => s + (a.major_count ?? 0), 0)),
      icon: AlertTriangle,
      sub: 'Requiring action',
      alert: true,
    },
    {
      label: 'Last Analysis',
      value: loading ? '—' : analyses[0]
        ? new Date(analyses[0].analysis_date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
        : '—',
      icon: Clock,
      sub: analyses[0]?.company || '',
    },
  ];

  // Build trend chart data from last 10 analyses (oldest first)
  const trendData = [...analyses].slice(0, 10).reverse().map((a, i) => ({
    name: new Date(a.analysis_date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }),
    score: a.overall_score ?? 0,
  }));

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">Gap Analysis Overview</h1>
          <p className="text-sm text-muted-foreground mt-1">ISO 9001 · 14001 · 45001 compliance status</p>
        </div>
        <Button onClick={() => navigate('/new-analysis')} className="gap-2">
          <PlusCircle className="w-4 h-4" />
          New Analysis
        </Button>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {kpis.map((kpi) => {
          const Icon = kpi.icon;
          return (
            <div
              key={kpi.label}
              className={`rounded-lg border bg-card p-4 flex items-start gap-3 ${kpi.alert ? 'border-destructive/30' : 'border-border'}`}
            >
              <div className={`p-2 rounded-md shrink-0 mt-0.5 ${kpi.alert ? 'bg-destructive/10' : 'bg-muted/40'}`}>
                <Icon className={`w-4 h-4 ${kpi.alert ? 'text-destructive' : 'text-muted-foreground'}`} />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground truncate">{kpi.label}</p>
                <p className={`text-lg font-semibold tracking-tight mt-0.5 ${kpi.alert ? 'text-destructive' : 'text-foreground'}`}>
                  {kpi.value}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5 truncate">{kpi.sub}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Trend chart */}
      {trendData.length >= 2 && (
        <div className="rounded-lg border border-border bg-card p-5">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-4">
            Score Trend
          </p>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={trendData} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#8a95a8' }} axisLine={false} tickLine={false} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: '#8a95a8' }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Line
                type="monotone" dataKey="score" name="Score"
                stroke="#269e8a" strokeWidth={2} dot={{ r: 3, fill: '#269e8a' }}
                activeDot={{ r: 5, fill: '#33c9af' }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Recent analyses table */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Recent Analyses
          </h2>
          <Button variant="ghost" size="sm" onClick={() => navigate('/history')} className="text-xs">
            View all
          </Button>
        </div>

        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/20">
                <th className="text-left px-4 py-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">Company</th>
                <th className="text-left px-4 py-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">Standards</th>
                <th className="text-left px-4 py-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">Score</th>
                <th className="text-left px-4 py-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">Major Gaps</th>
                <th className="text-left px-4 py-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">Date</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {loading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <tr key={i} className="border-b border-border">
                    {Array.from({ length: 6 }).map((_, j) => (
                      <td key={j} className="px-4 py-3">
                        <div className="h-4 rounded bg-muted/30 animate-pulse" />
                      </td>
                    ))}
                  </tr>
                ))
              ) : recent.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center">
                    <p className="text-sm text-muted-foreground">No analyses yet.</p>
                    <button onClick={() => navigate('/new-analysis')} className="mt-2 text-sm text-primary hover:underline">
                      Run your first analysis
                    </button>
                  </td>
                </tr>
              ) : (
                recent.map((a) => (
                  <tr
                    key={a.id}
                    role="button"
                    tabIndex={0}
                    className="border-b border-border last:border-0 hover:bg-muted/20 transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-primary"
                    onClick={() => navigate(`/analysis/${a.id}`)}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/analysis/${a.id}`); } }}
                  >
                    <td className="px-4 py-3 font-medium text-foreground">{a.company}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {(a.norms || []).map((n) => (
                        <span key={n} className="inline-block mr-1 px-1.5 py-0.5 rounded text-xs bg-muted/40 font-mono">
                          {n.split(':')[0]}
                        </span>
                      ))}
                    </td>
                    <td className="px-4 py-3"><ScorePill score={a.overall_score ?? 0} /></td>
                    <td className="px-4 py-3"><MajorPill count={a.major_count ?? 0} /></td>
                    <td className="px-4 py-3 text-muted-foreground text-xs">
                      {new Date(a.analysis_date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button variant="ghost" size="sm" className="text-xs h-8">View</Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
