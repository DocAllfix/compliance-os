// @ts-nocheck
import React, { useState, useRef, useEffect } from 'react';
import { Send, FileText, Loader2, Bot } from 'lucide-react';
import { Button } from '@/components/ui/button';

// ── Mock response for development ─────────────────────────────────────────────

function mockAnswer(question) {
  return new Promise(resolve => {
    setTimeout(() => {
      resolve({
        answer: `Based on the available evidence, the documentation for "${question.slice(0, 40)}..." shows gaps in the relevant ISO clauses. Specifically, [Supplier_Procedure_Rev1.pdf, p.3] does not specify qualification criteria for critical suppliers, which is a core requirement under ISO 9001 §8.4.`,
        sources: [
          { file_name: 'Supplier_Procedure_Rev1.pdf', pages: [3], excerpt: 'Section 4.2 does not specify qualification criteria.' },
        ],
      });
    }, 1200);
  });
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SourceChip({ source, onSourceClick }) {
  return (
    <button
      onClick={() => onSourceClick?.(source)}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-primary/10 text-primary hover:bg-primary/20 transition-colors duration-150 font-mono"
    >
      <FileText className="w-3 h-3 shrink-0" />
      <span className="truncate max-w-[160px]">{source.file_name}</span>
      {source.pages?.length > 0 && (
        <span className="opacity-60 shrink-0">p.{source.pages[0]}</span>
      )}
    </button>
  );
}

function Message({ msg, onSourceClick }) {
  if (msg.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] px-3 py-2 rounded-lg bg-primary/10 text-sm text-foreground">
          {msg.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-2.5">
      <div className="w-6 h-6 rounded-full bg-primary/15 flex items-center justify-center shrink-0 mt-0.5">
        <Bot className="w-3.5 h-3.5 text-primary" />
      </div>
      <div className="flex-1 space-y-2">
        <div className="text-sm text-foreground leading-relaxed max-w-[65ch]">
          {msg.content}
        </div>
        {msg.sources?.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {msg.sources.map((s, i) => (
              <SourceChip key={i} source={s} onSourceClick={onSourceClick} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-2.5">
      <div className="w-6 h-6 rounded-full bg-primary/15 flex items-center justify-center shrink-0">
        <Bot className="w-3.5 h-3.5 text-primary" />
      </div>
      <div className="flex items-center gap-1 py-2">
        {[0, 1, 2].map(i => (
          <div
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-muted-foreground/50 animate-blink"
            style={{ animationDelay: `${i * 0.16}s` }}
          />
        ))}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

const SUGGESTIONS = [
  'What are the most critical gaps to fix first?',
  'Which supplier documents are missing?',
  'What should the Quality Manager prioritise this month?',
];

export default function ChatPanel({ analysisId, onSourceClick }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Ask me anything about this gap analysis. I can explain findings, clarify ISO requirements, or help you prioritise corrective actions.',
      sources: [],
    },
  ]);
  const [input, setInput]     = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const sendMessage = async (text) => {
    const question = (text || input).trim();
    if (!question || loading) return;

    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: question, sources: [] }]);
    setLoading(true);

    try {
      let data;
      if (analysisId && !analysisId.startsWith('mock_')) {
        const res = await fetch(`/api/compliance/chat/${analysisId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question }),
        });
        data = await res.json();
      } else {
        data = await mockAnswer(question);
      }

      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: data.answer, sources: data.sources || [] },
      ]);
    } catch (e) {
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: 'Could not reach the analysis service. Please try again.', sources: [] },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-col h-full bg-background rounded-lg border border-border overflow-hidden">
      {/* Header */}
      <div className="px-4 py-2.5 border-b border-border shrink-0">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Analysis Assistant
        </p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.map((msg, i) => (
          <Message key={i} msg={msg} onSourceClick={onSourceClick} />
        ))}
        {loading && <TypingIndicator />}

        {/* Suggestions (show only when no user messages yet) */}
        {messages.length === 1 && !loading && (
          <div className="space-y-1.5 pt-2">
            {SUGGESTIONS.map((s, i) => (
              <button
                key={i}
                onClick={() => sendMessage(s)}
                className="w-full text-left text-xs text-muted-foreground hover:text-foreground px-3 py-2 rounded-md border border-border hover:border-muted-foreground/30 hover:bg-muted/20 transition-colors duration-150"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-3 pb-3 pt-2 border-t border-border shrink-0">
        <div className="flex items-end gap-2">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about this analysis…"
            rows={1}
            className="flex-1 resize-none bg-bg-elevated border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors duration-150"
            style={{ minHeight: '38px', maxHeight: '120px' }}
            onInput={e => {
              e.target.style.height = 'auto';
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
            }}
          />
          <Button
            size="icon"
            className="h-[38px] w-[38px] shrink-0"
            onClick={() => sendMessage()}
            disabled={!input.trim() || loading}
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
          </Button>
        </div>
      </div>
    </div>
  );
}
