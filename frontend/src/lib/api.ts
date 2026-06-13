/**
 * Amisys QHSE API client.
 * Backend: FastAPI at /api (proxied through Vite dev server).
 */

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '';
const TOKEN_KEY = 'amisys-auth';

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
  excerpt: string;                  // verbatim quote from the document (Q12)
  relevance_score: number;
  summary?: string | null;          // LLM descriptive summary (Q11), optional
}

export interface RemediationPlan {
  what: string;
  who: string;
  when: string;
  effort: 'LOW' | 'MEDIUM' | 'HIGH';
  // Sprint R4 (PRD 1.4.7) — two-level remediation
  correction?: string | null;          // immediate fix for the instance
  corrective_action?: string | null;   // systemic fix preventing recurrence
}

export type Severity = 'MAJOR' | 'MINOR' | 'OBSERVATION' | 'CONFORMANT';
export type ActionStatus = 'open' | 'in_progress' | 'closed';

// Sprint R4 — one atomic requirement verified by the deep pass
export interface RequirementCheck {
  requirement_id: string;
  status: 'PRESENT' | 'PARTIAL' | 'ABSENT';
  evidence_quote?: string | null;
  pages: number[];
  file_name?: string | null;
  note?: string | null;
}

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
  // Sprint R4 — reasoning exposure (PRD 1.4.6)
  confidence?: number | null;
  requirement_checks?: RequirementCheck[];
  hedged?: boolean;
  hedge_note?: string | null;
  deep_verified?: boolean;
  // Fase 4 — overlay dal registro NC (merge in lettura, PRD 1.4.8)
  dismissed?: boolean;
  dismiss_reason?: string | null;
  nc_id?: number;
}

