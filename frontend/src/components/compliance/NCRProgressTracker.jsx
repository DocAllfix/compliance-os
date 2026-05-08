// @ts-nocheck
import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  AlertTriangle, AlertCircle, Eye, CheckCircle2,
  Zap, ChevronDown, RotateCcw, MessageSquare, Check,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { api } from '@/api/apiClient';

// ── Status config ─────────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  open: {
    label: 'Open',
    next:  'in_progress',
    style: 'bg-destructive/10 text-destructive border-destructive/25',
  },
  in_progress: {
    label: 'In Progress',
    next:  'closed',
    style: 'bg-warning/10 text-warning border-warning/25',
  },
  closed: {
    label: 'Closed',
    next:  'open',
    style: 'bg-success/10 text-success border-success/25',
  },
};

// ── Severity config ───────────────────────────────────────────────────────────

const SEVERITY_CONFIG = {
  MAJOR: {
    icon:  AlertTriangle,
    badge: 'bg-destructive text-white',
    order: 1,
  },
  MINOR: {
    icon:  AlertCircle,
    badge: 'bg-warning text-bg-deep',
    order: 2,
  },
  OBSERVATION: {
    icon:  Eye,
    badge: 'bg-severity-obs text-bg-deep',
    order: 3,
  },
};

const EFFORT_COLOR = {
  HIGH:   'text-destructive',
  MEDIUM: 'text-warning',
  LOW:    'text-success',
};

// ── Sub-components ────────────────────────────────────────────────────────────

function ProgressBar({ value, label, color = 'bg-primary' }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="text-xs font-mono text-foreground">{value}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-muted/30 overflow-hidden">
        <motion.div
          className={`h-full rounded-full ${color}`}
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] }}
        />
      </div>
    </div>
  );
}

function StatusButton({ status, onCycle, disabled }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.open;
  const nextLabel = STATUS_CONFIG[cfg.next]?.label || cfg.label;
  return (
    <button
      onClick={(e) => { e.stopPropagation(); onCycle(); }}
      disabled={disabled}
      aria-label={`Status: ${cfg.label}. Click to set ${nextLabel}`}
      className={`
        inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium
        border transition-all duration-150 cursor-pointer
        hover:opacity-80 active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed
        ${cfg.style}
      `}
    >
      {status === 'closed' && <Check className="w-3 h-3" />}
      {cfg.label}
    </button>
  );
}

// ── NCR Card ──────────────────────────────────────────────────────────────────

