/**
 * Grounded post-audit chat.
 *
 * Reads analysis_id from /analyses/:id/chat (or shows an empty state when
 * the route is /chat without context). Composer uses Enter to send,
 * Shift+Enter for newline. Sources are rendered as chips citing the
 * underlying evidence file_name and ISO clause. Refusals from the backend
 * (chat_grounded.md instructs the model to say "No evidence in this audit
 * supports an answer..." when the retrieval is empty) are surfaced as a
 * neutral info turn, not an error.
 */
import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTheme } from '@/lib/theme';
import { useChat, type ChatTurn } from '@/lib/useChat';
import { useAnalysis } from '@/lib/hooks';
import { useAuth } from '@/lib/auth';
import type { ChatSource } from '@/lib/api';

const SUGGESTIONS = [
  'Which documents are expired?',
  'What does §6.1.3 require exactly?',
  'Which clause is most critical here?',
  'Summarise the legal register gap in plain English',
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

function ChatEmptyState() {
  return (
    <div className="main-inner">
      <div style={{ padding: 80, textAlign: 'center' }}>
        <h1 className="page-title" style={{ marginBottom: 8 }}>Open an analysis to start chatting</h1>
        <p style={{ color: 'var(--text-tertiary)', fontSize: 14, marginBottom: 24 }}>
          The analyst answers grounded questions about a specific compliance review.
        </p>
        <Link to="/dashboard" className="btn btn-accent">Back to dashboard</Link>
      </div>
    </div>
  );
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

function userInitials(name: string | undefined): string {
  if (!name) return '··';
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('') || '··';
}

function SourceChip({ src, index }: { src: ChatSource; index: number }) {
  return (
    <span className="source-chip" title={src.excerpt}>
      <span className="source-chip-num">{index + 1}</span>
      <span className="source-chip-info">
        <FileIcon />
        {src.file_name}
        {src.iso_clause_primary && (
          <span className="page"> · {src.iso_clause_primary}</span>
        )}
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
          <div className="msg-author"><b>{userName ?? 'You'}</b><span className="time">{formatTime(turn.timestamp)}</span></div>
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
            <span className="dot" /><span className="dot" /><span className="dot" />
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
            {!isRefusal && turn.text.split(/\n\s*\n+/).map((p, i) => (
              <p key={i}>{p}</p>
            ))}
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

export function Chat() {
  const { id } = useParams();
  const { toggleTheme } = useTheme();
  const { user } = useAuth();
  const [composer, setComposer] = useState('');
  const threadEndRef = useRef<HTMLDivElement>(null);

  const analysisQuery = useAnalysis(id);
  const { turns, isSending, sendMessage, clearConversation } = useChat(id);

  // Auto-scroll to bottom when new turns arrive
  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns.length, isSending]);

  if (!id) {
    return <ChatEmptyState />;
  }

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

  const analysis = analysisQuery.data;
  const companyName = analysis?.company ?? 'this analysis';
  const docsAnalyzed = analysis?.result?.documents_analyzed;
  const clauseCount = analysis?.result?.norms.reduce((acc, n) => acc + n.clauses.length, 0);
  const currentQuestion = turns.findLast?.((t) => t.role === 'user')?.text;

  return (
    <div className="chat-shell">
      {/* Threads sidebar */}
      <aside className="thread-list">
        <div className="thread-list-header">
          <div className="thread-list-eyebrow">
            <Link to={`/analyses/${id}`} style={{ color: 'var(--text-tertiary)', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6" /></svg>
              Back to analysis
            </Link>
          </div>
          <div className="thread-list-title">Ask the analyst</div>
        </div>

        <div className="thread-context">
          <div className="thread-context-label">Grounded in</div>
          <div className="thread-context-name">
            <FileIcon />
            {companyName}
          </div>
          {docsAnalyzed != null && clauseCount != null && (
            <div className="thread-context-meta">
              {docsAnalyzed} document{docsAnalyzed === 1 ? '' : 's'}
              <span className="sep"> · </span>
              {clauseCount} clause{clauseCount === 1 ? '' : 's'}
            </div>
          )}
        </div>

        <button className="thread-new-btn" onClick={clearConversation} disabled={turns.length === 0}>
          <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
          New conversation
        </button>

        <div className="thread-section-label">This session</div>

        {turns.length === 0 ? (
          <div className="thread-empty">Ask anything about this analysis. Answers cite your documents.</div>
        ) : (
          <div className="thread-current">
            <div className="thread-current-q">
              {turns.find((t) => t.role === 'user')?.text ?? 'New conversation'}
            </div>
            <div className="thread-current-meta">
              {turns.length} message{turns.length === 1 ? '' : 's'}
            </div>
          </div>
        )}

        <div style={{ marginTop: 'auto', padding: '14px 16px', borderTop: '1px solid var(--border-subtle)', background: 'var(--bg-elevated)' }}>
          <button className="theme-toggle" style={{ position: 'relative', top: 'auto', right: 'auto' }} aria-label="Toggle theme" onClick={toggleTheme}>
            <svg className="icon icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>
            <svg className="icon icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="4" /><path d="M12 2v2" /><path d="M12 20v2" /><path d="m4.93 4.93 1.41 1.41" /><path d="m17.66 17.66 1.41 1.41" /><path d="M2 12h2" /><path d="M20 12h2" /><path d="m4.93 19.07 1.41-1.41" /><path d="m17.66 6.34 1.41-1.41" /></svg>
          </button>
        </div>
      </aside>

      {/* Conversation */}
      <section className="conversation">
        <header className="conv-header">
          <div>
            <div className="conv-eyebrow">Ask the analyst</div>
            <div className="conv-title">
              {currentQuestion ?? 'Start a new conversation'}
            </div>
          </div>
        </header>

        <div className="conv-body">
          <div className="conv-thread">
            {turns.length === 0 && (
              <div className="conv-welcome">
                <p>Ask anything about this analysis. Answers cite the underlying documents and ISO clauses.</p>
                <p style={{ marginTop: 8, color: 'var(--text-tertiary)', fontSize: 13 }}>
                  If the question cannot be answered from the evidence available, the analyst will say so plainly.
                </p>
              </div>
            )}
            {turns.map((t) => (
              <Turn key={t.id} turn={t} userName={user?.display_name} />
            ))}
            <div ref={threadEndRef} />
          </div>
        </div>

        {/* Composer */}
        <div className="composer-wrapper">
          {turns.length === 0 && (
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="suggestion" onClick={() => setComposer(s)}>{s}</button>
              ))}
            </div>
          )}
          <div className="composer">
            <textarea
              className="composer-input"
              rows={2}
              placeholder="Ask anything about this analysis. Answers will cite your documents."
              value={composer}
              onChange={(e) => setComposer(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isSending}
            />
            <div className="composer-toolbar">
              <span className="composer-hint">Press <span className="kbd">⏎</span> to send · <span className="kbd">⇧⏎</span> for new line</span>
              <button
                className="composer-send"
                onClick={handleSend}
                disabled={!composer.trim() || isSending}
              >
                {isSending ? 'Sending…' : 'Send'}
                <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" /></svg>
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
