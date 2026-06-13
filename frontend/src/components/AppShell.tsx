import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { ChatDrawer } from './ChatDrawer';
import { NotificationsBell } from './NotificationsBell';
import { useChatDrawer } from '@/lib/useChatStore';

/**
 * AppShell — sidebar + outlet + context-aware "Ask the analyst" FAB + ChatDrawer.
 *
 * Sprint G.4.4: il FAB ora apre il drawer overlay quando l'utente è su
 * /analyses/:id (o /plan), invece di navigare a un'altra pagina. Per
 * la chat libera senza scope (sidebar link → /chat) c'è una route a sé.
 */
export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const { open: openDrawer } = useChatDrawer();

  // Match /analyses/<id> e /analyses/<id>/plan ma non /chat
  const match = location.pathname.match(/^\/analyses\/([^/]+)(?:\/plan)?$/);
  const analysisId = match?.[1];

  const handleFabClick = () => {
    if (analysisId) {
      openDrawer(analysisId);
    } else {
      // Niente analisi nel contesto corrente → vai alla pagina chat libera
      navigate('/chat');
    }
  };

  return (
    <div className="shell">
      <Sidebar />
      <main className="main">
        <NotificationsBell />
        <Outlet />
      </main>
      <button className="ask-ai-fab" onClick={handleFabClick}>
        <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
          <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
        </svg>
        Ask the analyst
      </button>
      <ChatDrawer />
    </div>
  );
}
