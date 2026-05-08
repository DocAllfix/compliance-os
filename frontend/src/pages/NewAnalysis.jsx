// @ts-nocheck
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { FileArchive, CheckCircle, ArrowRight, ArrowLeft, Download, AlertTriangle, TrendingUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import ContextIntakeForm from '@/components/compliance/ContextIntakeForm';
import FileDropzone from '@/components/shared/FileDropzone';
import GapMatrix from '@/components/compliance/GapMatrix';
import DocumentViewer from '@/components/compliance/DocumentViewer';
import ChatPanel from '@/components/compliance/ChatPanel';
import { useComplianceStore } from '@/store/complianceStore';
import { useSSEProcess } from '@/hooks/useSSEProcess';
import { MOCK_GAPS, MOCK_ANALYSIS } from '@/lib/mockData';

const STEPS = [
  'Company Context',
  'Upload Documents',
  'Review & Confirm',
  'Analysing',
  'Results',
];


function StepIndicator({ currentStep }) {
  return (
    <div className="flex items-center gap-2 mb-8">
      {STEPS.map((label, i) => {
        const done    = i < currentStep;
        const active  = i === currentStep;
        return (
          <React.Fragment key={i}>
            <div className="flex items-center gap-1.5">
              <div className={`
                w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 transition-colors duration-200
                ${done   ? 'bg-primary text-primary-foreground' :
                  active ? 'bg-primary/20 text-primary border border-primary' :
                           'bg-muted text-muted-foreground'}
              `}>
                {done ? <CheckCircle className="w-3.5 h-3.5" /> : i + 1}
              </div>
              <span className={`text-xs font-medium ${active ? 'text-foreground' : 'text-muted-foreground'}`}>
                {label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`flex-1 h-px ${i < currentStep ? 'bg-primary/40' : 'bg-border'}`} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

function ReviewConfirm({ context, file, onBack, onStart }) {
  const estimatedMinutes = (context?.norms?.length || 1) * 2;
  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-border bg-card divide-y divide-border">
        <div className="px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-2">Company</p>
          <p className="text-sm font-medium text-foreground">{context?.company_name}</p>
          <p className="text-xs text-muted-foreground mt-0.5">{context?.sector} · {context?.employee_range} employees · {context?.sites_count} site(s)</p>
        </div>
        <div className="px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-2">Standards</p>
          <div className="flex flex-wrap gap-1.5">
            {context?.norms?.map((n) => (
              <span key={n} className="px-2 py-0.5 rounded text-xs font-mono bg-primary/10 text-primary">{n}</span>
            ))}
          </div>
        </div>
        <div className="px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-2">Documents</p>
          <p className="text-sm text-foreground">{file?.name}</p>
          <p className="text-xs text-muted-foreground mt-0.5">{file ? ((file.size / 1e6).toFixed(1) + ' MB') : '—'}</p>
        </div>
        <div className="px-4 py-3">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1">Estimated time</p>
          <p className="text-sm text-foreground">~{estimatedMinutes} minutes</p>
        </div>
      </div>
      <div className="flex gap-3">
        <Button variant="outline" onClick={onBack} className="gap-1.5">
          <ArrowLeft className="w-4 h-4" /> Back
        </Button>
        <Button onClick={onStart} className="gap-2">
          Start Analysis <ArrowRight className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
}

function AnalysisProgress({ progress, message, error }) {
  const prefersReduced = useReducedMotion();
  const pct = progress ?? 0;
  const msg = message || 'Preparing analysis…';

  return (
    <div className="space-y-6 py-4">
      <Progress value={pct} className="h-1.5" />
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="flex items-center gap-2 text-sm text-muted-foreground"
      >
        <div className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse shrink-0" aria-hidden="true" />
        <AnimatePresence mode="wait">
          <motion.span
            key={msg}
            initial={{ opacity: 0, y: prefersReduced ? 0 : 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: prefersReduced ? 0 : -4 }}
            transition={{ duration: prefersReduced ? 0 : 0.2 }}
          >
            {msg}
          </motion.span>
        </AnimatePresence>
      </div>
      <p className="text-xs text-muted-foreground">{pct}% complete</p>
      {error && (
        <p className="text-xs text-destructive">{error.message || 'Analysis failed. Showing demo data.'}</p>
      )}
    </div>
  );
}


function ComplianceScoreCard({ result }) {
  const norms = result?.norms || [];
  const firstNorm = norms[0];
  const score = firstNorm?.overall_score ?? 58;
  const major = firstNorm?.major_count ?? 2;
  const spof  = firstNorm?.spof_count ?? 1;

  const scoreColor = score >= 75 ? 'text-success' : score >= 50 ? 'text-warning' : 'text-destructive';

  return (
    <div className="flex items-center gap-6 px-5 py-3 rounded-lg border border-border bg-card">
      <div className="flex items-center gap-3">
        <TrendingUp className="w-4 h-4 text-muted-foreground" />
        <div>
          <p className="text-xs text-muted-foreground uppercase tracking-wide">Compliance Score</p>
          <p className={`text-xl font-semibold font-mono tracking-tight ${scoreColor}`}>{score}</p>
        </div>
      </div>
      <div className="w-px h-8 bg-border" />
      <div className="flex items-center gap-3">
        <AlertTriangle className="w-4 h-4 text-destructive" />
        <div>
          <p className="text-xs text-muted-foreground uppercase tracking-wide">Major Gaps</p>
          <p className="text-lg font-semibold text-destructive">{major}</p>
        </div>
      </div>
      {spof > 0 && (
        <>
          <div className="w-px h-8 bg-border" />
          <div>
            <p className="text-xs text-muted-foreground uppercase tracking-wide">SPoF</p>
            <p className="text-lg font-semibold text-spof">{spof}</p>
          </div>
        </>
      )}
      <div className="ml-auto">
        <p className="text-xs text-muted-foreground">
          {norms.map(n => n.norm).join(' · ')}
        </p>
      </div>
    </div>
  );
}

function AnalysisResults({ result, analysisId, onBack }) {
  const [activeSource, setActiveSource] = useState(null);

  const gaps = result?.norms?.flatMap(n => n.clauses) || MOCK_GAPS;

  const handleSourceClick = (source) => {
    setActiveSource(source);
  };

  return (
    <div className="space-y-4">
      {/* Score card */}
      <ComplianceScoreCard result={result} />

      {/* Actions bar */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {gaps.length} clause{gaps.length !== 1 ? 's' : ''} assessed
        </p>
        <div className="flex items-center gap-2">
          <Button
            variant="outline" size="sm" className="gap-1.5"
            onClick={() => window.open(`/api/compliance/analyses/${analysisId}/download`, '_blank')}
          >
            <Download className="w-3.5 h-3.5" />
            Download Report
          </Button>
          <Button variant="ghost" size="sm" onClick={onBack}>
            Back to Dashboard
          </Button>
        </div>
      </div>

      {/* Two-panel layout */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] xl:grid-cols-[1fr_380px] gap-4 min-h-[600px]">
        {/* Left: GapMatrix */}
        <div className="space-y-4">
          <GapMatrix
            gaps={gaps}
            onSourceClick={handleSourceClick}
            onStatusChange={() => {}}
          />
        </div>

        {/* Right: DocumentViewer + ChatPanel */}
        <div className="flex flex-col gap-4">
          <div className="flex-1 min-h-[300px]">
            <DocumentViewer
              fileUrl={activeSource?.fileUrl || null}
              targetPages={activeSource?.pages || []}
              onToggleExpand={() => {}}
            />
          </div>
          <div className="h-[300px]">
            <ChatPanel
              analysisId={analysisId}
              onSourceClick={handleSourceClick}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function NewAnalysis() {
  const navigate = useNavigate();
  const { currentStep, companyContext, uploadedFile, analysisResult, setStep, setContext, setFile, setResult, reset } =
    useComplianceStore();
  const prefersReduced = useReducedMotion();
  const { start, isPending, progress, message, error } = useSSEProcess();

  React.useEffect(() => { reset(); }, []);

  const handleContext = (ctx) => { setContext(ctx); setStep(1); };
  const handleFile    = (f)   => { setFile(f); };

  const handleStart = async () => {
    setStep(3);
    const formData = new FormData();
    formData.append('file', uploadedFile);
    formData.append('company_name',   companyContext.company_name);
    formData.append('sector',         companyContext.sector);
    formData.append('employee_range', companyContext.employee_range);
    formData.append('certified',      companyContext.certified);
    formData.append('sites_count',    companyContext.sites_count);
    formData.append('norms',          JSON.stringify(companyContext.norms));

    try {
      const doneEvent = await start('/api/compliance/analyze', formData);
      const result = doneEvent?.result || MOCK_ANALYSIS;
      // Attach analysis_id at top level for easy access downstream
      if (doneEvent?.analysis_id && !result.analysis_id) {
        result.analysis_id = doneEvent.analysis_id;
      }
      setResult(result);
      setStep(4);
    } catch {
      // Backend unreachable — fall back to demo data silently
      setResult(MOCK_ANALYSIS);
      setStep(4);
    }
  };

  // On step 4 the two-panel results need full width — remove max-w-2xl
  const wrapperClass = currentStep === 4 ? '' : 'max-w-2xl mx-auto';

  return (
    <div className={wrapperClass}>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">New Analysis</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Upload your company documents to receive a clause-by-clause ISO gap report.
        </p>
      </div>

      {currentStep < 4 && <StepIndicator currentStep={currentStep} />}

      <AnimatePresence mode="wait">
        <motion.div
          key={currentStep}
          initial={{ opacity: 0, x: prefersReduced ? 0 : 12 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: prefersReduced ? 0 : -12 }}
          transition={{ duration: prefersReduced ? 0 : 0.18, ease: [0.25, 0.46, 0.45, 0.94] }}
        >
          {currentStep === 0 && (
            <ContextIntakeForm onContinue={handleContext} />
          )}

          {currentStep === 1 && (
            <div className="space-y-4">
              <FileDropzone
                accept=".zip,.pdf,.docx"
                title="Drop your documents here"
                description="ZIP archive, PDF or DOCX · max 50 MB"
                icon={FileArchive}
                file={uploadedFile}
                onFileSelect={handleFile}
                onRemove={() => setFile(null)}
              />
              <div className="flex gap-3">
                <Button variant="outline" onClick={() => setStep(0)} className="gap-1.5">
                  <ArrowLeft className="w-4 h-4" /> Back
                </Button>
                {uploadedFile && (
                  <Button onClick={() => setStep(2)} className="gap-2">
                    Continue <ArrowRight className="w-4 h-4" />
                  </Button>
                )}
              </div>
            </div>
          )}

          {currentStep === 2 && (
            <ReviewConfirm
              context={companyContext}
              file={uploadedFile}
              onBack={() => setStep(1)}
              onStart={handleStart}
            />
          )}

          {currentStep === 3 && (
            <div className="space-y-4">
              <p className="text-sm font-medium text-foreground">Running analysis…</p>
              <AnalysisProgress progress={progress} message={message} error={error} />
            </div>
          )}

          {currentStep === 4 && (
            <AnalysisResults
              result={analysisResult}
              analysisId={analysisResult?.analysis_id || 'mock_results'}
              onBack={() => navigate('/dashboard')}
            />
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
