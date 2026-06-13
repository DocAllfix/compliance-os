import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { runAnalysis, runAnalyzeDms, type CompanyContext, type SseEvent } from '@/lib/api';
import { useRequirementSets, useDmsFolders, useDmsDocuments } from '@/lib/hooks';

type Source = 'dms' | 'zip';

const STANDARDS = [
  { id: 'ISO 9001:2015', area: 'Quality management' },
  { id: 'ISO 14001:2015', area: 'Environmental' },
  { id: 'ISO 45001:2018', area: 'Health & safety' },
];

// Sprint R0: canonical backend values vs display labels. The backend schema
// (CompanyContext) and the prompt builder (context_intake.py) expect
// hyphenated ranges ("11-50") and snake_case certified values ("in_progress").
// The en-dash / capitalised variants are display-only.
const EMPLOYEE_RANGES = [
  { value: '1-10', label: '1–10' },
  { value: '11-50', label: '11–50' },
  { value: '51-250', label: '51–250' },
  { value: '250+', label: '250+' },
];
const CERTIFIED_OPTIONS = [
  { value: 'no', label: 'No' },
  { value: 'yes', label: 'Yes' },
  { value: 'in_progress', label: 'In progress' },
];
const SITES_OPTIONS = [
  { value: '1', label: '1' },
  { value: '2-5', label: '2–5' },
  { value: '5+', label: '5+' },
];

function labelFor(options: { value: string; label: string }[], value: string): string {
  return options.find((o) => o.value === value)?.label ?? value;
}

type StepIdx = 0 | 1 | 2 | 3;

interface FormState {
  company_name: string;
  sector: string;
  employee_range: string;
  certified: string;
  sites_count: string;
  norms: string[];
}

// Sprint F4: defaults dichiarati realisticamente neutri.
// company_name e norms restano vuoti per forzare un input cosciente.
// sector / employee_range / certified / sites_count hanno il valore "minimum
// realistic": piu' frequente nella nostra base d'utenza target, ma sempre
// modificabile dall'utente al primo step.
const DEFAULT_FORM: FormState = {
  company_name: '',
  sector: 'Manufacturing',
  employee_range: '11-50',
  certified: 'no',
  sites_count: '1',
  norms: [],
};

const STEPS = [
  { num: 1, title: 'Tell us about the company' },
  { num: 2, title: 'Choose documents' },
  { num: 3, title: 'Review & confirm' },
  { num: 4, title: 'Run analysis' },
];

function Stepper({ current }: { current: StepIdx }) {
  return (
    <aside className="stepper">
      <div className="stepper-eyebrow">New analysis</div>
      {STEPS.map((s, i) => {
        const cls = i < current ? 'done' : i === current ? 'current' : 'todo';
        return (
          <div key={s.num} className={`step-row ${cls}`}>
            <span className="step-mark">
              {cls === 'done' && (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12" /></svg>
              )}
            </span>
            <div className="step-body">
              <div className="step-num">STEP {s.num}</div>
              <div className="step-title">{s.title}</div>
            </div>
          </div>
        );
      })}
    </aside>
  );
}