// Fase 4 — NC inserita a mano dal manager (PRD 1.4.8)
export interface ManualNonconformity {
  id: number;
  analysis_id: string;
  clause_id: string | null;
  source: 'manual';
  title: string;
  description: string;
  severity: Severity | 'OBSERVATION';
  status: ActionStatus;
  dismissed: number;          // 0 | 1 (SQLite)
  dismiss_reason: string;
  created_by: string;
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

// Sprint R3 — Phase 2.6 documented-information coverage
export interface DocumentedInfoItem {
  item: string;
  clause_id: string;
  norm: string;
  retain_or_maintain: 'MAINTAIN' | 'RETAIN';
  status: 'FOUND' | 'FOUND_WEAK' | 'ABSENT';
  matched_evidence_id?: string | null;
  matched_file_name?: string | null;
  match_method: string;
  risk_if_missing: 'MAJOR' | 'MINOR';
}

export interface DocumentedInfoReport {
  items: DocumentedInfoItem[];
  found_count: number;
  weak_count: number;
  absent_count: number;
}

// Sprint R5 — Phase 3.5 cross-clause coherence
export interface CrossClauseFinding {
  chain_id: string;
  norm: string;
  title: string;
  status: 'LINKED' | 'PARTIAL' | 'BROKEN' | 'NOT_ASSESSABLE';
  narrative: string;
  clause_ids: string[];
  sources: TraceabilityLink[];
}

// Fase A — Phase 2.7 structured risk register (Sprint R8)
export interface RiskRegisterEntry {
  ref?: string | null;
  description: string;
  category?: string | null;          // 'risk' | 'opportunity' (free text from extraction)
  score?: string | null;
  score_present: boolean;
  mitigation?: string | null;
  mitigation_present: boolean;
  owner?: string | null;
  owner_present: boolean;
  pages: number[];
}

export interface RiskRegisterDocument {
  file_name: string;
  evidence_id: string;
  methodology?: string | null;
  methodology_declared: boolean;
  risks: RiskRegisterEntry[];
}

export interface RiskRegisterExtract {
  documents: RiskRegisterDocument[];
  total_risks: number;
  unscored_count: number;
  unmitigated_count: number;
  unowned_count: number;
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
  documented_info_report?: DocumentedInfoReport | null;  // Phase 2.6 (Sprint R3)
  cross_clause_findings?: CrossClauseFinding[];          // Phase 3.5 (Sprint R5)
  risk_register_extract?: RiskRegisterExtract | null;    // Phase 2.7 (Sprint R8)
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
  manual_nonconformities?: ManualNonconformity[];  // Fase 4
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
  analysis_id: string | null;        // null → chat general senza grounding
  query: string;
  conversation_id?: string | null;
  // Fase 6 — multi-turn: ultimi turni (max 6 usati dal backend) come contesto
  messages?: { role: 'user' | 'assistant'; content: string }[];
}

export interface ChatResponse {
  analysis_id: string | null;
  response: string;
  sources: ChatSource[];
}

// Fase 5 — Delta / Compare
export interface ClauseDelta {
  clause_id: string;
  clause_title: string;
  score_old: number | null;
  score_new: number | null;
  delta: number | null;
  severity_old: Severity | null;
  severity_new: Severity | null;
  severity_changed: boolean;
  direction: 'improved' | 'regressed' | 'unchanged' | 'new' | 'removed';
}

export interface NormDelta {
  norm: string;
  overall_new: number | null;
  overall_old: number | null;
  overall_delta: number | null;
}

export interface AnalysisDelta {
  analysis_new: string;
  analysis_old: string;
  company: string;
  date_new: string;
  date_old: string;
  norms: NormDelta[];
  clauses: ClauseDelta[];
  summary: {
    improved: number;
    regressed: number;
    unchanged: number;
    new: number;
    removed: number;
    severity_upgrades: number;
    severity_downgrades: number;
  };
  documented_info: { resolved: string[]; newly_missing: string[] } | null;
}

// Fase 7 — criteri operativi custom (PRD 1.4.4b)
export interface RequirementSet {
  name: string;
  label: string;
  description: string;
  requirement_count: number;
}

export interface PqqAnswer {
  question: string;
  answer: string;
  status: 'answered' | 'needs_input';
  sources: ChatSource[];
}

export const compliance = {
  listAnalyses: () => request<AnalysisSummary[]>('/api/compliance/analyses'),
  listRequirementSets: () => request<RequirementSet[]>('/api/compliance/requirement-sets'),
  getDelta: (id: string, against: string) =>
    request<AnalysisDelta>(`/api/compliance/analyses/${id}/delta?against=${encodeURIComponent(against)}`),
  getAnalysis: (id: string) => request<AnalysisDetail>(`/api/compliance/analyses/${id}`),
  updateAction: (id: string, clauseId: string, status: ActionStatus, notes?: string) =>
    request<{ ok: boolean }>(`/api/compliance/analyses/${id}/actions/${clauseId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status, notes: notes ?? '' }),
    }),
  // Fase 4 — registro NC (PRD 1.4.8)
  addManualNC: (id: string, title: string, description: string, severity: string) =>
    request<{ ok: boolean; nc_id: number }>(`/api/compliance/analyses/${id}/nonconformities`, {
      method: 'POST',
      body: JSON.stringify({ title, description, severity }),
    }),
  dismissNC: (id: string, ncId: number, reason: string) =>
    request<{ ok: boolean }>(`/api/compliance/analyses/${id}/nonconformities/${ncId}/dismiss`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  restoreNC: (id: string, ncId: number) =>
    request<{ ok: boolean }>(`/api/compliance/analyses/${id}/nonconformities/${ncId}/restore`, {
      method: 'POST',
    }),
  chat: (req: ChatRequest) =>
    request<ChatResponse>('/api/compliance/chat', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  // Fase H — PQQ/SQ tender assistant
  pqq: (analysisId: string, questions: string[]) =>
    request<{ analysis_id: string; answers: PqqAnswer[] }>('/api/compliance/pqq', {
      method: 'POST',
      body: JSON.stringify({ analysis_id: analysisId, questions }),
    }),
  pqqExport: async (company: string, items: { question: string; answer: string; status: string }[]): Promise<{ blob: Blob; filename: string }> => {
    const res = await fetch(`${BASE}/api/compliance/pqq/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeader() },
      body: JSON.stringify({ company, items }),
    });
    if (!res.ok) throw new ApiError(res.status, res.statusText);
    const disp = res.headers.get('Content-Disposition') ?? '';
    const m = disp.match(/filename="?([^"]+)"?/i);
    return { blob: await res.blob(), filename: m?.[1] ?? 'PQQ_draft.docx' };
  },

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
    const filename = m?.[1] ?? `AmisysQHSE_Report_${id.slice(0, 12)}.docx`;
    return { blob, filename };
  },
};

// ── DMS (Fase C) ──────────────────────────────────────────────────────────
export interface DmsFolder {
  id: number;
  owner: string;
  parent_id: number | null;
  name: string;
  retention_days: number | null;
  created_at: string;
}