function NCRCard({ gap, onStatusChange, analysisId }) {
  const [expanded, setExpanded]   = useState(false);
  const [note, setNote]           = useState(gap.notes || '');
  const [editingNote, setEditingNote] = useState(false);
  const [updating, setUpdating]   = useState(false);

  const sevCfg  = SEVERITY_CONFIG[gap.severity] || SEVERITY_CONFIG.MINOR;
  const SevIcon = sevCfg.icon;
  const status  = gap.status || 'open';

  const handleCycle = async () => {
    if (updating) return;
    const next = STATUS_CONFIG[status]?.next || 'open';
    setUpdating(true);
    try {
      if (analysisId && !analysisId.startsWith('mock_')) {
        await api.compliance.updateAction(analysisId, gap.clause_id, next, note);
      }
      onStatusChange?.(gap.clause_id, next);
    } catch {
      // silently handle — optimistic UI already updated
    } finally {
      setUpdating(false);
    }
  };

  const handleSaveNote = async () => {
    if (analysisId && !analysisId.startsWith('mock_')) {
      await api.compliance.updateAction(analysisId, gap.clause_id, status, note).catch(() => {});
    }
    setEditingNote(false);
  };

  return (
    <div
      className={`
        rounded-lg border transition-colors duration-150
        ${status === 'closed'
          ? 'border-border bg-card opacity-60'
          : gap.is_spof
            ? 'border-spof/30 bg-spof/5'
            : 'border-border bg-card'}
      `}
    >
      {/* Card header */}
      <div
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-label={`${gap.clause_id}: ${gap.clause_title}`}
        className="flex items-start gap-3 px-4 py-3 cursor-pointer hover:bg-muted/10 rounded-t-lg transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-primary"
        onClick={() => setExpanded(v => !v)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded(v => !v); } }}
      >
        {/* Severity icon — decorative, info carried by clause title and StatusButton */}
        <div className={`mt-0.5 p-1.5 rounded-md shrink-0 ${sevCfg.badge}`} aria-hidden="true">
          <SevIcon className="w-3.5 h-3.5" />
        </div>

        {/* Clause info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-xs text-muted-foreground">{gap.clause_id}</span>
            {gap.is_spof && (
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-spof/15 text-spof border border-spof/30">
                <Zap className="w-2.5 h-2.5" />SPoF
              </span>
            )}
          </div>
          <p className="text-sm font-medium text-foreground mt-0.5 leading-snug">
            {gap.clause_title}
          </p>
          {!expanded && (
            <p className="text-xs text-muted-foreground mt-1 line-clamp-1">
              {gap.finding}
            </p>
          )}
        </div>

        {/* Right: status + effort + chevron */}
        <div className="flex items-center gap-2 shrink-0 ml-2">
          {gap.remediation?.effort && (
            <span className={`text-xs font-medium hidden sm:block ${EFFORT_COLOR[gap.remediation.effort] || ''}`}>
              {gap.remediation.effort}
            </span>
          )}
          <StatusButton status={status} onCycle={handleCycle} disabled={updating} />
          <ChevronDown
            className={`w-4 h-4 text-muted-foreground transition-transform duration-150 ${expanded ? 'rotate-180' : ''}`}
          />
        </div>
      </div>

      {/* Expanded detail */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18, ease: [0.25, 0.46, 0.45, 0.94] }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-1 border-t border-border space-y-4">

              {/* Finding */}
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1.5">
                  Finding
                </p>
                <p className="text-sm text-foreground leading-relaxed">{gap.finding}</p>
              </div>

              {/* Action plan */}
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1.5">
                  Action Plan
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="sm:col-span-3">
                    <p className="text-xs text-muted-foreground">What</p>
                    <p className="text-sm text-foreground mt-0.5 leading-relaxed">{gap.remediation?.what}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Who</p>
                    <p className="text-sm text-foreground mt-0.5">{gap.remediation?.who}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">When</p>
                    <p className="text-sm text-foreground mt-0.5">{gap.remediation?.when}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Effort</p>
                    <p className={`text-sm font-medium mt-0.5 ${EFFORT_COLOR[gap.remediation?.effort] || ''}`}>
                      {gap.remediation?.effort}
                    </p>
                  </div>
                </div>
              </div>

              {/* Notes */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                    <MessageSquare className="w-3 h-3" />Notes
                  </p>
                  {!editingNote && (
                    <button
                      onClick={() => setEditingNote(true)}
                      className="text-xs text-muted-foreground hover:text-primary transition-colors"
                    >
                      {note ? 'Edit' : 'Add note'}
                    </button>
                  )}
                </div>

                {editingNote ? (
                  <div className="space-y-2">
                    <textarea
                      value={note}
                      onChange={e => setNote(e.target.value)}
                      placeholder="Add a note about this action item…"
                      rows={3}
                      className="w-full resize-none bg-bg-elevated border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors"
                    />
                    <div className="flex gap-2">
                      <Button size="sm" onClick={handleSaveNote} className="h-8 text-xs">Save</Button>
                      <Button size="sm" variant="ghost" onClick={() => setEditingNote(false)} className="h-8 text-xs">Cancel</Button>
                    </div>
                  </div>
                ) : note ? (
                  <p className="text-sm text-muted-foreground italic">{note}</p>
                ) : (
                  <p className="text-xs text-muted-foreground/50">No notes yet.</p>
                )}
              </div>

            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function NCRProgressTracker({ gaps = [], analysisId, onStatusChange }) {
  const [localStatuses, setLocalStatuses] = useState({});

  const gapsWithStatus = useMemo(() => {
    return gaps
      .filter(g => g.severity !== 'CONFORMANT')
      .map(g => ({
        ...g,
        status: localStatuses[g.clause_id] ?? g.status ?? 'open',
      }))
      .sort((a, b) => {
        if (a.is_spof && a.severity === 'MAJOR' && !(b.is_spof && b.severity === 'MAJOR')) return -1;
        if (!(a.is_spof && a.severity === 'MAJOR') && b.is_spof && b.severity === 'MAJOR') return 1;
        const oa = SEVERITY_CONFIG[a.severity]?.order ?? 99;
        const ob = SEVERITY_CONFIG[b.severity]?.order ?? 99;
        return oa - ob;
      });
  }, [gaps, localStatuses]);

  const stats = useMemo(() => {
    const total  = gapsWithStatus.length;
    const closed = gapsWithStatus.filter(g => g.status === 'closed').length;
    const majors = gapsWithStatus.filter(g => g.severity === 'MAJOR');
    const majorsClosed = majors.filter(g => g.status === 'closed').length;
    return {
      total,
      closed,
      overallPct:  total  > 0 ? Math.round((closed / total) * 100)              : 0,
      majorPct:    majors.length > 0 ? Math.round((majorsClosed / majors.length) * 100) : 100,
      majorTotal:  majors.length,
      majorClosed: majorsClosed,
    };
  }, [gapsWithStatus]);

  const handleStatusChange = (clauseId, newStatus) => {
    setLocalStatuses(prev => ({ ...prev, [clauseId]: newStatus }));
    onStatusChange?.(clauseId, newStatus);
  };

  if (gaps.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center text-sm text-muted-foreground">
        No non-conformities to track.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Progress header */}
      <div className="rounded-lg border border-border bg-card px-5 py-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">NCR Action Tracker</h2>
          <span className="text-xs text-muted-foreground">
            {stats.closed} / {stats.total} actions closed
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <ProgressBar
            value={stats.majorPct}
            label={`Major closures (${stats.majorClosed}/${stats.majorTotal})`}
            color="bg-destructive"
          />
          <ProgressBar
            value={stats.overallPct}
            label="Overall progress"
            color="bg-primary"
          />
        </div>
      </div>

      {/* NCR cards */}
      <div className="space-y-2">
        {gapsWithStatus.map(gap => (
          <NCRCard
            key={gap.clause_id}
            gap={gap}
            analysisId={analysisId}
            onStatusChange={handleStatusChange}
          />
        ))}
      </div>
    </div>
  );
}
