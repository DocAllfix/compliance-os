import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { compliance, type ActionStatus } from './api';

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