export interface DmsDocument {
  id: number;
  owner: string;
  folder_id: number | null;
  filename: string;
  doc_type: string | null;
  doc_type_source: 'heuristic' | 'engine' | 'manual';
  expiry_date: string | null;
  current_version: number;
  size: number;
  content_chars: number;
  uploaded_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface DmsVersion {
  id: number;
  document_id: number;
  version: number;
  size: number;
  content_chars: number;
  uploaded_by: string | null;
  uploaded_at: string;
  note: string;
}

export interface ImportZipResult {
  ok: boolean;
  imported: number;
  versioned: number;
  skipped: number;
}

export interface RegisterEntry {
  id: number;
  filename: string;
  doc_type: string | null;
  tier: string;
  version: number;
  expiry_date: string | null;
  updated_at: string;
  folder_id: number | null;
}

export interface PyramidTier {
  tier: string;
  count: number;
  documents: RegisterEntry[];
}

export interface PyramidResult {
  tiers: PyramidTier[];
  empty_tiers: string[];
  total: number;
}

export const dms = {
  listFolders: () => request<{ folders: DmsFolder[] }>('/api/dms/folders'),
  createFolder: (name: string, parent_id?: number | null, retention_days?: number | null) =>
    request<{ ok: boolean; folder_id: number }>('/api/dms/folders', {
      method: 'POST',
      body: JSON.stringify({ name, parent_id: parent_id ?? null, retention_days: retention_days ?? null }),
    }),
  patchFolder: (id: number, body: { name?: string; parent_id?: number | null; retention_days?: number | null; move?: boolean }) =>
    request<{ ok: boolean }>(`/api/dms/folders/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteFolder: (id: number) => request<{ ok: boolean }>(`/api/dms/folders/${id}`, { method: 'DELETE' }),

  listDocuments: (folderId?: number | null) =>
    request<{ documents: DmsDocument[] }>(
      folderId != null ? `/api/dms/documents?folder_id=${folderId}` : '/api/dms/documents',
    ),
  getDocument: (id: number) =>
    request<{ document: DmsDocument; versions: DmsVersion[] }>(`/api/dms/documents/${id}`),
  patchDocument: (id: number, body: { doc_type?: string; expiry_date?: string; folder_id?: number; filename?: string; move?: boolean }) =>
    request<{ ok: boolean }>(`/api/dms/documents/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteDocument: (id: number) => request<{ ok: boolean }>(`/api/dms/documents/${id}`, { method: 'DELETE' }),
  restoreDocument: (id: number) =>
    request<{ ok: boolean }>(`/api/dms/documents/${id}/restore`, { method: 'POST' }),
  search: (q: string) => request<{ documents: DmsDocument[] }>(`/api/dms/search?q=${encodeURIComponent(q)}`),

  register: () => request<{ register: RegisterEntry[] }>('/api/dms/register'),
  pyramid: () => request<PyramidResult>('/api/dms/pyramid'),
  exportRegister: async (): Promise<{ blob: Blob; filename: string }> => {
    const res = await fetch(`${BASE}/api/dms/register/export`, { headers: { ...authHeader() } });
    if (!res.ok) throw new ApiError(res.status, res.statusText);
    return { blob: await res.blob(), filename: 'document_register.xlsx' };
  },

  upload: async (file: File, folderId?: number | null): Promise<{ ok: boolean; document_id: number; version: number; deduped: boolean }> => {
    const form = new FormData();
    form.append('file', file);
    if (folderId != null) form.append('folder_id', String(folderId));
    const res = await fetch(`${BASE}/api/dms/documents`, { method: 'POST', headers: { ...authHeader() }, body: form });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new ApiError(res.status, (data as { detail?: string }).detail ?? res.statusText, data);
    }
    return res.json();
  },

  importZip: async (file: File, folderId?: number | null): Promise<ImportZipResult> => {
    const form = new FormData();
    form.append('file', file);
    if (folderId != null) form.append('folder_id', String(folderId));
    const res = await fetch(`${BASE}/api/dms/import-zip`, { method: 'POST', headers: { ...authHeader() }, body: form });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new ApiError(res.status, (data as { detail?: string }).detail ?? res.statusText, data);
    }
    return res.json();
  },

