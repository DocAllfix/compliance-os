/**
 * useChatStore — store globale per le conversazioni con l'analista AI.
 *
 * Sprint G.4.2: la chat ha due modalità di scope:
 *
 *   - "general"        → conversazione libera senza grounding documentale
 *                        (il backend risponde con chat_general.md, sources=[])
 *   - "<analysisId>"   → conversazione groundata su una specifica analisi
 *                        (chat_grounded.md, sources reali dalle citations)
 *
 * Lo store mantiene `Record<scope, ChatThread[]>` in memoria, sincronizzato
 * a localStorage `amisys-chat-store-v1`. Sia il drawer (overlay su
 * AppShell) sia la pagina full `/chat` leggono/scrivono da qui.
 *
 * Niente DB persistence ancora — è uno sprint backend separato (B0+).
 * Il refresh del browser preserva i thread perché localStorage sopravvive.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import type { ChatSource } from '@/lib/api';

// ── Tipi ─────────────────────────────────────────────────────────────────

export type ChatScope = string;   // "general" | analysisId

export interface ChatTurn {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  sources?: ChatSource[];
  timestamp: number;
  pending?: boolean;
  error?: boolean;
}

export interface ChatThread {
  id: string;
  scope: ChatScope;
  title: string;          // derivato dalla prima query user, fallback "New conversation"
  turns: ChatTurn[];
  createdAt: number;
  updatedAt: number;
}

interface ChatStoreState {
  // Tutti i thread di tutti gli scope, raggruppati
  threadsByScope: Record<ChatScope, ChatThread[]>;
  // CRUD
  getThreads: (scope: ChatScope) => ChatThread[];
  getThread: (threadId: string) => ChatThread | undefined;
  createThread: (scope: ChatScope) => ChatThread;
  appendTurn: (threadId: string, turn: ChatTurn) => void;
  updateTurn: (threadId: string, turnId: string, patch: Partial<ChatTurn>) => void;
  deleteThread: (threadId: string) => void;
  // Aggregati utility
  allScopes: () => ChatScope[];                // scope con almeno 1 thread
  totalThreadsCount: () => number;
}

const ChatStoreContext = createContext<ChatStoreState | null>(null);

// ── Persistenza ──────────────────────────────────────────────────────────

const STORAGE_KEY = 'amisys-chat-store-v1';

function loadFromStorage(): Record<ChatScope, ChatThread[]> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return {};
    return parsed as Record<ChatScope, ChatThread[]>;
  } catch {
    return {};
  }
}

function saveToStorage(state: Record<ChatScope, ChatThread[]>): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // localStorage può essere disabilitato o pieno — non bloccare l'app
  }
}

function genId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

// ── Provider ─────────────────────────────────────────────────────────────

export function ChatStoreProvider({ children }: { children: ReactNode }) {
  const [threadsByScope, setThreadsByScope] = useState<Record<ChatScope, ChatThread[]>>(
    () => loadFromStorage(),
  );

  // Debounce localStorage write (evita lag durante streaming turn updates)
  const writeTimerRef = useRef<number | null>(null);
  useEffect(() => {
    if (writeTimerRef.current !== null) {
      window.clearTimeout(writeTimerRef.current);
    }
    writeTimerRef.current = window.setTimeout(() => {
      saveToStorage(threadsByScope);
      writeTimerRef.current = null;
    }, 250);
    return () => {
      if (writeTimerRef.current !== null) {
        window.clearTimeout(writeTimerRef.current);
        writeTimerRef.current = null;
      }
    };
  }, [threadsByScope]);

  const getThreads = useCallback(
    (scope: ChatScope) => threadsByScope[scope] ?? [],
    [threadsByScope],
  );

  const getThread = useCallback(
    (threadId: string): ChatThread | undefined => {
      for (const scope of Object.keys(threadsByScope)) {
        const t = threadsByScope[scope].find((x) => x.id === threadId);
        if (t) return t;
      }
      return undefined;
    },
    [threadsByScope],
  );

  const createThread = useCallback((scope: ChatScope): ChatThread => {
    const now = Date.now();
    const newThread: ChatThread = {
      id: genId('thread'),
      scope,
      title: 'New conversation',
      turns: [],
      createdAt: now,
      updatedAt: now,
    };
    setThreadsByScope((prev) => ({
      ...prev,
      [scope]: [newThread, ...(prev[scope] ?? [])],
    }));
    return newThread;
  }, []);

  const appendTurn = useCallback((threadId: string, turn: ChatTurn) => {
    setThreadsByScope((prev) => {
      const next: Record<ChatScope, ChatThread[]> = {};
      for (const scope of Object.keys(prev)) {
        next[scope] = prev[scope].map((t) => {
          if (t.id !== threadId) return t;
          const turns = [...t.turns, turn];
          // Aggiorna title se è la prima query user (e il default è ancora "New conversation")
          let title = t.title;
          if (turn.role === 'user' && t.title === 'New conversation') {
            title = turn.text.slice(0, 80).trim() || 'New conversation';
          }
          return { ...t, turns, title, updatedAt: Date.now() };
        });
      }
      return next;
    });
  }, []);

  const updateTurn = useCallback(
    (threadId: string, turnId: string, patch: Partial<ChatTurn>) => {
      setThreadsByScope((prev) => {
        const next: Record<ChatScope, ChatThread[]> = {};
        for (const scope of Object.keys(prev)) {
          next[scope] = prev[scope].map((t) => {
            if (t.id !== threadId) return t;
            const turns = t.turns.map((tn) =>
              tn.id === turnId ? { ...tn, ...patch } : tn,
            );
            return { ...t, turns, updatedAt: Date.now() };
          });
        }
        return next;
      });
    },
    [],
  );

  const deleteThread = useCallback((threadId: string) => {
    setThreadsByScope((prev) => {
      const next: Record<ChatScope, ChatThread[]> = {};
      for (const scope of Object.keys(prev)) {
        const filtered = prev[scope].filter((t) => t.id !== threadId);
        if (filtered.length > 0) next[scope] = filtered;
      }
      return next;
    });
  }, []);

  const allScopes = useCallback((): ChatScope[] => {
    return Object.keys(threadsByScope).filter((s) => (threadsByScope[s] ?? []).length > 0);
  }, [threadsByScope]);

  const totalThreadsCount = useCallback((): number => {
    return Object.values(threadsByScope).reduce((acc, arr) => acc + arr.length, 0);
  }, [threadsByScope]);

  const value: ChatStoreState = useMemo(
    () => ({
      threadsByScope,
      getThreads,
      getThread,
      createThread,
      appendTurn,
      updateTurn,
      deleteThread,
      allScopes,
      totalThreadsCount,
    }),
    [threadsByScope, getThreads, getThread, createThread, appendTurn, updateTurn, deleteThread, allScopes, totalThreadsCount],
  );

  return <ChatStoreContext.Provider value={value}>{children}</ChatStoreContext.Provider>;
}

// ── Hook ────────────────────────────────────────────────────────────────

export function useChatStore(): ChatStoreState {
  const ctx = useContext(ChatStoreContext);
  if (!ctx) throw new Error('useChatStore must be used inside <ChatStoreProvider>');
  return ctx;
}

// ── Drawer state (separato) ────────────────────────────────────────────

interface ChatDrawerState {
  isOpen: boolean;
  scope: ChatScope | null;       // analysisId quando contestuale, null quando chiuso
  open: (scope: ChatScope) => void;
  close: () => void;
}

const ChatDrawerContext = createContext<ChatDrawerState | null>(null);

export function ChatDrawerProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const [scope, setScope] = useState<ChatScope | null>(null);

  const open = useCallback((s: ChatScope) => {
    setScope(s);
    setIsOpen(true);
  }, []);

  const close = useCallback(() => {
    setIsOpen(false);
    // Lasciamo scope settato per evitare flash di contenuto vuoto durante l'animazione di chiusura
  }, []);

  // Escape chiude il drawer
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, close]);

  const value: ChatDrawerState = useMemo(
    () => ({ isOpen, scope, open, close }),
    [isOpen, scope, open, close],
  );

  return <ChatDrawerContext.Provider value={value}>{children}</ChatDrawerContext.Provider>;
}

export function useChatDrawer(): ChatDrawerState {
  const ctx = useContext(ChatDrawerContext);
  if (!ctx) throw new Error('useChatDrawer must be used inside <ChatDrawerProvider>');
  return ctx;
}
