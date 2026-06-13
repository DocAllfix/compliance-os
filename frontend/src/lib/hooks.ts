import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { compliance, dms, type ActionStatus } from './api';

// ── DMS (Fase C) ────────────────────────────────────────────────────────────
export function useDmsFolders() {
  return useQuery({ queryKey: ['dms-folders'], queryFn: () => dms.listFolders() });
}

export function useDmsDocuments(folderId: number | null | undefined) {
  return useQuery({
    queryKey: ['dms-documents', folderId ?? 'all'],
    queryFn: () => dms.listDocuments(folderId ?? null),
  });
}

export function useDmsDocument(id: number | undefined) {
  return useQuery({
    queryKey: ['dms-document', id],
    queryFn: () => dms.getDocument(id as number),
    enabled: !!id,
  });
}

export function useAnalyses() {
  return useQuery({
    queryKey: ['analyses'],
    queryFn: () => compliance.listAnalyses(),
  });
}

export function useAnalysis(id: string | undefined) {
  return useQuery({
    queryKey: ['analysis', id],
    queryFn: () => compliance.getAnalysis(id as string),
    enabled: !!id,
  });
}

// Fase 7 — criteri operativi custom (PRD 1.4.4b)
export function useRequirementSets() {
  return useQuery({
    queryKey: ['requirement-sets'],
    queryFn: () => compliance.listRequirementSets(),
    staleTime: 5 * 60 * 1000,
  });
}

// Fase 5 — Delta / Compare
export function useDelta(id: string | undefined, against: string | undefined) {
  return useQuery({
    queryKey: ['delta', id, against],
    queryFn: () => compliance.getDelta(id as string, against as string),
    enabled: !!id && !!against,
  });
}

export function useUpdateAction(analysisId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ clauseId, status, notes }: { clauseId: string; status: ActionStatus; notes?: string }) =>
      compliance.updateAction(analysisId, clauseId, status, notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['analysis', analysisId] });
    },
  });
}

// Fase 4 — registro NC (PRD 1.4.8)

export function useAddManualNC(analysisId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ title, description, severity }: { title: string; description: string; severity: string }) =>
      compliance.addManualNC(analysisId, title, description, severity),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['analysis', analysisId] });
    },
  });
}

export function useDismissNC(analysisId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ ncId, reason }: { ncId: number; reason: string }) =>
      compliance.dismissNC(analysisId, ncId, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['analysis', analysisId] });
    },
  });
}

export function useRestoreNC(analysisId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ ncId }: { ncId: number }) => compliance.restoreNC(analysisId, ncId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['analysis', analysisId] });
    },
  });
}