  download: async (id: number, version?: number): Promise<{ blob: Blob; filename: string }> => {
    const url = version != null
      ? `${BASE}/api/dms/documents/${id}/download?version=${version}`
      : `${BASE}/api/dms/documents/${id}/download`;
    const res = await fetch(url, { headers: { ...authHeader() } });
    if (!res.ok) {
      throw new ApiError(res.status, res.statusText);
    }
    const blob = await res.blob();
    const disp = res.headers.get('Content-Disposition') ?? '';
    const m = disp.match(/filename="?([^"]+)"?/i);
    return { blob, filename: m?.[1] ?? `document_${id}` };
  },
};

// ── Tasks (Fase F) ──────────────────────────────────────────────────────────
export type Rag = 'red' | 'amber' | 'green' | 'done' | 'snoozed';

export interface Task {
  task_key: string;
  source: 'nonconformity' | 'expiry' | 'manual';
  title: string;
  severity: string | null;
  due_date: string | null;
  link: string;
  rag: Rag;
  done: boolean;
  snoozed_until: string | null;
  analysis_id?: string;
  clause_id?: string;
}

export const tasks = {
  list: () => request<{ tasks: Task[]; counts: Record<string, number> }>('/api/tasks'),
  setDone: (taskKey: string, done: boolean) =>
    request<{ ok: boolean }>(`/api/tasks/${encodeURIComponent(taskKey)}/done`, {
      method: 'POST', body: JSON.stringify({ done }),
    }),
  snooze: (taskKey: string, until: string) =>
    request<{ ok: boolean }>(`/api/tasks/${encodeURIComponent(taskKey)}/snooze`, {
      method: 'POST', body: JSON.stringify({ until }),
    }),
  addManual: (title: string, due_date?: string | null) =>
    request<{ ok: boolean; task_id: number }>('/api/tasks', {
      method: 'POST', body: JSON.stringify({ title, due_date: due_date ?? null }),
    }),
  deleteManual: (taskId: number) =>
    request<{ ok: boolean }>(`/api/tasks/manual/${taskId}`, { method: 'DELETE' }),
};

// ── Notifications (Fase E) ──────────────────────────────────────────────────
export interface AppNotification {
  id: number;
  username: string;
  kind: string;
  severity: string | null;
  title: string;
  body: string | null;
  link: string | null;
  entity_ref: string | null;
  created_at: string;
  read_at: string | null;
}

export const notifications = {
  list: (unreadOnly = false) =>
    request<{ notifications: AppNotification[]; unread: number }>(
      `/api/notifications?unread_only=${unreadOnly}`,
    ),
  unreadCount: () => request<{ unread: number }>('/api/notifications/unread-count'),
  markRead: (id: number) =>
    request<{ ok: boolean; unread: number }>(`/api/notifications/${id}/read`, { method: 'POST' }),
  markAllRead: () =>
    request<{ ok: boolean; marked: number }>('/api/notifications/read-all', { method: 'POST' }),
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
  await readSseStream(res, onEvent);
}

/**
 * Re-run the pipeline on the saved corpus of an existing analysis.
 * Backend: POST /api/compliance/analyses/{id}/reanalyse (SSE response).
 * Produces a NEW analysis row — the done event carries the new analysis_id.
 */
export async function runReanalyse(
  analysisId: string,
  onEvent: (ev: SseEvent) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/api/compliance/analyses/${encodeURIComponent(analysisId)}/reanalyse`, {
    method: 'POST',
    headers: { ...authHeader() },
  });
  await readSseStream(res, onEvent);
}

export interface AnalyzeDmsRequest {
  company_name: string;
  sector: string;
  employee_range: string;
  certified: string;
  sites_count: string;
  norms: string[];
  scope: 'all' | 'folder' | 'updated_since';
  folder_id?: number | null;
  updated_since?: string | null;
}

/**
 * Run the pipeline on documents already in the DMS (PRD §1.4.3 scan scoping).
 * Backend: POST /api/compliance/analyze-dms (JSON body, SSE response).
 */
export async function runAnalyzeDms(
  req: AnalyzeDmsRequest,
  onEvent: (ev: SseEvent) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/api/compliance/analyze-dms`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeader() },
    body: JSON.stringify(req),
  });
  await readSseStream(res, onEvent);
}

/** Shared SSE frame reader (fetch body → parsed events). */
async function readSseStream(res: Response, onEvent: (ev: SseEvent) => void): Promise<void> {
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
