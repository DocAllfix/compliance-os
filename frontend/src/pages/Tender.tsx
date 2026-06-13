/**
 * Tender questionnaire (PQQ/SQ) — Fase H (PRD §1.6.9).
 *
 * Il manager sceglie un'analisi (per il grounding sull'evidenza), incolla le
 * domande del PQQ una per riga, e ottiene bozze di risposta con citazioni.
 * Dove l'evidenza non copre, la risposta è "needs input" (mai inventata).
 * Export DOCX con disclaimer "Draft for review — not a submission".
 */
import { useMemo, useState } from 'react';
import { useAnalyses } from '@/lib/hooks';
import { compliance, triggerBrowserDownload, ApiError, type PqqAnswer } from '@/lib/api';

export function Tender() {
  const analysesQuery = useAnalyses();
  const analyses = useMemo(() => analysesQuery.data ?? [], [analysesQuery.data]);
  const [analysisId, setAnalysisId] = useState<string>('');
  const [questionsText, setQuestionsText] = useState('');
  const [answers, setAnswers] = useState<PqqAnswer[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const effectiveId = analysisId || analyses[0]?.id || '';
  const company = analyses.find((a) => a.id === effectiveId)?.company ?? '';

  const run = async () => {
    const questions = questionsText.split('\n').map((q) => q.trim()).filter(Boolean);
    if (!effectiveId || questions.length === 0) return;
    setBusy(true); setErr(null); setAnswers([]);
    try {
      const res = await compliance.pqq(effectiveId, questions);
      setAnswers(res.answers);
    } catch (e) {
      setErr(e instanceof ApiError ? `${e.status} ${e.message}` : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const exportDocx = async () => {
    const { blob, filename } = await compliance.pqqExport(
      company,
      answers.map((a) => ({ question: a.question, answer: a.answer, status: a.status })),
    );
    triggerBrowserDownload(blob, filename);
  };

  return (
    <div className="main-inner">
      <header className="compact-header">
        <div>
          <div className="eyebrow">Tender support</div>
          <h1 className="page-title">Tender questionnaire</h1>
          <div className="page-meta">
            Draft PQQ / SQ answers from your documented evidence. Every draft must be reviewed before submission.
          </div>
        </div>
      </header>

      <div className="pqq-controls">
        <div className="field">
          <label className="field-label">Ground answers on</label>
          <select className="select" value={effectiveId} onChange={(e) => setAnalysisId(e.target.value)}>
            {analyses.length === 0 && <option value="">No analyses yet</option>}
            {analyses.map((a) => (
              <option key={a.id} value={a.id}>
                {a.company} · {new Date(a.analysis_date).toLocaleDateString('en-GB')}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="field-label">Questions (one per line)</label>
          <textarea
            className="input"
            rows={6}
            placeholder={'Do you hold ISO 9001 certification?\nDescribe your approach to risk management.\nProvide your Employers Liability insurance certificate.'}
            value={questionsText}
            onChange={(e) => setQuestionsText(e.target.value)}
            style={{ resize: 'vertical', fontFamily: 'var(--font-sans)' }}
          />
        </div>
        <button className="btn btn-accent" onClick={run} disabled={busy || !effectiveId || !questionsText.trim()}>
          {busy ? 'Drafting…' : 'Draft answers'}
        </button>
      </div>

      {err && <div className="dms-error">{err}</div>}

      {answers.length > 0 && (
        <div className="pqq-results">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '8px 0 14px' }}>
            <span className="section-title" style={{ margin: 0 }}>Drafts<span className="count">{answers.length}</span></span>
            <button className="btn btn-secondary" onClick={exportDocx}>Export DOCX</button>
          </div>
          <p className="pqq-disclaimer">Draft for review — not a submission. Complete the "needs input" items before submitting.</p>
          {answers.map((a, i) => (
            <article key={i} className="pqq-item">
              <div className="pqq-q">
                <span className="pqq-num">Q{i + 1}</span>
                {a.question}
                {a.status === 'needs_input'
                  ? <span className="badge badge-minor" style={{ marginLeft: 8 }}>Needs input</span>
                  : <span className="badge badge-conf" style={{ marginLeft: 8 }}>Answered</span>}
              </div>
              <p className="pqq-a">{a.answer}</p>
              {a.sources.length > 0 && (
                <div className="pqq-sources">
                  {a.sources.map((s, j) => (
                    <span key={j} className="pqq-source" title={s.excerpt}>{s.file_name}</span>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
