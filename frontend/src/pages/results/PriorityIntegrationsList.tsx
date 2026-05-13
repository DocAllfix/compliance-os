/**
 * Top Priority Integrations — Phase 4 section §5.
 *
 * Ordered list of action-verb sentences from the backend's
 * ExecutiveSummary.top_priority_integrations. Highlights inline clause
 * tags such as [ISO 14001 §6.1.2] so the manager can scan by clause.
 */
import { useState } from 'react';

interface Props {
  items: string[];
}

function ChevronIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

/**
 * Split an integration string into tokens, lifting `[ISO 14001 §6.1.2]`-style
 * tags into a separate `<span class="integration-tag">` so the layout can
 * style them with accent colour without using gradient text or other
 * decorative tricks DESIGN.md forbids.
 */
function renderTokens(text: string): React.ReactNode[] {
  // Match bracketed tags: [ISO 9001 §X.Y], [DVR Jeoedil R.pdf, expired 605 days ago], etc.
  const pattern = /\[([^\]]+)\]/g;
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    const inner = match[1];
    const isClauseTag = /^ISO\s+\d/.test(inner);
    nodes.push(
      <span
        key={`tag-${key++}`}
        className={isClauseTag ? 'integration-clause-tag' : 'integration-doc-tag'}
      >
        {inner}
      </span>,
    );
    lastIndex = pattern.lastIndex;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes;
}

export function PriorityIntegrationsList({ items }: Props) {
  const [expanded, setExpanded] = useState(true);
  const shown = items.slice(0, 10);

  if (shown.length === 0) return null;

  return (
    <section className={`integrations-section${expanded ? ' expanded' : ''}`}>
      <button
        type="button"
        className="integrations-head"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <span className="integrations-head-title">Top priority integrations</span>
        <span className="integrations-head-count">{shown.length}</span>
        <ChevronIcon />
      </button>

      {expanded && (
        <ol className="integrations-list">
          {shown.map((action, i) => (
            <li key={i} className="integration-item">
              <span className="integration-num">{String(i + 1).padStart(2, '0')}</span>
              <span className="integration-body">{renderTokens(action)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