function Step1Context({ form, setForm, onNext }: { form: FormState; setForm: (f: FormState) => void; onNext: () => void }) {
  const update = <K extends keyof FormState>(k: K, v: FormState[K]) => setForm({ ...form, [k]: v });
  const toggleStandard = (id: string) =>
    update('norms', form.norms.includes(id) ? form.norms.filter((x) => x !== id) : [...form.norms, id]);
  // Fase 7 (PRD 1.4.4b): criteri operativi custom selezionabili accanto agli standard
  const requirementSets = useRequirementSets().data ?? [];

  const answered = [form.company_name, form.sector, form.employee_range, form.certified, form.sites_count, form.norms.length > 0]
    .filter(Boolean).length;
  const valid = form.company_name.trim().length > 0 && form.norms.length > 0;

  return (
    <section className="form-area">
      <div className="form-eyebrow">Step 1 of 4</div>
      <h1 className="form-title">Tell us about the company</h1>
      <p className="form-lead">
        Six questions, sixty seconds. The answers shape how we read your documents and which thresholds we apply.
      </p>

      <div className="field-grid">
        <div className="field full">
          <label className="field-label">Company name</label>
          <input className="input" type="text" value={form.company_name} onChange={(e) => update('company_name', e.target.value)} />
        </div>

        <div className="field">
          <label className="field-label">Industry sector</label>
          <select className="select" value={form.sector} onChange={(e) => update('sector', e.target.value)}>
            {['Manufacturing', 'Construction', 'Services', 'Logistics', 'Healthcare', 'Energy', 'Other'].map((o) => <option key={o}>{o}</option>)}
          </select>
        </div>

        <div className="field">
          <label className="field-label">Number of employees</label>
          <select className="select" value={form.employee_range} onChange={(e) => update('employee_range', e.target.value)}>
            {EMPLOYEE_RANGES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>

        <div className="field">
          <label className="field-label">Currently certified?</label>
          <select className="select" value={form.certified} onChange={(e) => update('certified', e.target.value)}>
            {CERTIFIED_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>

        <div className="field">
          <label className="field-label">Operating sites</label>
          <select className="select" value={form.sites_count} onChange={(e) => update('sites_count', e.target.value)}>
            {SITES_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>

        <div className="field full">
          <label className="field-label">Standards to assess</label>
          <span className="field-help">Pick one or more. We'll only score the clauses that belong to the selected standards.</span>
          <div className="standards-grid" style={{ marginTop: 6 }}>
            {STANDARDS.map((s) => (
              <div
                key={s.id}
                className={`standard-card${form.norms.includes(s.id) ? ' selected' : ''}`}
                onClick={() => toggleStandard(s.id)}
              >
                <span className="check">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12" /></svg>
                </span>
                <div className="standard-card-name">{s.id}</div>
                <div className="standard-card-area">{s.area}</div>
              </div>
            ))}
          </div>

          {/* Fase 7 (PRD 1.4.4b) — criteri operativi propri dell'organizzazione */}
          {requirementSets.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <span className="field-help">
                You can also assess against your organisation's own operating criteria.
              </span>
              <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {requirementSets.map((rs) => (
                  <label
                    key={rs.name}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      padding: '10px 14px', borderRadius: 8, cursor: 'pointer',
                      border: `1px solid ${form.norms.includes(rs.label) ? 'var(--accent)' : 'var(--border-subtle)'}`,
                      background: 'var(--bg-surface)', fontSize: 13.5,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={form.norms.includes(rs.label)}
                      onChange={() => toggleStandard(rs.label)}
                    />
                    <span style={{ fontWeight: 500 }}>{rs.label}</span>
                    <span style={{ color: 'var(--text-tertiary)', fontSize: 12 }}>
                      {rs.requirement_count} requirement{rs.requirement_count === 1 ? '' : 's'}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <footer className="form-footer">
        <div className="progress-text"><b>{answered} of 6</b> answered</div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Link className="btn btn-link" to="/dashboard">Cancel</Link>
          <button className="btn btn-accent" onClick={onNext} disabled={!valid}>
            Continue to upload
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" /></svg>
          </button>
        </div>
      </footer>
    </section>
  );
}

function Step2Source({
  source, setSource, dmsFolderId, setDmsFolderId, file, setFile, onBack, onNext,
}: {
  source: Source; setSource: (s: Source) => void;
  dmsFolderId: number | null; setDmsFolderId: (id: number | null) => void;
  file: File | null; setFile: (f: File | null) => void;
  onBack: () => void; onNext: () => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const folders = useDmsFolders().data?.folders ?? [];
  const dmsDocs = useDmsDocuments(source === 'dms' ? dmsFolderId : undefined);
  const docCount = source === 'dms' ? (dmsDocs.data?.documents.length ?? 0) : 0;

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f && f.name.toLowerCase().endsWith('.zip')) setFile(f);
  };

  const canContinue = source === 'dms' ? docCount > 0 : !!file;

  return (
    <section className="form-area">
      <div className="form-eyebrow">Step 2 of 4</div>
      <h1 className="form-title">Choose documents</h1>
      <p className="form-lead">Assess the documents already in your library, or upload a fresh ZIP.</p>

      <div className="source-toggle" style={{ marginTop: 16 }}>
        <button
          type="button"
          className={`source-tab${source === 'dms' ? ' active' : ''}`}
          onClick={() => setSource('dms')}
        >
          From your library
        </button>
        <button
          type="button"
          className={`source-tab${source === 'zip' ? ' active' : ''}`}
          onClick={() => setSource('zip')}
        >
          Upload a ZIP
        </button>
      </div>

      {source === 'dms' ? (
        <div style={{ marginTop: 16 }}>
          <div className="field">
            <label className="field-label">Scope</label>
            <span className="field-help">Analyse everything in your library, or a single folder.</span>
            <select
              className="select"
              style={{ marginTop: 6 }}
              value={dmsFolderId ?? 'all'}
              onChange={(e) => setDmsFolderId(e.target.value === 'all' ? null : Number(e.target.value))}
            >
              <option value="all">All documents</option>
              {folders.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </div>
          <p style={{ marginTop: 12, fontSize: 13, color: 'var(--text-tertiary)' }}>
            {dmsDocs.isLoading
              ? 'Counting documents…'
              : docCount > 0
              ? `${docCount} document${docCount === 1 ? '' : 's'} in scope.`
              : 'No documents in this scope. Add some in Documents, or upload a ZIP.'}
          </p>
        </div>
      ) : (
        <div
          onDrop={onDrop}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onClick={() => inputRef.current?.click()}
          style={{
            marginTop: 16, padding: 48, textAlign: 'center',
            border: `1.5px dashed ${dragOver ? 'var(--accent)' : 'var(--border-default)'}`,
            borderRadius: 10,
            background: dragOver ? 'var(--accent-subtle)' : 'var(--bg-surface)',
            cursor: 'pointer', transition: 'all 150ms',
          }}
        >
          <input ref={inputRef} type="file" accept=".zip"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)} style={{ display: 'none' }} />
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ color: 'var(--text-tertiary)', marginBottom: 12 }}>
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          {file ? (
            <>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-primary)' }}>{file.name}</div>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 4 }}>
                {(file.size / 1024 / 1024).toFixed(1)} MB · click or drop a different ZIP to replace
              </div>
            </>
          ) : (
            <>
              <div style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 500 }}>Drop your ZIP here, or click to browse</div>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 4 }}>
                Procedures, registers, manuals, policies — anything in PDF, DOCX, XLSX
              </div>
            </>
          )}
        </div>
      )}

      <footer className="form-footer">
        <div className="progress-text">
          {source === 'dms'
            ? (docCount > 0 ? <><b>{docCount}</b> in scope</> : 'Nothing in scope')
            : (file ? <><b>1 file</b> ready</> : 'No file selected')}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-link" onClick={onBack}>← Back</button>
          <button className="btn btn-accent" onClick={onNext} disabled={!canContinue}>
            Continue to review
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" /></svg>
          </button>
        </div>
      </footer>
    </section>
  );
}

