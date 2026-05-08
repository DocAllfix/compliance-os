import React from 'react';
import { TrendingUp, TrendingDown, Minus, ArrowRight } from 'lucide-react';

const SEVERITY_COLOR = {
  MAJOR:       'text-destructive',
  MINOR:       'text-warning',
  OBSERVATION: 'text-yellow-400',
  CONFORMANT:  'text-success',
};

function DeltaBadge({ delta, direction }) {
  if (direction === 'unchanged' || delta === null) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
        <Minus className="w-3 h-3" />
        <span className="font-mono">—</span>
      </span>
    );
  }
  if (direction === 'new') {
    return <span className="text-xs text-muted-foreground italic">New</span>;
  }
  const improved = delta > 0;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-mono font-medium ${improved ? 'text-success' : 'text-destructive'}`}>
      {improved ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {improved ? '+' : ''}{delta}
    </span>
  );
}

function ScoreTransition({ scoreOld, scoreNew, direction }) {
  if (scoreOld === null) return <span className="text-xs font-mono text-foreground">{scoreNew}</span>;
  const color = direction === 'improved' ? 'text-success' : direction === 'regressed' ? 'text-destructive' : 'text-muted-foreground';
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-mono ${color}`}>
      <span className="text-muted-foreground">{scoreOld}</span>
      <ArrowRight className="w-3 h-3 text-muted-foreground/50" />
      <span className="font-medium">{scoreNew}</span>
    </span>
  );
}

export default function DeltaView({ delta }) {
  if (!delta || delta.error) {
    return (
      <div className="rounded-lg border border-border bg-card p-6 text-center text-sm text-muted-foreground">
        {delta?.error || 'No comparison data available.'}
      </div>
    );
  }

  const overallDelta = delta.overall_delta ?? 0;
  const overallColor = overallDelta > 0 ? 'text-success' : overallDelta < 0 ? 'text-destructive' : 'text-muted-foreground';

  return (
    <div className="space-y-4">
      {/* Overall delta header */}
      <div className="rounded-lg border border-border bg-card px-5 py-4 flex items-center justify-between">
        <div>
          <p className="text-xs text-muted-foreground uppercase tracking-wide">Overall Score Change</p>
          <p className={`text-2xl font-semibold font-mono mt-0.5 ${overallColor}`}>
            {overallDelta > 0 ? '+' : ''}{overallDelta}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs text-muted-foreground">Previous → Current</p>
          <p className="text-sm font-mono text-foreground mt-0.5">
            {delta.overall_old} → {delta.overall_new}
          </p>
        </div>
      </div>

      {/* Clause delta table */}
      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/20">
              <th className="text-left px-4 py-2.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">Clause</th>
              <th className="text-left px-4 py-2.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">Score</th>
              <th className="text-left px-4 py-2.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">Change</th>
              <th className="text-left px-4 py-2.5 text-xs font-medium uppercase tracking-wider text-muted-foreground hidden sm:table-cell">Severity</th>
            </tr>
          </thead>
          <tbody>
            {(delta.clauses || []).map((c, i) => (
              <tr key={c.clause_id} className="border-b border-border last:border-0 hover:bg-muted/10 transition-colors">
                <td className="px-4 py-2.5">
                  <span className="font-mono text-xs text-muted-foreground block">{c.clause_id}</span>
                  <span className="text-sm text-foreground">{c.clause_title}</span>
                </td>
                <td className="px-4 py-2.5">
                  <ScoreTransition scoreOld={c.score_old} scoreNew={c.score_new} direction={c.direction} />
                </td>
                <td className="px-4 py-2.5">
                  <DeltaBadge delta={c.delta} direction={c.direction} />
                </td>
                <td className="px-4 py-2.5 hidden sm:table-cell">
                  {c.severity_changed ? (
                    <span className="inline-flex items-center gap-1 text-xs">
                      <span className={SEVERITY_COLOR[c.severity_old]}>{c.severity_old}</span>
                      <ArrowRight className="w-3 h-3 text-muted-foreground/50" />
                      <span className={`font-medium ${SEVERITY_COLOR[c.severity_new]}`}>{c.severity_new}</span>
                    </span>
                  ) : (
                    <span className={`text-xs ${SEVERITY_COLOR[c.severity_new]}`}>{c.severity_new}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
