/**
 * useChat — hook che gestisce una conversazione attiva.
 *
 * Sprint G.4 refactor: prima Sprint F2 il hook teneva lo stato in `useState`
 * locale, ora delega tutto al `useChatStore` globale così drawer e pagina
 * full possono condividere i threads in localStorage. L'API esterna resta
 * compatibile per minimizzare il refactor di chi consumava `useChat`.
 *
 * Modalità scope:
 *   - "general"       → POST /api/compliance/chat senza analysis_id
 *   - "<analysisId>"  → POST /api/compliance/chat con analysis_id reale
 */
import { useCallback, useRef, useState } from 'react';
import { compliance, ApiError } from './api';
import { useChatStore, type ChatTurn, type ChatScope } from './useChatStore';

export type { ChatTurn };

export interface UseChatResult {
  threadId: string | null;
  turns: ChatTurn[];
  isSending: boolean;
  sendMessage: (query: string) => Promise<void>;
  newConversation: () => void;
  selectThread: (threadId: string) => void;
  error: string | null;
}

function genTurnId(): string {
  return `turn_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export function useChat(scope: ChatScope): UseChatResult {
  const store = useChatStore();
  const [threadId, setThreadId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pendingIdRef = useRef<string | null>(null);

  const threads = store.getThreads(scope);
  const activeThread = threadId ? store.getThread(threadId) : threads[0];
  const turns = activeThread?.turns ?? [];

  const newConversation = useCallback(() => {
    const t = store.createThread(scope);
    setThreadId(t.id);
    setError(null);
  }, [store, scope]);

  const selectThread = useCallback((tid: string) => {
    setThreadId(tid);
    setError(null);
  }, []);

  const sendMessage = useCallback(
    async (query: string) => {
      const trimmed = query.trim();
      if (!trimmed) return;

      // Se non c'è un thread attivo per questo scope, ne creiamo uno on-the-fly
      let activeTid = threadId;
      if (!activeTid || !store.getThread(activeTid)) {
        const t = store.createThread(scope);
        activeTid = t.id;
        setThreadId(activeTid);
      }

      // Turn user ottimistico
      const userTurn: ChatTurn = {
        id: genTurnId(),
        role: 'user',
        text: trimmed,
        timestamp: Date.now(),
      };
      // Placeholder assistant pending
      const placeholderId = genTurnId();
      const placeholder: ChatTurn = {
        id: placeholderId,
        role: 'assistant',
        text: '',
        timestamp: Date.now(),
        pending: true,
      };
      pendingIdRef.current = placeholderId;

      store.appendTurn(activeTid, userTurn);
      store.appendTurn(activeTid, placeholder);
      setIsSending(true);
      setError(null);

      try {
        const reqBody = scope === 'general'
          ? { query: trimmed, analysis_id: null }
          : { query: trimmed, analysis_id: scope };
        const resp = await compliance.chat(reqBody as Parameters<typeof compliance.chat>[0]);
        store.updateTurn(activeTid, placeholderId, {
          pending: false,
          text: resp.response,
          sources: resp.sources,
        });
      } catch (e) {
        const msg =
          e instanceof ApiError
            ? e.message
            : e instanceof Error
            ? e.message
            : 'Unknown error';
        setError(msg);
        store.updateTurn(activeTid, placeholderId, {
          pending: false,
          error: true,
          text: `This question could not be answered: ${msg}`,
        });
      } finally {
        setIsSending(false);
        pendingIdRef.current = null;
      }
    },
    [scope, store, threadId],
  );

  return {
    threadId: activeThread?.id ?? null,
    turns,
    isSending,
    sendMessage,
    newConversation,
    selectThread,
    error,
  };
}
