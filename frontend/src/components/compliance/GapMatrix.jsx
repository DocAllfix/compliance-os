// @ts-nocheck
import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  AlertTriangle, AlertCircle, Eye, CheckCircle2,
  ChevronDown, ChevronRight, FileText, Zap,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

// ── Severity config ───────────────────────────────────────────────────────────

const SEVERITY_CONFIG = {
  MAJOR: {
    label: 'MAJOR',
    icon: AlertTriangle,
    badge: 'bg-destructive text-white',
    chip:  'bg-destructive/15 text-destructive border-destructive/30',
    row:   'bg-destructive/5',
  },
  MINOR: {
    label: 'MINOR',
    icon: AlertCircle,
    badge: 'bg-warning text-bg-deep',
    chip:  'bg-warning/15 text-warning border-warning/30',
    row:   '',
  },
  OBSERVATION: {
    label: 'OBS',
    icon: Eye,
    badge: 'bg-severity-obs text-[hsl(230_30%_8%)]',
    chip:  'bg-severity-obs/15 text-severity-obs border-severity-obs/30',
    row:   '',
  },
  CONFORMANT: {
    label: 'CONF',
    icon: CheckCircle2,
    badge: 'bg-success text-bg-deep',
    chip:  'bg-success/15 text-success border-success/30',
    row:   '',
  },
};

const EFFORT_COLOR = { HIGH: 'text-destructive', MEDIUM: 'text-warning', LOW: 'text-success' };

const SEVERITY_ORDER = { MAJOR: 0, MINOR: 1, OBSERVATION: 2, CONFORMANT: 3 };

// ── Filter chips ──────────────────────────────────────────────────────────────

const FILTERS = [
  { key: 'ALL',         label: 'All',         color: '' },
  { key: 'MAJOR',       label: 'Major',       color: 'bg-destructive/15 text-destructive border-destructive/30' },
  { key: 'MINOR',       label: 'Minor',       color: 'bg-warning/15 text-warning border-warning/30' },
  { key: 'OBSERVATION', label: 'Observation', color: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30' },
  { key: 'CONFORMANT',  label: 'Conformant',  color: 'bg-success/15 text-success border-success/30' },
  { key: 'SPOF',        label: 'SPoF only',   color: 'bg-spof/15 text-spof border-spof/30' },
];

// ── Sub-components ────────────────────────────────────────────────────────────

function SeverityBadge({ severity, isSpof }) {
  const cfg = SEVERITY_CONFIG[severity] || SEVERITY_CONFIG.OBSERVATION;
  const Icon = cfg.icon;
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium tracking-wide ${cfg.badge}`}>
        <Icon className="w-3 h-3" />
        {cfg.label}
      </span>
      {isSpof && (
        <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-spof/15 text-spof border border-spof/30">
          <Zap className="w-2.5 h-2.5" />
          SPoF
        </span>
      )}
    </div>
  );
}

function ScoreChip({ score }) {
  const color =
    score >= 75 ? 'text-success' :
    score >= 50 ? 'text-warning' :
                  'text-destructive';
  return (
    <span className={`font-mono text-sm font-medium ${color}`}>{score}</span>
  );
}

function SourceChip({ source, onSourceClick }) {
  return (
    <button
      onClick={() => onSourceClick?.(source)}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-muted/30 text-muted-foreground hover:bg-primary/10 hover:text-primary transition-colors duration-150 font-mono"
    >
      <FileText className="w-3 h-3 shrink-0" />
      <span className="truncate max-w-[180px]">{source.file_name}</span>
      {source.pages?.length > 0 && (
        <span className="text-[10px] opacity-60">p.{source.pages[0]}</span>
      )}
    </button>
  );
}

function StatusBadge({ status }) {
  const map = {
    open:        'bg-destructive/10 text-destructive',
    in_progress: 'bg-warning/10 text-warning',
    closed:      'bg-success/10 text-success',
  };
  const labels = { open: 'Open', in_progress: 'In Progress', closed: 'Closed' };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${map[status] || map.open}`}>
      {labels[status] || 'Open'}
    </span>
  );
}

