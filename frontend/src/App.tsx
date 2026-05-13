import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from '@/components/AppShell';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { Dashboard } from '@/pages/Dashboard';
import { NewAnalysis } from '@/pages/NewAnalysis';
import { Results } from '@/pages/Results';
import { Plan } from '@/pages/Plan';
import { Chat } from '@/pages/Chat';
import { Login } from '@/pages/Login';
import { useTheme } from '@/lib/theme';

function App() {
  // Theme provider effect
  useTheme();
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<Login />} />

      {/* Chat — protected, own 3-column layout */}
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
            <Chat />
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
