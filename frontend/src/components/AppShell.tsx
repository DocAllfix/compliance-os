import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';

/**
 * AppShell — sidebar + outlet + context-aware "Ask the analyst" FAB.
 *
 * When the user is on /analyses/:id or /analyses/:id/plan, the FAB navigates
 * to the chat scoped to that specific analysis. Otherwise it falls back to
 * /chat (which renders an empty state inviting the user to pick an analysis).
 */
export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();

  // Match /analyses/<id> and /analyses/<id>/plan but NOT /analyses/<id>/chat
  // (already on the chat page) or just /analyses (list redirect).
  const match = location.pathname.match(/^\/analyses\/([^/]+)(?:\/plan)?$/);
  const analysisId = match?.[1];
  const fabTarget = analysisId ? `/analyses/${analysisId}/chat` : '/chat';

  return (
    <div className="shell">
      <Sidebar />
      <main className="main">
        <Outlet />
      </main>
      <button className="ask-ai-fab" onClick={() => navigate(fabTarget)}>
        <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
          <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
        </svg>
        Ask the analyst
      </button>
    </div>
  );
}
