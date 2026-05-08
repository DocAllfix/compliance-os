// @ts-nocheck
import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Download, TrendingUp, AlertTriangle, Zap, LayoutGrid, ClipboardList } from 'lucide-react';
import { Button } from '@/components/ui/button';
import GapMatrix from '@/components/compliance/GapMatrix';
import NCRProgressTracker from '@/components/compliance/NCRProgressTracker';
import DocumentViewer from '@/components/compliance/DocumentViewer';
import ChatPanel from '@/components/compliance/ChatPanel';
import ErrorBoundary from '@/components/shared/ErrorBoundary';
import { MOCK_GAPS, MOCK_ANALYSIS } from '@/lib/mockData';

// ── Score summary ─────────────────────────────────────────────────────────────

function ScoreSummary({ result }) {
  const norm = result?.norms?.[0];
  if (!norm) return null;

  const score = norm.overall_score ?? 0;
  const scoreColor = score >= 75 ? 'text-success' : score >= 50 ? 'text-warning' : 'text-destructive';

  return (
    <div className="flex items-center flex-wrap gap-4 px-5 py-3 rounded-lg border border-border bg-card">
      <div className="flex items-center gap-3">
        <TrendingUp className="w-4 h-4 text-muted-foreground" />
        <div>
          <p className="text-[11px] text-muted-foreground uppercase tracking-wide">Score</p>
          <p className={`text-xl font-semibold font-mono ${scoreColor}`}>{score}</p>
        </div>
      </div>
      <div className="w-px h-8 bg-border" />
      <div className="flex items-center gap-3">
        <AlertTriangle className="w-4 h-4 text-destructive" />
        <div>
          <p className="text-[11px] text-muted-foreground uppercase tracking-wide">Major</p>
          <p className="text-xl font-semibold text-destructive">{norm.major_count}</p>
        </div>
      </div>
      {norm.spof_count > 0 && (
        <>
          <div className="w-px h-8 bg-border" />
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-spof" />
            <div>
              <p className="text-[11px] text-muted-foreground uppercase tracking-wide">SPoF</p>
              <p className="text-xl font-semibold text-spof">{norm.spof_count}</p>
            </div>
          </div>
        </>
      )}
      <div className="ml-auto text-right">
        <p className="text-xs text-muted-foreground">{result?.company}</p>
        <p className="text-[11px] text-muted-foreground/60">
          {result?.analysis_date ? new Date(result.analysis_date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : ''}
        </p>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

const TABS = [
  { key: 'matrix',  label: 'Gap Matrix',  icon: LayoutGrid },
  { key: 'tracker', label: 'NCR Tracker', icon: ClipboardList },
];

export default function AnalysisDetail() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [analysis, setAnalysis]     = useState(null);
  const [loading, setLoading]       = useState(true);
  const [tab, setTab]               = useState('matrix');
  const [activeSource, setActiveSource] = useState(null);

  useEffect(() => {
    const fetchAnalysis = async () => {
      if (id?.startsWith('mock_')) {
        setAnalysis(MOCK_ANALYSIS);
        setLoading(false);
        return;
      }
      try {
        const res = await fetch(`/api/compliance/analyses/${id}`);
        if (!res.ok) throw new Error('Not found');
        const data = await res.json();
        // Reconstruct norms from result_json if needed
        const result = data.result_json ? JSON.parse(data.result_json) : data;
        setAnalysis(result);
      } catch {
        setAnalysis(MOCK_ANALYSIS);
      } finally {
        setLoading(false);
      }
    };
    fetchAnalysis();
  }, [id]);

  const gaps = analysis?.norms?.flatMap(n => n.clauses) || [];

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-16 rounded-lg bg-muted/20" />
        <div className="h-8 rounded bg-muted/20 w-48" />
        <div className="h-96 rounded-lg bg-muted/20" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/history')} className="h-8 w-8">
          <ArrowLeft className="w-4 h-4" />
        </Button>
        <div className="flex-1">
          <h1 className="text-xl font-semibold tracking-tight">{analysis?.company || 'Analysis Detail'}</h1>
          <p className="text-xs font-mono text-muted-foreground mt-0.5">{id}</p>
        </div>
        <Button
          variant="outline" size="sm" className="gap-1.5"
          onClick={() => window.open(`/api/compliance/analyses/${id}/download`, '_blank')}
        >
          <Download className="w-3.5 h-3.5" />
          Download Report
        </Button>
      </div>

      {/* Score summary */}
      <ScoreSummary result={analysis} />

      {/* Tabs */}
      <div role="tablist" aria-label="Analysis views" className="flex items-center gap-1 border-b border-border pb-0">
        {TABS.map(t => {
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              aria-controls={`tabpanel-${t.key}`}
              id={`tab-${t.key}`}
              onClick={() => setTab(t.key)}
              className={`
                flex items-center gap-1.5 px-3 py-2 text-sm font-medium transition-colors duration-150
                border-b-2 -mb-px
                ${tab === t.key
                  ? 'border-primary text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'}
              `}
            >
              <Icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div
        role="tabpanel"
        id={`tabpanel-${tab}`}
        aria-labelledby={`tab-${tab}`}
        className="grid grid-cols-1 lg:grid-cols-[1fr_320px] xl:grid-cols-[1fr_360px] gap-4 min-h-[600px]"
      >
        {/* Left panel */}
        <div>
          <ErrorBoundary title="Gap matrix unavailable">
            {tab === 'matrix' && (
              <GapMatrix
                gaps={gaps}
                onSourceClick={setActiveSource}
                onStatusChange={() => {}}
              />
            )}
            {tab === 'tracker' && (
              <NCRProgressTracker
                gaps={gaps}
                analysisId={id}
                onStatusChange={() => {}}
              />
            )}
          </ErrorBoundary>
        </div>

        {/* Right panel: DocumentViewer + Chat */}
        <div className="flex flex-col gap-4">
          <div className="flex-1 min-h-[280px]">
            <ErrorBoundary title="Document preview unavailable" description="The document could not be loaded. Try selecting a different source reference.">
              <DocumentViewer
                fileUrl={activeSource?.fileUrl || null}
                targetPages={activeSource?.pages || []}
                onToggleExpand={() => {}}
              />
            </ErrorBoundary>
          </div>
          <div className="h-[280px]">
            <ErrorBoundary title="Chat unavailable">
              <ChatPanel
                analysisId={id}
                onSourceClick={setActiveSource}
              />
            </ErrorBoundary>
          </div>
        </div>
      </div>
    </div>
  );
}
