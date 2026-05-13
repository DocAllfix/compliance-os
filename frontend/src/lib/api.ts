/**
 * ComplianceOS API client.
 * Backend: FastAPI at /api (proxied through Vite dev server).
 */

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';
const TOKEN_KEY = 'complianceos-auth';

class ApiError extends Error {
  status: number;
  data?: unknown;
  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

function authHeader(): Record<string, string> {
  const token = window.localStorage.getItem(TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...authHeader(),
    ...((init.headers as Record<string, string>) ?? {}),
  };
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) {
      window.localStorage.removeItem(TOKEN_KEY);
    }
    throw new ApiError(res.status, (data as { detail?: string }).detail ?? res.statusText, data);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Auth ────────────────────────────────────────────────────────────────
export interface User {
  username: string;
  email: string;
  role: 'admin' | 'auditor' | 'user';
  display_name: string;
}

export const auth = {
  login: (username: string, password: string) =>
    request<{ token: string; user: User }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  me: () => request<User>('/api/auth/me'),
  logout: () => request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
  setToken: (token: string) => window.localStorage.setItem(TOKEN_KEY, token),
  clearToken: () => window.localStorage.removeItem(TOKEN_KEY),
  hasToken: () => Boolean(window.localStorage.getItem(TOKEN_KEY)),
};

// ── Compliance ──────────────────────────────────────────────────────────
export interface CompanyContext {
  company_name: string;
  sector: string;
  employee_range: string;
  certified: string;
  sites_count: string;
  norms: string[];
}

export interface TraceabilityLink {
  evidence_id: string;
  file_name: string;
  pages: number[];
  excerpt: string;
  relevance_score: number;
}

export interface RemediationPlan {
  what: string;
  who: string;
  when: string;
  effort: 'LOW' | 'MEDIUM' | 'HIGH';
}

export type Severity = 'MAJOR' | 'MINOR' | 'OBSERVATION' | 'CONFORMANT';
export type ActionStatus = 'open' | 'in_progress' | 'closed';

export interface ClauseGap {
  clause_id: string;
  clause_title: string;
  score: number;
  severity: Severity;
  is_spof: boolean;
  finding: string;
  sources: TraceabilityLink[];
  remediation: RemediationPlan;
  status?: ActionStatus;
}

export interface NormGapReport {
  norm: string;
  overall_score: number;
  clauses: ClauseGap[];
  major_count: number;
  minor_count: number;
  observation_count: number;
  conformant_count: number;
  spof_count: number;
}

// ── Phase 2.5: expiry check ─────────────────────────────────────────────
export interface ExpiredDocument {
  file_name: string;
  doc_type: string;
  evidence_id: string;
  expiry_date: string;           // YYYY-MM-DD
  days_overdue: number;          // >0 = expired N days ago, <0 = expires in |N| days
  severity: 'MAJOR' | 'MINOR' | 'OBSERVATION' | 'INFO';
  linked_iso_clauses: string[];  // e.g. ["ISO 45001 §7.2"]
}

export interface ExpiryReport {
  audit_date: string;                       // YYYY-MM-DD
  expired_documents: ExpiredDocument[];     // days_overdue >= 0
  expiring_soon: ExpiredDocument[];         // days_overdue < 0 (within 90 days)
  no_expiry_information: number;
}

// ── Phase 4: executive summary ──────────────────────────────────────────
export interface CompanySnapshot {
  company_name: string;
  sector: string;
  size: string;
  sites_summary: string;
  key_roles: string[];                  // e.g. ["RSPP: Mario Rossi"]
  certified_standards: string[];
  scope_observations: string;
}

export interface ExecutiveSummary {
  company_snapshot: CompanySnapshot;
  top_priority_integrations: string[];  // action-verb sentences, max 10
  executive_narrative: string;          // 3-4 paragraphs UK English
}

export interface AnalysisResult {
  analysis_id: string;
  company: string;
  context: CompanyContext;
  analysis_date: string;
  norms: NormGapReport[];
  documents_analyzed: number;
  top_gaps: ClauseGap[];
  expiry_report?: ExpiryReport | null;            // Phase 2.5 (backend Sprint 2)
  executive_summary?: ExecutiveSummary | null;    // Phase 4 (backend Sprint 4)
}

export interface AnalysisSummary {
  id: string;
  company: string;
  analysis_date: string;
  overall_score?: number;
  major_count?: number;
  minor_count?: number;
  observation_count?: number;
  conformant_count?: number;
  result_json?: string;
}

export interface AnalysisDetail extends AnalysisSummary {
  result?: AnalysisResult;
}

// ── Sprint 3.3: grounded post-audit chat ───────────────────────────────
export interface ChatSource {
  evidence_id: string;
  file_name: string;
  excerpt: string;
  iso_clause_primary: string;
  relevance_score: number;
}

export interface ChatRequest {
  analysis_id: string;
  query: string;
  conversation_id?: string | null;   // reserved for future multi-turn persistence
}

export interface ChatResponse {
  analysis_id: string;
  response: string;
  sources: ChatSource[];
}

export const compliance = {
  listAnalyses: () => request<AnalysisSummary[]>('/api/compliance/analyses'),
  getAnalysis: (id: string) => request<AnalysisDetail>(`/api/compliance/analyses/${id}`),
  updateAction: (id: string, clauseId: string, status: ActionStatus, notes?: string) =>
    request<{ ok: boolean }>(`/api/compliance/analyses/${id}/actions/${clauseId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status, notes: notes ?? '' }),
    }),
  chat: (req: ChatRequest) =>
    request<ChatResponse>('/api/compliance/chat', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  /**
   * Sprint G.3: download report DOCX con auth.
   *
   * Il vecchio `downloadReportUrl(id)` produceva un href statico che il
   * browser apriva senza header Authorization → 401. Ora facciamo fetch
   * con il Bearer token e scarichiamo il blob via object URL.
   *
   * Suggested filename viene dal Content-Disposition se presente, altrimenti
   * fallback su un nome derivato dall'id.
   */
  downloadReport: async (id: string): Promise<{ blob: Blob; filename: string }> => {
    const res = await fetch(`${BASE}/api/compliance/analyses/${id}/download`, {
      headers: { ...authHeader() },
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      if (res.status === 401) {
        window.localStorage.removeItem(TOKEN_KEY);
      }
      throw new ApiError(res.status, (data as { detail?: string }).detail ?? res.statusText, data);
    }
    const blob = await res.blob();
    // Estrai filename dal Content-Disposition se c'è
    const disp = res.headers.get('Content-Disposition') ?? '';
    const m = disp.match(/filename="?([^"]+)"?/i);
    const filename = m?.[1] ?? `ComplianceOS_Report_${id.slice(0, 12)}.docx`;
    return { blob, filename };
  },
};

/**
 * Sprint G.3: helper UI per triggerare il download nel browser
 * a partire da un blob ottenuto via fetch autenticato.
 */
export function triggerBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Revoca dopo un tick per evitare che il browser annulli il download
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ── SSE pipeline ────────────────────────────────────────────────────────
export interface SseProgress {
  pct: number;
  msg: string;
}
export interface SseDone {
  done: true;
  analysis_id: string;
  result: AnalysisResult;
}
export interface SseError {
  error: string;
}
export type SseEvent = SseProgress | SseDone | SseError;

/**
 * Run the compliance analysis pipeline.
 * Backend: POST /api/compliance/analyze (multipart/form-data + SSE response).
 */
export async function runAnalysis(
  file: File,
  context: CompanyContext,
  onEvent: (ev: SseEvent) => void,
): Promise<void> {
  const form = new FormData();
  form.append('file', file);
  form.append('company_name', context.company_name);
  form.append('sector', context.sector);
  form.append('employee_range', context.employee_range);
  form.append('certified', context.certified);
  form.append('sites_count', context.sites_count);
  form.append('norms', JSON.stringify(context.norms));

  const res = await fetch(`${BASE}/api/compliance/analyze`, {
    method: 'POST',
    headers: { ...authHeader() },
    body: form,
  });
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}));
    throw new ApiError(res.status, (data as { detail?: string }).detail ?? res.statusText, data);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames separated by blank line
    let idx: number;
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      if (!frame.trim() || frame.startsWith(':')) continue; // keepalive comment
      const dataLine = frame.split('\n').find((l) => l.startsWith('data: '));
      if (!dataLine) continue;
      const json = dataLine.slice(6).trim();
      try {
        const parsed = JSON.parse(json) as SseEvent;
        onEvent(parsed);
      } catch {
        // ignore malformed frames
      }
    }
  }
}

export { ApiError };
