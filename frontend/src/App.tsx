import { Navigate, Route, Routes, useParams } from 'react-router-dom';
import { AppShell } from '@/components/AppShell';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { Dashboard } from '@/pages/Dashboard';
import { NewAnalysis } from '@/pages/NewAnalysis';
import { Results } from '@/pages/Results';
import { Plan } from '@/pages/Plan';
import { Chat } from '@/pages/Chat';
import { Login } from '@/pages/Login';
import { useTheme } from '@/lib/theme';

/** Sprint G.4.7: redirect legacy `/analyses/:id/chat` → `/chat?analysis=:id`,
 *  preservando il parametro così l'utente atterra sullo scope giusto. */
function LegacyAnalysisChatRedirect() {
  const { id } = useParams();
  return <Navigate to={`/chat?analysis=${encodeURIComponent(id ?? '')}`} replace />;
}

function App() {
  // Theme provider effect
  useTheme();
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<Login />} />

      {/* Chat full page — protected, own 3-column layout.
          Sprint G.4: la chat scoped a una specifica analisi è ora un drawer
          overlay (vedi ChatDrawer in AppShell), non più una route separata.
          Per chi atterra sul vecchio link /analyses/:id/chat redirigiamo
          alla full page con query param ?analysis=:id. */}
      <Route
        path="/chat"
        element={
          <ProtectedRoute>
            <Chat />
          </ProtectedRoute>
        }
      />
      <Route
        path="/analyses/:id/chat"
        element={
          <ProtectedRoute>
            <LegacyAnalysisChatRedirect />
          </ProtectedRoute>
        }
      />

      {/* Everything else — protected, AppShell with sidebar */}
      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/new-analysis" element={<NewAnalysis />} />
        <Route path="/analyses" element={<Navigate to="/dashboard" replace />} />
        <Route path="/analyses/:id" element={<Results />} />
        <Route path="/analyses/:id/plan" element={<Plan />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}

export default App;
