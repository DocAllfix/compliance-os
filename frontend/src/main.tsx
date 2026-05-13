import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/lib/auth';
import { ChatStoreProvider, ChatDrawerProvider } from '@/lib/useChatStore';
import { queryClient } from '@/lib/query';
import App from './App';
import './index.css';
import './pages.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <ChatStoreProvider>
            <ChatDrawerProvider>
              <App />
            </ChatDrawerProvider>
          </ChatStoreProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
