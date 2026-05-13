/**
 * ChatPanel — riusabile, presentation-only.
 *
 * Sprint G.4.3: contiene conversation thread + composer + sources. Riceve
 * `scope` (analysisId | "general") e usa `useChat(scope)` per fetch.
 * NON contiene la sidebar dei threads — quella è esterna (drawer ha la
 * propria mini-sidebar, la pagina /chat ha la full sidebar).
 */
import { useEffect, useRef, useState } from 'react';
import { useChat, type ChatTurn } from '@/lib/useChat';
import { useAuth } from '@/lib/auth';
import type { ChatSource } from '@/lib/api';

const SUGGESTIONS_ANALYSIS = [
  'Which documents are expired?',
  'What does §6.1.3 require exactly?',
  'Which clause is most critical here?',
  'Summarise the legal register gap in plain English',
];

const SUGGESTIONS_GENERAL = [
  'What does ISO 9001 clause 7.5 require?',
  'Explain the difference between Major and Minor non-conformity',
  'What evidence typically demonstrates §8.4 compliance?',
  'How is a single point of failure (SPoF) identified?',
];

const REFUSAL_PATTERN = /^no evidence in this audit/i;

function FileIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

function InfoIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="16" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12.01" y2="8" />
    </svg>
  );
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

function userInitials(name: string | undefined): string {
  if (!name) return '··';
  return (
    name
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((w) => w[0]?.toUpperCase() ?? '')
      .join('') || '··'
  );
}

function SourceChip({ src, index }: { src: ChatSource; index: number }) {
  return (
    <span className="source-chip" title={src.excerpt}>
      <span className="source-chip-num">{index + 1}</span>
      <span className="source-chip-info">
        <FileIcon />
        {src.file_name}
        {src.iso_clause_primary && <span className="page"> · {src.iso_clause_primary}</span>}
      </span>
    </span>
  );
}

function Turn({ turn, userName }: { turn: ChatTurn; userName: string | undefined }) {
  const isRefusal = turn.role === 'assistant' && REFUSAL_PATTERN.test(turn.text);

  if (turn.role === 'user') {
    return (
      <div className="msg user">
        <div className="msg-avatar">{userInitials(userName)}</div>
        <div className="msg-content">
          <div className="msg-author">
            <b>{userName ?? 'You'}</b>
            <span className="time">{formatTime(turn.timestamp)}</span>
          </div>
          <div className="msg-text">{turn.text}</div>
        </div>
      </div>
    );
  }

  return (
    <div className={`msg ai${turn.error ? ' msg-error' : ''}${isRefusal ? ' msg-refusal' : ''}`}>
      <div className="msg-avatar">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
          <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
        </svg>
      </div>
      <div className="msg-content">
        <div className="msg-author">
          <b>The analyst</b>
          <span className="time">{formatTime(turn.timestamp)}</span>
        </div>
        {turn.pending ? (
          <div className="msg-text msg-thinking">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
            <span className="msg-thinking-label">Thinking…</span>
          </div>
        ) : (
          <div className="msg-text">
            {isRefusal && (
              <div className="refusal-banner">
                <InfoIcon />
                <span>No evidence in this audit supports an answer to that question.</span>
              </div>
            )}
            {!isRefusal &&
              turn.text.split(/\n\s*\n+/).map((p, i) => <p key={i}>{p}</p>)}
            {turn.sources && turn.sources.length > 0 && (
              <div className="sources-block">
                <div className="sources-label">Sources</div>
                <div className="sources-list">
                  {turn.sources.map((s, i) => (
                    <SourceChip key={s.evidence_id || i} src={s} index={i} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

interface Props {
  scope: string;            // analysisId | "general"
  variant?: 'page' | 'drawer';
  emptyHint?: string;       // testo opzionale mostrato quando 0 turni
}

export function ChatPanel({ scope, variant = 'page', emptyHint }: Props) {
  const { user } = useAuth();
  const { turns, isSending, sendMessage } = useChat(scope);
  const [composer, setComposer] = useState('');
  const threadEndRef = useRef<HTMLDivElement>(null);
  const SUGGESTIONS = scope === 'general' ? SUGGESTIONS_GENERAL : SUGGESTIONS_ANALYSIS;

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns.length, isSending]);

  const handleSend = async () => {
    if (!composer.trim() || isSending) return;
    const q = composer;
    setComposer('');
    await sendMessage(q);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className={`chat-panel chat-panel-${variant}`}>
      <div className="conv-body">
        <div className="conv-thread">
          {turns.length === 0 && (
            <div className="conv-welcome">
              <p>
                {emptyHint ??
                  (scope === 'general'
                    ? 'Ask anything about ISO 9001, 14001, or 45001 in general. This conversation is not grounded on a specific analysis.'
                    : 'Ask anything about this analysis. Answers cite the underlying documents and ISO clauses.')}
              </p>
              <p style={{ marginTop: 8, color: 'var(--text-tertiary)', fontSize: 13 }}>
                {scope === 'general'
                  ? 'For questions about your own documents, open one of your analyses and ask from there.'
                  : "If the question cannot be answered from the evidence available, the analyst will say so plainly."}
              </p>
            </div>
          )}
          {turns.map((t) => (
            <Turn key={t.id} turn={t} userName={user?.display_name} />
          ))}
          <div ref={threadEndRef} />
        </div>
      </div>

      <div className="composer-wrapper">
        {turns.length === 0 && (
          <div className="suggestions">
            {SUGGESTIONS.map((s) => (
              <button key={s} className="suggestion" onClick={() => setComposer(s)} type="button">
                {s}
              </button>
            ))}
          </div>
        )}
        <div className="composer">
          <textarea
            className="composer-input"
            rows={2}
            placeholder={
              scope === 'general'
                ? 'Ask about ISO clauses, severity, audit prep…'
                : 'Ask anything about this analysis. Answers will cite your documents.'
            }
            value={composer}
            onChange={(e) => setComposer(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isSending}
          />
          <div className="composer-toolbar">
            <span className="composer-hint">
              Press <span className="kbd">⏎</span> to send · <span className="kbd">⇧⏎</span> for new line
            </span>
            <button
              type="button"
              className="composer-send"
              onClick={handleSend}
              disabled={!composer.trim() || isSending}
            >
              {isSending ? 'Sending…' : 'Send'}
              <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
