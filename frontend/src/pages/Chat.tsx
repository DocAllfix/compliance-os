/**
 * Chat full page — `/chat` route.
 *
 * Sprint G.4.5: layout 3-column con threads list raggruppata per scope.
 * Sidebar a sinistra mostra "General" (chat libera) + un gruppo per ogni
 * analisi con almeno una conversazione. L'utente può:
 *  - cliccare "New conversation" → crea un thread sul scope corrente
 *  - cliccare un thread esistente per riprenderlo
 *  - switchare scope (general / specifica analisi) dalla sidebar
 *
 * Quando la URL è `?analysis=<id>`, lo scope iniziale è quell'analisi.
 * Altrimenti default a "general".
 */
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useTheme } from '@/lib/theme';
import { useChatStore, type ChatScope } from '@/lib/useChatStore';
import { useChat } from '@/lib/useChat';
import { useAnalyses } from '@/lib/hooks';
import { ChatPanel } from '@/components/ChatPanel';

function PlusIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function ChatBubbleIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
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

export function Chat() {
  const [searchParams] = useSearchParams();
  const initialScope: ChatScope = searchParams.get('analysis') ?? 'all';
  const [scope, setScope] = useState<ChatScope>(initialScope);
  const { toggleTheme } = useTheme();
  const navigate = useNavigate();
  const store = useChatStore();
  const { newConversation, selectThread, threadId: activeThreadId } = useChat(scope);
  const analysesQuery = useAnalyses();

  // Quando cambia ?analysis= nella URL (es. arrivo dal drawer), aggiorna lo scope
  useEffect(() => {
    const want = searchParams.get('analysis');
    if (want && want !== scope) {
      setScope(want);
    }
    if (!want && scope !== 'general' && scope !== 'all' && !store.getThreads(scope).length) {
      // se l'utente naviga via senza ?analysis e lo scope corrente non ha thread, default
      setScope('all');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const allScopes = store.allScopes();
  const generalThreads = store.getThreads('general');
  const accountThreads = store.getThreads('all');
  // Per ogni analysisId con threads, prepariamo il company name dalla cache analisi
  const analysisIdsWithThreads = allScopes.filter((s) => s !== 'general' && s !== 'all');
  const analyses = analysesQuery.data ?? [];

  const companyOf = useMemo(() => {
    const map = new Map<string, string>();
    for (const a of analyses) map.set(a.id, a.company);
    return map;
  }, [analyses]);

  const currentScopeLabel =
    scope === 'all'
      ? 'All my data'
      : scope === 'general'
      ? 'General ISO advisor'
      : companyOf.get(scope) ?? `Analysis ${scope.slice(-8)}`;

  const activeThreadTitle = useMemo(() => {
    if (!activeThreadId) return null;
    const t = store.getThread(activeThreadId);
    return t?.title ?? null;
  }, [activeThreadId, store]);

  const handleSelectScope = (s: ChatScope) => {
    setScope(s);
    // Aggiorna URL per riflettere lo scope (deep-linkable)
    if (s === 'general') {
      navigate('/chat', { replace: true });
    } else {
      navigate(`/chat?analysis=${encodeURIComponent(s)}`, { replace: true });
    }
  };

  return (
    <div className="chat-shell">
      {/* Threads sidebar */}
      <aside className="thread-list">
        <div className="thread-list-header">
          <div className="thread-list-eyebrow">
            <Link
              to="/dashboard"
              style={{
                color: 'var(--text-tertiary)',
                textDecoration: 'none',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
              }}
            >
              <svg
                width="11"
                height="11"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <polyline points="15 18 9 12 15 6" />
              </svg>
              Back to dashboard
            </Link>
          </div>
          <div className="thread-list-title">Ask the analyst</div>
        </div>

        {/* New conversation button */}
        <button type="button" className="thread-new-btn" onClick={newConversation}>
          <PlusIcon />
          New {scope === 'general' ? 'general ' : ''}conversation
        </button>

        {/* Group: All my data (analista onnisciente) */}
        <div className="thread-section-label">
          <FileIcon />
          Your data
        </div>
        <button
          type="button"
          className={`scope-pill${scope === 'all' ? ' active' : ''}`}
          onClick={() => handleSelectScope('all')}
          title="The analyst sees every analysis and every analysed document"
        >
          <span className="scope-pill-name">All my data</span>
          <span className="scope-pill-count">{accountThreads.length}</span>
        </button>
        {scope === 'all' &&
          accountThreads.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`thread-item${t.id === activeThreadId ? ' active' : ''}`}
              onClick={() => selectThread(t.id)}
            >
              <div className="thread-item-q">{t.title}</div>
              <div className="thread-item-meta">
                <span>{t.turns.length} message{t.turns.length === 1 ? '' : 's'}</span>
              </div>
            </button>
          ))}

        {/* Group: General */}
        <div className="thread-section-label">
          <ChatBubbleIcon />
          General
        </div>
        <button
          type="button"
          className={`scope-pill${scope === 'general' ? ' active' : ''}`}
          onClick={() => handleSelectScope('general')}
        >
          <span className="scope-pill-name">General ISO advisor</span>
          <span className="scope-pill-count">{generalThreads.length}</span>
        </button>
        {scope === 'general' &&
          generalThreads.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`thread-item${t.id === activeThreadId ? ' active' : ''}`}
              onClick={() => selectThread(t.id)}
            >
              <div className="thread-item-q">{t.title}</div>
              <div className="thread-item-meta">
                <span>{t.turns.length} message{t.turns.length === 1 ? '' : 's'}</span>
              </div>
            </button>
          ))}

        {/* Group: per-analisi */}
        {analysisIdsWithThreads.length > 0 && (
          <div className="thread-section-label">
            <FileIcon />
            From analyses
          </div>
        )}
        {analysisIdsWithThreads.map((aid) => {
          const aThreads = store.getThreads(aid);
          const company = companyOf.get(aid) ?? `Analysis ${aid.slice(-8)}`;
          return (
            <div key={aid}>
              <button
                type="button"
                className={`scope-pill${scope === aid ? ' active' : ''}`}
                onClick={() => handleSelectScope(aid)}
                title={aid}
              >
                <span className="scope-pill-name">{company}</span>
                <span className="scope-pill-count">{aThreads.length}</span>
              </button>
              {scope === aid &&
                aThreads.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={`thread-item${t.id === activeThreadId ? ' active' : ''}`}
                    onClick={() => selectThread(t.id)}
                  >
                    <div className="thread-item-q">{t.title}</div>
                    <div className="thread-item-meta">
                      <span>
                        {t.turns.length} message{t.turns.length === 1 ? '' : 's'}
                      </span>
                    </div>
                  </button>
                ))}
            </div>
          );
        })}

        {/* Theme toggle in footer */}
        <div
          style={{
            marginTop: 'auto',
            padding: '14px 16px',
            borderTop: '1px solid var(--border-subtle)',
            background: 'var(--bg-elevated)',
          }}
        >
          <button
            type="button"
            className="theme-toggle"
            style={{ position: 'relative', top: 'auto', right: 'auto' }}
            aria-label="Toggle theme"
            onClick={toggleTheme}
          >
            <svg
              className="icon icon-moon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
            </svg>
            <svg
              className="icon icon-sun"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2" />
              <path d="M12 20v2" />
              <path d="m4.93 4.93 1.41 1.41" />
              <path d="m17.66 17.66 1.41 1.41" />
              <path d="M2 12h2" />
              <path d="M20 12h2" />
              <path d="m4.93 19.07 1.41-1.41" />
              <path d="m17.66 6.34 1.41-1.41" />
            </svg>
          </button>
        </div>
      </aside>

      {/* Conversation */}
      <section className="conversation">
        <header className="conv-header">
          <div>
            <div className="conv-eyebrow">{currentScopeLabel}</div>
            <div className="conv-title">
              {activeThreadTitle ?? 'Start a new conversation'}
            </div>
          </div>
          {scope !== 'general' && (
            <Link to={`/analyses/${scope}`} className="btn btn-link" title="Open the analysis page">
              <FileIcon />
              Open analysis
            </Link>
          )}
        </header>
        <ChatPanel scope={scope} variant="page" />
      </section>
    </div>
  );
}