// ── Row (collapsed + expanded) ────────────────────────────────────────────────

function GapRow({ gap, onSourceClick, onStatusChange }) {
  const [open, setOpen] = useState(false);
  const cfg = SEVERITY_CONFIG[gap.severity] || SEVERITY_CONFIG.OBSERVATION;
  const firstSource = gap.sources?.[0];

  return (
    <>
      {/* Collapsed row */}
      <tr
        role="button"
        tabIndex={0}
        aria-expanded={open}
        className={`border-b border-border cursor-pointer transition-colors duration-100 group focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-primary ${
          open ? 'bg-bg-elevated' : `hover:bg-muted/20 ${gap.is_spof ? cfg.row : ''}`
        }`}
        onClick={() => setOpen(v => !v)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpen(v => !v); } }}
      >
        {/* SPoF strip */}
        <td className="w-1 p-0 relative">
          {gap.is_spof && (
            <div className="absolute inset-y-0 left-0 w-[3px] bg-spof rounded-sm" />
          )}
        </td>

        <td className="px-3 py-2.5 w-36">
          <SeverityBadge severity={gap.severity} isSpof={gap.is_spof} />
        </td>

        <td className="px-3 py-2.5">
          <div className="flex flex-col gap-0.5">
            <span className="font-mono text-xs text-muted-foreground">{gap.clause_id}</span>
            <span className="text-sm font-medium text-foreground leading-snug">
              {gap.clause_title}
            </span>
          </div>
        </td>

        <td className="px-3 py-2.5 w-16 text-center">
          <ScoreChip score={gap.score} />
        </td>

        <td className="px-3 py-2.5 max-w-xs hidden lg:table-cell">
          <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
            {gap.finding}
          </p>
        </td>

        <td className="px-3 py-2.5 hidden xl:table-cell">
          {firstSource && (
            <SourceChip
              source={firstSource}
              onSourceClick={(s) => { onSourceClick?.(s); }}
            />
          )}
        </td>

        <td className="px-3 py-2.5 w-8">
          <ChevronDown
            className={`w-4 h-4 text-muted-foreground transition-transform duration-150 ${open ? 'rotate-180' : ''}`}
          />
        </td>
      </tr>

      {/* Expanded detail */}
      {open && (
        <tr className="border-b border-border bg-bg-elevated">
          <td colSpan={7} className="px-4 py-4">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

              {/* Finding */}
              <div className="lg:col-span-1">
                <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-2">
                  Finding
                </p>
                <p className="text-sm text-foreground leading-relaxed max-w-[65ch]">
                  {gap.finding}
                </p>
              </div>

              {/* Evidence */}
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-2">
                  Evidence
                </p>
                {gap.sources?.length > 0 ? (
                  <div className="space-y-1.5">
                    {gap.sources.map((s, i) => (
                      <div key={i} className="flex flex-col gap-0.5">
                        <SourceChip source={s} onSourceClick={onSourceClick} />
                        {s.excerpt && (
                          <p className="text-xs text-muted-foreground ml-2 italic line-clamp-2">
                            "{s.excerpt}"
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">No source documents identified.</p>
                )}
              </div>

              {/* Action plan */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Action Plan
                  </p>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={gap.status || 'open'} />
                    {onStatusChange && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onStatusChange(gap.clause_id); }}
                        className="text-xs text-muted-foreground hover:text-primary transition-colors"
                      >
                        Update
                      </button>
                    )}
                  </div>
                </div>
                <div className="space-y-1.5 text-sm">
                  <div>
                    <span className="text-xs text-muted-foreground">What</span>
                    <p className="text-foreground text-xs leading-relaxed mt-0.5">
                      {gap.remediation?.what}
                    </p>
                  </div>
                  <div className="flex gap-4">
                    <div>
                      <span className="text-xs text-muted-foreground">Who</span>
                      <p className="text-foreground text-xs mt-0.5">{gap.remediation?.who}</p>
                    </div>
                    <div>
                      <span className="text-xs text-muted-foreground">When</span>
                      <p className="text-foreground text-xs mt-0.5">{gap.remediation?.when}</p>
                    </div>
                    <div>
                      <span className="text-xs text-muted-foreground">Effort</span>
                      <p className={`text-xs font-medium mt-0.5 ${EFFORT_COLOR[gap.remediation?.effort] || ''}`}>
                        {gap.remediation?.effort}
                      </p>
                    </div>
                  </div>
                </div>
              </div>

            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function GapMatrix({ gaps = [], onSourceClick, onStatusChange }) {
  const [activeFilters, setActiveFilters] = useState(new Set(['ALL']));

  const counts = useMemo(() => {
    const c = { MAJOR: 0, MINOR: 0, OBSERVATION: 0, CONFORMANT: 0, SPOF: 0 };
    gaps.forEach(g => {
      if (g.severity in c) c[g.severity]++;
      if (g.is_spof) c.SPOF++;
    });
    return c;
  }, [gaps]);

  const toggleFilter = (key) => {
    if (key === 'ALL') {
      setActiveFilters(new Set(['ALL']));
      return;
    }
    setActiveFilters(prev => {
      const next = new Set(prev);
      next.delete('ALL');
      if (next.has(key)) {
        next.delete(key);
        if (next.size === 0) next.add('ALL');
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const filtered = useMemo(() => {
    let list = [...gaps];

    if (!activeFilters.has('ALL')) {
      list = list.filter(g => {
        if (activeFilters.has('SPOF') && g.is_spof) return true;
        if (activeFilters.has(g.severity)) return true;
        return false;
      });
    }

    return list.sort((a, b) => {
      const sa = a.is_spof && a.severity === 'MAJOR' ? -1 : SEVERITY_ORDER[a.severity] ?? 99;
      const sb = b.is_spof && b.severity === 'MAJOR' ? -1 : SEVERITY_ORDER[b.severity] ?? 99;
      if (sa !== sb) return sa - sb;
      return a.score - b.score;
    });
  }, [gaps, activeFilters]);

  if (gaps.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center">
        <p className="text-sm text-muted-foreground">No gap analysis results available.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Filter chips */}
      <div className="flex items-center flex-wrap gap-1.5">
        {FILTERS.map(f => {
          const count = f.key === 'ALL' ? gaps.length : counts[f.key] ?? 0;
          const active = activeFilters.has(f.key);
          return (
            <button
              key={f.key}
              onClick={() => toggleFilter(f.key)}
              aria-pressed={active}
              aria-label={`Filter by ${f.label}, ${count} item${count !== 1 ? 's' : ''}`}
              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border transition-all duration-150 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary ${
                active
                  ? f.color || 'bg-primary/15 text-primary border-primary/30'
                  : 'bg-transparent text-muted-foreground border-border hover:border-muted-foreground/40'
              }`}
            >
              {f.label}
              <span className={`${active ? 'opacity-80' : 'opacity-50'}`}>{count}</span>
            </button>
          );
        })}
      </div>

      {/* Table */}
      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/20">
              <th className="w-1 p-0" />
              <th className="text-left px-3 py-2.5 text-xs font-medium uppercase tracking-wider text-muted-foreground w-36">Severity</th>
              <th className="text-left px-3 py-2.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">Clause</th>
              <th className="text-left px-3 py-2.5 text-xs font-medium uppercase tracking-wider text-muted-foreground w-16">Score</th>
              <th className="text-left px-3 py-2.5 text-xs font-medium uppercase tracking-wider text-muted-foreground hidden lg:table-cell">Finding</th>
              <th className="text-left px-3 py-2.5 text-xs font-medium uppercase tracking-wider text-muted-foreground hidden xl:table-cell">Source</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-sm text-muted-foreground">
                  No gaps match the selected filter.
                  <button onClick={() => setActiveFilters(new Set(['ALL']))} className="ml-1 text-primary hover:underline">
                    Clear filters
                  </button>
                </td>
              </tr>
            ) : (
              filtered.map((gap) => (
                <GapRow
                  key={gap.clause_id}
                  gap={gap}
                  onSourceClick={onSourceClick}
                  onStatusChange={onStatusChange}
                />
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
