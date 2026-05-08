import { create } from 'zustand';

const initialWizard = {
  currentStep: 0,
  companyContext: null,
  uploadedFile: null,
  analysisResult: null,
};

export const useComplianceStore = create((set) => ({
  // Wizard
  ...initialWizard,
  setStep:    (step)    => set({ currentStep: step }),
  setContext: (ctx)     => set({ companyContext: ctx }),
  setFile:    (file)    => set({ uploadedFile: file }),
  setResult:  (result)  => set({ analysisResult: result }),
  reset:      ()        => set(initialWizard),

  // History
  analyses: [],
  setAnalyses: (analyses) => set({ analyses }),
  addAnalysis:  (analysis) => set((state) => ({ analyses: [analysis, ...state.analyses] })),
}));
