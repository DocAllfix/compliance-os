/**
 * Documents (DMS) — Fase C, PRD §1.2 / §1.3.2.
 *
 * Repository documentale per account: albero cartelle a sinistra, documenti
 * della cartella selezionata a destra con tipo, scadenza, versione corrente.
 * Upload drag-free (input file), import ZIP, download, soft-delete, changelog
 * versioni. Stile sobrio DESIGN.md (riusa token/classi esistenti).
 */
import { useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useDmsFolders, useDmsDocuments } from '@/lib/hooks';
import { dms, triggerBrowserDownload, ApiError, type DmsFolder, type DmsDocument } from '@/lib/api';

type View = 'folders' | 'register' | 'pyramid';

function fmtDate(s: string | null): string {
  if (!s) return '—';
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

function fmtType(t: string | null): string {
  if (!t) return 'Unclassified';
  return t.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function expiryClass(expiry: string | null): string {
  if (!expiry) return '';
  const days = Math.ceil((new Date(expiry).getTime() - Date.now()) / 86400000);
  if (isNaN(days)) return '';
  if (days < 0) return 'expiry-row-major';
  if (days <= 30) return 'expiry-row-minor';
  if (days <= 90) return 'expiry-row-obs';
  return '';
}

function RegisterView() {
  const { data, isLoading } = useQuery({ queryKey: ['dms-register'], queryFn: () => dms.register() });
  const rows = data?.register ?? [];
  const exportXlsx = async () => {
    const { blob, filename } = await dms.exportRegister();
    triggerBrowserDownload(blob, filename);
  };
  if (isLoading) return <p className="dms-hint">Loading…</p>;
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <button className="btn btn-secondary" onClick={exportXlsx} disabled={rows.length === 0}>Export XLSX</button>
      </div>
      {rows.length === 0 ? (
        <div className="dms-empty"><p>No documents yet.</p></div>
      ) : (
        <table className="expiry-table dms-table">
          <thead><tr><th>Document</th><th>Type</th><th>Tier</th><th>Version</th><th>Expiry</th><th>Updated</th></tr></thead>
          <tbody>
            {rows.map((d) => (
              <tr key={d.id}>
                <td>{d.filename}</td>
                <td className="expiry-doctype">{(d.doc_type ?? 'unclassified').replace(/_/g, ' ')}</td>
                <td className="expiry-doctype">{d.tier}</td>
                <td className="expiry-days">v{d.version}</td>
                <td>{d.expiry_date ?? '—'}</td>
                <td className="expiry-doctype">{String(d.updated_at ?? '').slice(0, 10)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function PyramidView() {
  const { data, isLoading } = useQuery({ queryKey: ['dms-pyramid'], queryFn: () => dms.pyramid() });
  if (isLoading) return <p className="dms-hint">Loading…</p>;
  const tiers = data?.tiers ?? [];
  const maxCount = Math.max(1, ...tiers.map((t) => t.count));
  return (
    <div className="pyramid">
      {tiers.map((t, i) => (
        <div key={t.tier} className="pyramid-tier" style={{ width: `${55 + (i / Math.max(1, tiers.length - 1)) * 45}%` }}>
          <div className={`pyramid-bar${t.count === 0 ? ' empty' : ''}`}>
            <span className="pyramid-tier-name">{t.tier}</span>
            <span className="pyramid-tier-count">{t.count}</span>
            <div className="pyramid-fill" style={{ width: `${(t.count / maxCount) * 100}%` }} />
          </div>
          {t.count === 0 && <span className="pyramid-empty-note">No documents identified at this level</span>}
        </div>
      ))}
    </div>
  );
}

export function Documents() {
  const qc = useQueryClient();
  const foldersQuery = useDmsFolders();
  const [view, setView] = useState<View>('folders');
  const [activeFolder, setActiveFolder] = useState<number | null>(null);
  const docsQuery = useDmsDocuments(activeFolder);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const uploadRef = useRef<HTMLInputElement>(null);
  const zipRef = useRef<HTMLInputElement>(null);

  const folders = foldersQuery.data?.folders ?? [];
  const documents = docsQuery.data?.documents ?? [];

  // Albero: raggruppa per parent_id (un livello di nidificazione visibile,
  // i figli indentati — sufficiente per l'MVP).
  const roots = useMemo(() => folders.filter((f) => f.parent_id == null), [folders]);
  const childrenOf = (id: number) => folders.filter((f) => f.parent_id === id);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['dms-folders'] });
    qc.invalidateQueries({ queryKey: ['dms-documents'] });
  };

  const wrap = async (label: string, fn: () => Promise<void>) => {
    setBusy(label);
    setErr(null);
    try {
      await fn();
      refresh();
    } catch (e) {
      setErr(e instanceof ApiError ? `${e.status} ${e.message}` : (e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const newFolder = () => {
    const name = window.prompt('Folder name');
    if (!name?.trim()) return;
    wrap('folder', async () => { await dms.createFolder(name.trim(), activeFolder); });
  };

  const onUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (!files.length) return;
    wrap('upload', async () => {
      for (const f of files) await dms.upload(f, activeFolder);
    }).finally(() => { if (uploadRef.current) uploadRef.current.value = ''; });
  };

  const onImportZip = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    wrap('zip', async () => {
      const r = await dms.importZip(f, activeFolder);
      window.alert(`Imported ${r.imported}, new versions ${r.versioned}, skipped ${r.skipped}.`);
    }).finally(() => { if (zipRef.current) zipRef.current.value = ''; });
  };

  const download = (doc: DmsDocument) =>
    wrap('download', async () => {
      const { blob, filename } = await dms.download(doc.id);
      triggerBrowserDownload(blob, filename);
    });

  const remove = (doc: DmsDocument) => {
    if (!window.confirm(`Move "${doc.filename}" to deleted? It can be restored.`)) return;
    wrap('delete', async () => { await dms.deleteDocument(doc.id); });
  };

  const deleteFolder = (f: DmsFolder) => {
    if (!window.confirm(`Delete folder "${f.name}" and its documents? They can be restored individually.`)) return;
    wrap('folder', async () => {
      await dms.deleteFolder(f.id);
      if (activeFolder === f.id) setActiveFolder(null);
    });
  };

  const FolderRow = ({ f, depth }: { f: DmsFolder; depth: number }) => (
    <div>
      <div
        className={`dms-folder${activeFolder === f.id ? ' active' : ''}`}
        style={{ paddingLeft: 10 + depth * 16 }}
        onClick={() => setActiveFolder(f.id)}
      >
        <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        </svg>
        <span className="dms-folder-name">{f.name}</span>
        <button className="dms-folder-del" title="Delete folder"
          onClick={(e) => { e.stopPropagation(); deleteFolder(f); }}>×</button>
      </div>
      {childrenOf(f.id).map((c) => <FolderRow key={c.id} f={c} depth={depth + 1} />)}
    </div>
  );

  return (
    <div className="main-wide-inner">
      <header className="compact-header">
        <div>
          <div className="eyebrow">Document management</div>
          <h1 className="page-title">Documents</h1>
          <div className="page-meta">
            Your QHSE documentation. Analyse a folder from here, or run a new analysis.
          </div>
        </div>
        <div className="header-actions">
          <button className="btn btn-secondary" onClick={newFolder} disabled={!!busy}>New folder</button>
          <button className="btn btn-secondary" onClick={() => zipRef.current?.click()} disabled={!!busy}>
            {busy === 'zip' ? 'Importing…' : 'Import ZIP'}
          </button>
          <button className="btn btn-accent" onClick={() => uploadRef.current?.click()} disabled={!!busy}>
            {busy === 'upload' ? 'Uploading…' : 'Upload'}
          </button>
          <input ref={uploadRef} type="file" multiple hidden onChange={onUpload} />
          <input ref={zipRef} type="file" accept=".zip" hidden onChange={onImportZip} />
        </div>
      </header>

      {err && <div className="dms-error">{err}</div>}

      <div className="source-toggle" style={{ marginTop: 16 }}>
        <button className={`source-tab${view === 'folders' ? ' active' : ''}`} onClick={() => setView('folders')}>Folders</button>
        <button className={`source-tab${view === 'register' ? ' active' : ''}`} onClick={() => setView('register')}>Register</button>
        <button className={`source-tab${view === 'pyramid' ? ' active' : ''}`} onClick={() => setView('pyramid')}>Pyramid</button>
      </div>

      {view === 'register' ? (
        <div style={{ marginTop: 16 }}><RegisterView /></div>
      ) : view === 'pyramid' ? (
        <div style={{ marginTop: 16 }}><PyramidView /></div>
      ) : (
      <div className="dms-layout">
        <aside className="dms-sidebar">
          <div
            className={`dms-folder${activeFolder === null ? ' active' : ''}`}
            onClick={() => setActiveFolder(null)}
          >
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
            <span className="dms-folder-name">All documents</span>
          </div>
          {roots.map((f) => <FolderRow key={f.id} f={f} depth={0} />)}
          {folders.length === 0 && (
            <p className="dms-hint">No folders yet. Create one to organise your documents.</p>
          )}
        </aside>

        <section className="dms-main">
          {docsQuery.isLoading ? (
            <p className="dms-hint">Loading…</p>
          ) : documents.length === 0 ? (
            <div className="dms-empty">
              <p>No documents in this view.</p>
              <p className="dms-hint">Upload files or import a ZIP to get started.</p>
            </div>
          ) : (
            <table className="expiry-table dms-table">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Type</th>
                  <th>Expiry</th>
                  <th>Version</th>
                  <th>Updated</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {documents.map((d) => (
                  <tr key={d.id} className={expiryClass(d.expiry_date)}>
                    <td>{d.filename}</td>
                    <td className="expiry-doctype">
                      {fmtType(d.doc_type)}
                      {d.doc_type_source === 'heuristic' && (
                        <span className="dms-tag" title="Provisional type — confirmed when you analyse">auto</span>
                      )}
                    </td>
                    <td>{fmtDate(d.expiry_date)}</td>
                    <td className="expiry-days">v{d.current_version}</td>
                    <td className="expiry-doctype">{fmtDate(d.updated_at)}</td>
                    <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                      <button className="btn btn-link" onClick={() => download(d)}>Download</button>
                      <button className="btn btn-link" onClick={() => remove(d)}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
      )}
    </div>
  );
}
