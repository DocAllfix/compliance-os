/**
 * Executive Narrative — Phase 4 section §2.
 *
 * Renders the 3-4 paragraph narrative produced by the backend's
 * generate_executive_summary as Inter body copy (DESIGN.md v2: no serif)
 * at a comfortable reading width. Pure presentation.
 */
interface Props {
  text: string;
}

export function ExecutiveNarrative({ text }: Props) {
  // Split on blank lines so each paragraph becomes its own <p>.
  const paragraphs = text
    .split(/\n\s*\n+/)
    .map((p) => p.trim())
    .filter(Boolean);

  if (paragraphs.length === 0) return null;

  return (
    <section className="exec-narrative">
      <header className="exec-narrative-head">
        <span className="eyebrow">Executive narrative</span>
      </header>
      <div className="exec-narrative-body">
        {paragraphs.map((p, i) => (
          <p key={i}>{p}</p>
        ))}
      </div>
    </section>
  );
}
