// @ts-nocheck
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/apiClient';
import { Button } from '@/components/ui/button';
import { PlusCircle, AlertTriangle, Search } from 'lucide-react';
import { Input } from '@/components/ui/input';

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

export default function AnalysisHistory() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');

  const { data: analyses = [], isLoading: loading } = useQuery({
    queryKey: ['compliance-analyses-history'],
    queryFn: () => api.compliance.list(100),
    initialData: [],
  });

  const filtered = analyses.filter(a =>
    !query || a.company?.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Analysis History</h1>
          <p className="text-sm text-muted-foreground mt-1">All completed gap analyses</p>
        </div>
        <Button onClick={() => navigate('/new-analysis')} className="gap-2">
          <PlusCircle className="w-4 h-4" /> New Analysis
        </Button>
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
        <Input
          placeholder="Search by company…"
          value={query}
          onChange={e => setQuery(e.target.value)}
          className="pl-8 h-8 text-sm"
        />
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
              Array.from({ length: 4 }).map((_, i) => (
                <tr key={i} className="border-b border-border">
                  {Array.from({ length: 6 }).map((_, j) => (
                    <td key={j} className="px-4 py-3"><div className="h-4 rounded bg-muted/30 animate-pulse" /></td>
                  ))}
                </tr>
              ))
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center">
                  <p className="text-sm text-muted-foreground">
                    {query ? `No analyses matching "${query}".` : 'No analyses yet.'}
                  </p>
                  {!query && (
                    <button onClick={() => navigate('/new-analysis')} className="mt-2 text-sm text-primary hover:underline">
                      Run your first analysis
                    </button>
                  )}
                </td>
              </tr>
            ) : (
              filtered.map((a) => (
                <tr
                  key={a.id}
                  role="button"
                  tabIndex={0}
                  className="border-b border-border last:border-0 hover:bg-muted/20 transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-primary"
                  onClick={() => navigate(`/analysis/${a.id}`)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`/analysis/${a.id}`); } }}
                >
                  <td className="px-4 py-3 font-medium text-foreground">{a.company}</td>
                  <td className="px-4 py-3">
                    {(a.norms || []).map((n) => (
                      <span key={n} className="inline-block mr-1 px-1.5 py-0.5 rounded text-xs bg-muted/40 font-mono">
                        {n.split(':')[0]}
                      </span>
                    ))}
                  </td>
                  <td className="px-4 py-3"><ScorePill score={a.overall_score ?? 0} /></td>
                  <td className="px-4 py-3">
                    {(a.major_count ?? 0) === 0
                      ? <span className="text-xs text-muted-foreground">None</span>
                      : <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-destructive/10 text-destructive">
                          <AlertTriangle className="w-3 h-3" />{a.major_count}
                        </span>
                    }
                  </td>
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
  );
}
