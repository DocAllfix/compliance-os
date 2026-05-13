/**
 * ChatDrawer — overlay sliding-from-right per chat contestuale.
 *
 * Sprint G.4.4: si apre quando l'utente è su Results e clicca "Ask the
 * analyst" (FAB AppShell o pulsante header Results). La pagina sotto
 * resta visibile, non c'è navigazione. Escape chiude.
 *
 * Width 520px su desktop, full-width su mobile <768px.
 * Backdrop solido (no glassmorphism, vedi DESIGN.md hard-ban).
 *
 * Contiene:
 *  - header con close button + "Open in full page" link
 *  - mini-sidebar threads di questo scope + "New conversation"
 *  - <ChatPanel scope={drawer.scope} variant="drawer" />
 */
import { Link, useNavigate } from 'react-router-dom';
import { useChatDrawer, useChatStore } from '@/lib/useChatStore';
import { useChat } from '@/lib/useChat';
import { ChatPanel } from '@/components/ChatPanel';

function CloseIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  );
}

function ExpandIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="15 3 21 3 21 9" />
      <polyline points="9 21 3 21 3 15" />
      <line x1="21" y1="3" x2="14" y2="10" />
      <line x1="3" y1="21" x2="10" y2="14" />
    </svg>
  );
}

export function ChatDrawer() {
  const { isOpen, scope, close } = useChatDrawer();
  const store = useChatStore();
  const navigate = useNavigate();
  // useChat va chiamato sempre per non rompere rules-of-hooks; passiamo
  // una stringa stabile anche quando il drawer è chiuso (allora scope=null
  // → usiamo "general" come placeholder neutro, ma il componente non viene
  // renderizzato).
  const effectiveScope = scope ?? 'general';
  const { newConversation, selectThread, threadId: activeThreadId } = useChat(effectiveScope);

  if (!isOpen || scope === null) return null;

  const threads = store.getThreads(scope);

  const handleOpenFull = () => {
    close();
    // /chat?analysis=<id> selezionerà automaticamente lo scope nella full page
    if (scope === 'general') {
      navigate('/chat');
    } else {
      navigate(`/chat?analysis=${encodeURIComponent(scope)}`);
    }
  };

  return (
    <>
      <div className="chat-drawer-backdrop" onClick={close} aria-hidden="true" />
      <aside className="chat-drawer" role="dialog" aria-label="Ask the analyst">
        <header className="chat-drawer-header">
          <div className="chat-drawer-title">
            <span className="eyebrow">Ask the analyst</span>
            <div className="chat-drawer-scope">
              {scope === 'general' ? 'General conversation' : `Grounded on this analysis`}
            </div>
          </div>
          <div className="chat-drawer-actions">
            <button
              type="button"
              className="icon-btn"
              onClick={handleOpenFull}
              title="Open in full page"
              aria-label="Open in full page"
            >
              <ExpandIcon />
            </button>
            <button
              type="button"
              className="icon-btn"
              onClick={close}
              title="Close (Esc)"
              aria-label="Close"
            >
              <CloseIcon />
            </button>
          </div>
        </header>

        <div className="chat-drawer-threads">
          <button type="button" className="thread-new-btn-mini" onClick={newConversation}>
            <PlusIcon />
            New conversation
          </button>
          {threads.length > 0 && (
            <div className="chat-drawer-threads-list">
              {threads.slice(0, 5).map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className={`thread-item-mini${t.id === activeThreadId ? ' active' : ''}`}
                  onClick={() => selectThread(t.id)}
                >
                  <span className="thread-item-mini-q">{t.title}</span>
                  <span className="thread-item-mini-meta">
                    {t.turns.length} message{t.turns.length === 1 ? '' : 's'}
                  </span>
                </button>
              ))}
              {threads.length > 5 && (
                <Link
                  to={scope === 'general' ? '/chat' : `/chat?analysis=${encodeURIComponent(scope)}`}
                  className="thread-item-mini-more"
                  onClick={close}
                >
                  + {threads.length - 5} more · open full page
                </Link>
              )}
            </div>
          )}
        </div>

        <ChatPanel scope={scope} variant="drawer" />
      </aside>
    </>
  );
}
