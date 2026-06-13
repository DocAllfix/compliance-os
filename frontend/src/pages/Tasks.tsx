/**
 * Tasks — Fase F (PRD §1.3.4).
 *
 * Waterfall di task con stato RAG (red/amber/green), composto a lettura da
 * nonconformità aperte, scadenze documenti e task manuali. Colonne per stato
 * (la semantica RAG usa i token severity). Completare un task da NC chiude la
 * nonconformità collegata (visibile sul Plan).
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { tasks as tasksApi, type Task, type Rag } from '@/lib/api';

const COLUMNS: { rag: Rag; label: string; hint: string }[] = [
  { rag: 'red', label: 'Overdue', hint: 'Past due date' },
  { rag: 'amber', label: 'Due soon', hint: 'Within 30 days' },
  { rag: 'green', label: 'On track', hint: 'More than 30 days out' },
];

function fmtDate(s: string | null): string {
  if (!s) return 'No due date';
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function ragDot(rag: Rag): string {
  if (rag === 'red') return 'major';
  if (rag === 'amber') return 'minor';
  return 'conf';
}

export function Tasks() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ['tasks'], queryFn: () => tasksApi.list() });
  const [title, setTitle] = useState('');
  const [due, setDue] = useState('');
  const [busy, setBusy] = useState(false);

  const all = data?.tasks ?? [];
  const refresh = () => qc.invalidateQueries({ queryKey: ['tasks'] });

  const complete = async (t: Task) => { await tasksApi.setDone(t.task_key, !t.done); refresh(); };
  const snooze = async (t: Task) => {
    const until = window.prompt('Snooze until (YYYY-MM-DD)');
    if (!until) return;
    await tasksApi.snooze(t.task_key, until); refresh();
  };
  const addManual = async () => {
    if (!title.trim()) return;
    setBusy(true);
    try { await tasksApi.addManual(title.trim(), due || null); setTitle(''); setDue(''); refresh(); }
    finally { setBusy(false); }
  };

  const TaskCard = ({ t }: { t: Task }) => (
    <article className={`task-card${t.done ? ' done' : ''}`}>
      <div className="task-card-head">
        <span className={`dot ${ragDot(t.rag)}`} />
        <span className="task-source">{t.source === 'nonconformity' ? 'Nonconformity' : t.source === 'expiry' ? 'Document expiry' : 'Manual'}</span>
        {t.severity && <span className={`badge badge-${t.severity.toLowerCase()}`}>{t.severity.charAt(0) + t.severity.slice(1).toLowerCase()}</span>}
      </div>
      <Link to={t.link} className="task-title">{t.title}</Link>
      <div className="task-meta">{fmtDate(t.due_date)}</div>
      <div className="task-actions">
        <button className="btn btn-link" onClick={() => complete(t)}>{t.done ? 'Reopen' : 'Complete'}</button>
        {!t.done && <button className="btn btn-link" onClick={() => snooze(t)}>Snooze</button>}
      </div>
    </article>
  );

  const done = all.filter((t) => t.rag === 'done');
  const snoozed = all.filter((t) => t.rag === 'snoozed');

  return (
    <div className="main-wide-inner">
      <header className="compact-header">
        <div>
          <div className="eyebrow">Action tracking</div>
          <h1 className="page-title">Tasks</h1>
          <div className="page-meta">
            Open nonconformities, document renewals and your own to-dos, graded by urgency.
          </div>
        </div>
      </header>

      <div className="task-add">
        <input className="input" placeholder="Add a task…" value={title}
          onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addManual()} />
        <input className="input" type="date" value={due} onChange={(e) => setDue(e.target.value)} style={{ maxWidth: 170 }} />
        <button className="btn btn-accent" onClick={addManual} disabled={busy || !title.trim()}>Add</button>
      </div>

      {isLoading ? (
        <p className="dms-hint">Loading…</p>
      ) : (
        <>
          <div className="task-board">
            {COLUMNS.map((col) => {
              const items = all.filter((t) => t.rag === col.rag);
              return (
                <div key={col.rag} className="task-col">
                  <div className="task-col-head">
                    <span className={`dot ${ragDot(col.rag)}`} />
                    {col.label}
                    <span className="task-col-count">{items.length}</span>
                  </div>
                  <div className="task-col-hint">{col.hint}</div>
                  {items.length === 0 ? (
                    <p className="task-col-empty">Nothing here.</p>
                  ) : items.map((t) => <TaskCard key={t.task_key} t={t} />)}
                </div>
              );
            })}
          </div>

          {(snoozed.length > 0 || done.length > 0) && (
            <div className="task-secondary">
              {snoozed.length > 0 && (
                <details>
                  <summary>Snoozed ({snoozed.length})</summary>
                  {snoozed.map((t) => <TaskCard key={t.task_key} t={t} />)}
                </details>
              )}
              {done.length > 0 && (
                <details>
                  <summary>Completed ({done.length})</summary>
                  {done.map((t) => <TaskCard key={t.task_key} t={t} />)}
                </details>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
