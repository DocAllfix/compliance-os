// @ts-nocheck
import { Toaster } from "@/components/ui/toaster"
import { Toaster as SonnerToaster } from "@/components/ui/sonner"
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClientInstance } from '@/lib/query-client'
import { BrowserRouter as Router, Route, Routes, Navigate } from 'react-router-dom';
import PageNotFound from './lib/PageNotFound';
import { AuthProvider, useAuth } from '@/lib/AuthContext';
import { ThemeProvider } from '@/lib/ThemeContext';

// Layout
import AppLayout from '@/components/layout/AppLayout';

// Pages
import Login from '@/pages/Login';
import AdminPanel from '@/pages/AdminPanel';
import AdminErrorLog from '@/pages/AdminErrorLog';
import ComplianceDashboard from '@/pages/ComplianceDashboard';
import NewAnalysis from '@/pages/NewAnalysis';
import AnalysisDetail from '@/pages/AnalysisDetail';
import AnalysisHistory from '@/pages/AnalysisHistory';

const AppRoutes = () => {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 rounded-lg brand-gradient flex items-center justify-center">
            <span className="text-white font-bold text-lg">C</span>
          </div>
          <div className="w-8 h-8 border-2 border-muted border-t-primary rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <Routes>
        <Route path="*" element={<Login />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard"       element={<ComplianceDashboard />} />
        <Route path="new-analysis"    element={<NewAnalysis />} />
        <Route path="analysis/:id"    element={<AnalysisDetail />} />
        <Route path="history"         element={<AnalysisHistory />} />
        <Route path="admin"           element={<AdminPanel />} />
        <Route path="admin/errori"    element={<AdminErrorLog />} />
        <Route path="*"               element={<PageNotFound />} />
      </Route>
    </Routes>
  );
};

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <QueryClientProvider client={queryClientInstance}>
          <Router>
            <AppRoutes />
          </Router>
          <Toaster />
          <SonnerToaster />
        </QueryClientProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
