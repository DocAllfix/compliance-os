/**
 * NotificationsBell — Fase E (PRD §1.3.3).
 *
 * Campanella fissa in alto a destra del chrome: badge con il conteggio non
 * lette (polling), dropdown con l'elenco, mark-read singolo e "mark all".
 * Le notifiche di scadenza linkano a /documents.
 */
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { notifications, type AppNotification } from '@/lib/api';

function sevDot(sev: string | null): string {
  if (sev === 'MAJOR') return 'major';
  if (sev === 'MINOR') return 'minor';
  if (sev === 'OBSERVATION') return 'obs';
  return 'conf';
}

function ago(iso: string): string {
  const d = new Date(iso + (iso.endsWith('Z') ? '' : 'Z'));
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (isNaN(mins)) return '';
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

export function NotificationsBell() {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const ref = useRef<HTMLDivElement>(null);

  const countQuery = useQuery({
    queryKey: ['notif-unread'],
    queryFn: () => notifications.unreadCount(),
    refetchInterval: 60000,
    refetchOnWindowFocus: true,
  });
  const listQuery = useQuery({
    queryKey: ['notif-list'],
    queryFn: () => notifications.list(),
    enabled: open,
  });

  const unread = countQuery.data?.unread ?? 0;
  const items = listQuery.data?.notifications ?? [];

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['notif-unread'] });
    qc.invalidateQueries({ queryKey: ['notif-list'] });
  };

  const onItem = async (n: AppNotification) => {
    if (!n.read_at) { await notifications.markRead(n.id); refresh(); }
    if (n.link) { setOpen(false); navigate(n.link); }
  };

  const markAll = async () => { await notifications.markAllRead(); refresh(); };

  return (
    <div className="notif-bell" ref={ref}>
      <button className="notif-trigger" onClick={() => setOpen((o) => !o)} aria-label="Notifications">
        <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unread > 0 && <span className="notif-badge">{unread > 9 ? '9+' : unread}</span>}
      </button>

      {open && (
        <div className="notif-panel">
          <div className="notif-panel-head">
            <span>Notifications</span>
            {unread > 0 && <button className="btn btn-link" onClick={markAll}>Mark all read</button>}
          </div>
          <div className="notif-list">
            {listQuery.isLoading ? (
              <p className="notif-empty">Loading…</p>
            ) : items.length === 0 ? (
              <p className="notif-empty">No notifications. Expiring documents will show up here.</p>
            ) : (
              items.map((n) => (
                <button
                  key={n.id}
                  className={`notif-item${n.read_at ? '' : ' unread'}`}
                  onClick={() => onItem(n)}
                >
                  <span className={`dot ${sevDot(n.severity)}`} />
                  <span className="notif-item-body">
                    <span className="notif-item-title">{n.title}</span>
                    <span className="notif-item-meta">{ago(n.created_at)}</span>
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