function Step3Review({ form, source, file, dmsFolderName, dmsCount, onBack, onStart }: {
  form: FormState; source: Source; file: File | null;
  dmsFolderName: string; dmsCount: number;
  onBack: () => void; onStart: () => void;
}) {
  return (
    <section className="form-area">
      <div className="form-eyebrow">Step 3 of 4</div>
      <h1 className="form-title">Review &amp; confirm</h1>
      <p className="form-lead">Before we run, double-check what we're going to assess.</p>

      <div
        style={{
          marginTop: 16,
          padding: '20px 24px',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 10,
          display: 'grid',
          gridTemplateColumns: '120px 1fr',
          rowGap: 12,
          columnGap: 16,
          fontSize: 13.5,
        }}
      >
        <span style={{ color: 'var(--text-tertiary)' }}>Company</span>
        <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{form.company_name}</span>
        <span style={{ color: 'var(--text-tertiary)' }}>Sector</span>
        <span>{form.sector}</span>
        <span style={{ color: 'var(--text-tertiary)' }}>Employees</span>
        <span>{labelFor(EMPLOYEE_RANGES, form.employee_range)}</span>
        <span style={{ color: 'var(--text-tertiary)' }}>Certified</span>
        <span>{labelFor(CERTIFIED_OPTIONS, form.certified)}</span>
        <span style={{ color: 'var(--text-tertiary)' }}>Sites</span>
        <span>{labelFor(SITES_OPTIONS, form.sites_count)}</span>
        <span style={{ color: 'var(--text-tertiary)' }}>Standards</span>
        <span>{form.norms.join(' · ')}</span>
        <span style={{ color: 'var(--text-tertiary)' }}>Documents</span>
        {source === 'dms' ? (
          <span>From library · {dmsFolderName} ({dmsCount} document{dmsCount === 1 ? '' : 's'})</span>
        ) : (
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
            {file?.name} ({((file?.size ?? 0) / 1024 / 1024).toFixed(1)} MB)
          </span>
        )}
      </div>

      <p style={{ marginTop: 24, fontStyle: 'italic', fontSize: 14, color: 'var(--text-tertiary)', maxWidth: '56ch' }}>
        Estimated processing time: 2–5 minutes depending on document count. The browser stays open during the analysis.
      </p>

      <footer className="form-footer">
        <div className="progress-text">Ready to run</div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-link" onClick={onBack}>← Back</button>
          <button className="btn btn-accent" onClick={onStart}>
            Run analysis
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9 18 15 12 9 6" /></svg>
          </button>
        </div>
      </footer>
    </section>
  );
}

interface ProgressState {
  pct: number;
  msg: string;
  done: boolean;
  error: string | null;
  analysisId: string | null;
  log: { pct: number; msg: string; ts: number }[];
}

