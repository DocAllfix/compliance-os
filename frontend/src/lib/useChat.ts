/**
 * In-process chat state hook.
 *
 * Holds an ordered list of turns for a single conversation grounded on
 * an analysis_id. No DB persistence — refresh wipes the conversation,
 * which is acceptable for the MVP (a future backend sprint can add
 * server-side chat persistence keyed on analysis_id + conversation_id).
 *
 * Errors are surfaced as assistant turns with an `error: true` flag so
 * the UI can render them inline without toast plumbing.
 */
import { useCallback, useRef, useState } from 'react';
import { compliance, type ChatSource, ApiError } from './api';

export interface ChatTurn {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  sources?: ChatSource[];
  timestamp: number;
  pending?: boolean;   // true while awaiting LLM response
  error?: boolean;     // true if the request failed
}

export interface UseChatResult {
  turns: ChatTurn[];
  isSending: boolean;
  sendMessage: (query: string) => Promise<void>;
  clearConversation: () => void;
  error: string | null;
}

function randomId(): string {
  // Lightweight unique-ish id; we don't need cryptographic strength here.
  return `t_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export function useChat(analysisId: string | undefined): UseChatResult {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Track pending assistant turn id so we can replace it on resolution.
  const pendingIdRef = useRef<string | null>(null);

  const sendMessage = useCallback(
    async (query: string) => {
      const trimmed = query.trim();
      if (!trimmed || !analysisId) return;

      // Optimistic user turn + pending assistant placeholder
      const userTurn: ChatTurn = {
        id: randomId(),
        role: 'user',
        text: trimmed,
        timestamp: Date.now(),
      };
      const placeholder: ChatTurn = {
        id: randomId(),
        role: 'assistant',
        text: '',
        timestamp: Date.now(),
        pending: true,
      };
      pendingIdRef.current = placeholder.id;

      setTurns((prev) => [...prev, userTurn, placeholder]);
      setIsSending(true);
      setError(null);

      try {
        const resp = await compliance.chat({
          analysis_id: analysisId,
          query: trimmed,
        });
        setTurns((prev) =>
          prev.map((t) =>
            t.id === placeholder.id
              ? {
                  ...t,
                  pending: false,
                  text: resp.response,
                  sources: resp.sources,
                }
              : t,
          ),
        );
      } catch (e) {
        const msg =
          e instanceof ApiError
            ? e.message
            : e instanceof Error
            ? e.message
            : 'Unknown error';
        setError(msg);
        setTurns((prev) =>
          prev.map((t) =>
            t.id === placeholder.id
              ? {
                  ...t,
                  pending: false,
                  error: true,
                  text: `This question could not be answered: ${msg}`,
                }
              : t,
          ),
        );
      } finally {
        setIsSending(false);
        pendingIdRef.current = null;
      }
    },
    [analysisId],
  );

  const clearConversation = useCallback(() => {
    setTurns([]);
    setError(null);
    pendingIdRef.current = null;
  }, []);

  return { turns, isSending, sendMessage, clearConversation, error };
}