function Step4Progress({ progress }: { progress: ProgressState }) {
  return (
    <section className="form-area">
      <div className="form-eyebrow">Step 4 of 4</div>
      <h1 className="form-title">{progress.error ? 'Something went wrong' : progress.done ? 'Analysis complete' : 'Running analysis'}</h1>
      <p className="form-lead">
        {progress.error
          ? 'The pipeline returned an error. See details below.'
          : progress.done
          ? 'Your gap report is ready. Open it from the link below.'
          : "We're reading your documents, indexing the evidence, and scoring each clause."}
      </p>

      {!progress.done && !progress.error && (
        <>
          <div style={{ height: 6, background: 'var(--bg-elevated)', borderRadius: 3, overflow: 'hidden', marginTop: 24 }}>
            <div
              style={{
                height: '100%',
                width: `${progress.pct}%`,
                background: 'var(--accent)',
                borderRadius: 3,
                transition: 'width 250ms cubic-bezier(0.25, 1, 0.5, 1)',
              }}
            />
          </div>
          <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--text-tertiary)' }}>
            <span>{progress.msg}</span>
            <span className="tabular">{progress.pct}%</span>
          </div>
        </>
      )}

      {progress.error && (
        <div
          style={{
            marginTop: 24,
            padding: '12px 14px',
            background: 'var(--severity-major-bg)',
            color: 'var(--severity-major-fg)',
            borderRadius: 8,
            fontSize: 13.5,
          }}
        >
          {progress.error}
        </div>
      )}

      {progress.log.length > 0 && (
        <div
          style={{
            marginTop: 24,
            padding: 16,
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 8,
            maxHeight: 240,
            overflowY: 'auto',
            fontFamily: 'var(--font-mono)',
            fontSize: 11.5,
            lineHeight: 1.7,
          }}
        >
          {progress.log.map((l, i) => (
            <div key={i} style={{ color: 'var(--text-secondary)' }}>
              <span style={{ color: 'var(--text-tertiary)', marginRight: 12 }}>{l.pct.toString().padStart(3, ' ')}%</span>
              {l.msg}
            </div>
          ))}
        </div>
      )}

      {progress.done && progress.analysisId && (
        <div style={{ marginTop: 32, display: 'flex', gap: 8 }}>
          <Link to={`/analyses/${progress.analysisId}`} className="btn btn-accent">
            Open results
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" /></svg>
          </Link>
        </div>
      )}
    </section>
  );
}

export function NewAnalysis() {
  const [step, setStep] = useState<StepIdx>(0);
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [source, setSource] = useState<Source>('dms');
  const [dmsFolderId, setDmsFolderId] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<ProgressState>({
    pct: 0, msg: 'Starting…', done: false, error: null, analysisId: null, log: [],
  });

  const folders = useDmsFolders().data?.folders ?? [];
  const dmsScopeDocs = useDmsDocuments(source === 'dms' ? dmsFolderId : undefined);
  const dmsFolderName = dmsFolderId == null ? 'All documents' : (folders.find((f) => f.id === dmsFolderId)?.name ?? 'Folder');
  const dmsCount = dmsScopeDocs.data?.documents.length ?? 0;

  const onEvent = (ev: SseEvent) =>
    setProgress((prev) => {
      if ('error' in ev) return { ...prev, error: ev.error, done: true };
      if ('done' in ev) return { ...prev, pct: 100, msg: 'Complete', done: true, analysisId: ev.analysis_id };
      return { ...prev, pct: ev.pct, msg: ev.msg, log: [...prev.log, { pct: ev.pct, msg: ev.msg, ts: Date.now() }] };
    });

  const start = async () => {
    setStep(3);
    setProgress({ pct: 0, msg: 'Starting…', done: false, error: null, analysisId: null, log: [] });

    const ctx: CompanyContext = {
      company_name: form.company_name,
      sector: form.sector,
      employee_range: form.employee_range,
      certified: form.certified,
      sites_count: form.sites_count,
      norms: form.norms,
    };

    try {
      if (source === 'dms') {
        await runAnalyzeDms(
          { ...ctx, scope: dmsFolderId == null ? 'all' : 'folder', folder_id: dmsFolderId },
          onEvent,
        );
      } else {
        if (!file) return;
        await runAnalysis(file, ctx, onEvent);
      }
    } catch (err) {
      setProgress((prev) => ({ ...prev, error: (err as Error).message, done: true }));
    }
  };

  return (
    <div className="wizard-layout">
      <Stepper current={step} />
      {step === 0 && <Step1Context form={form} setForm={setForm} onNext={() => setStep(1)} />}
      {step === 1 && (
        <Step2Source
          source={source} setSource={setSource}
          dmsFolderId={dmsFolderId} setDmsFolderId={setDmsFolderId}
          file={file} setFile={setFile}
          onBack={() => setStep(0)} onNext={() => setStep(2)}
        />
      )}
      {step === 2 && (
        <Step3Review
          form={form} source={source} file={file}
          dmsFolderName={dmsFolderName} dmsCount={dmsCount}
          onBack={() => setStep(1)} onStart={start}
        />
      )}
      {step === 3 && <Step4Progress progress={progress} />}
    </div>
  );
}
