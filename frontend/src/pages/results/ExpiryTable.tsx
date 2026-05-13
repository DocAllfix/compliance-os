/**
 * Document Expiry Status — Phase 2.5 section §3.
 *
 * Two tables: documents already expired (days_overdue >= 0, sorted most-overdue first)
 * and documents expiring within 90 days (days_overdue < 0). Each row tinted by
 * severity using the existing OKLCH design tokens.
 */
import { useState } from 'react';
import type { ExpiryReport, ExpiredDocument } from '@/lib/api';

interface Props {
  report: ExpiryReport;
}

function ChevronIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function FileIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

function lastPathSegment(path: string): string {
  if (!path) return '';
  const normalised = path.replace(/\\/g, '/');
  const idx = normalised.lastIndexOf('/');
  return idx >= 0 ? normalised.slice(idx + 1) : normalised;
}

function formatDays(rec: ExpiredDocument): string {
  const days = Math.abs(rec.days_overdue);
  if (rec.days_overdue > 0)  return `${days} day${days === 1 ? '' : 's'} ago`;
  if (rec.days_overdue === 0) return 'Today';
  return `In ${days} day${days === 1 ? '' : 's'}`;
}

function severityClass(sev: ExpiredDocument['severity']): string {
  switch (sev) {
    case 'MAJOR':       return 'expiry-row-major';
    case 'MINOR':       return 'expiry-row-minor';
    case 'OBSERVATION': return 'expiry-row-obs';
    default:            return 'expiry-row-info';
  }
}

function Table({ rows, headerColumn }: { rows: ExpiredDocument[]; headerColumn: string }) {
  return (
    <div className="expiry-table-wrap">
      <table className="expiry-table">
        <thead>
          <tr>
            <th>File</th>
            <th>Doc type</th>
            <th>Expiry</th>
            <th>{headerColumn}</th>
            <th>Severity</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.evidence_id} className={severityClass(r.severity)}>
              <td>
                <span className="expiry-file">
                  <FileIcon />
                  {lastPathSegment(r.file_name)}
                </span>
              </td>
              <td className="expiry-doctype">{r.doc_type.replace(/_/g, ' ')}</td>
              <td className="expiry-date">{r.expiry_date}</td>
              <td className="expiry-days">{formatDays(r)}</td>
              <td>
                <span className={`badge badge-${r.severity.toLowerCase()}`}>{r.severity}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ExpiryTable({ report }: Props) {
  const totalCount = report.expired_documents.length + report.expiring_soon.length;
  const [expanded, setExpanded] = useState(totalCount > 0);

  if (totalCount === 0) return null;

  return (
    <section className={`expiry-section${expanded ? ' expanded' : ''}`}>
      <button
        type="button"
        className="expiry-head"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <span className="expiry-head-title">Document expiry status</span>
        <span className="expiry-head-counts">
          {report.expired_documents.length > 0 && (
            <span className="expiry-count expiry-count-expired">
              {report.expired_documents.length} expired
            </span>
          )}
          {report.expiring_soon.length > 0 && (
            <span className="expiry-count expiry-count-soon">
              {report.expiring_soon.length} expiring soon
            </span>
          )}
        </span>
        <ChevronIcon />
      </button>

      {expanded && (
        <div className="expiry-body">
          {report.expired_documents.length > 0 && (
            <>
              <div className="expiry-subheader">Expired</div>
              <Table rows={report.expired_documents} headerColumn="Overdue" />
            </>
          )}

          {report.expiring_soon.length > 0 && (
            <>
              <div className="expiry-subheader">Expiring within 90 days</div>
              <Table rows={report.expiring_soon} headerColumn="Time to expiry" />
            </>
          )}

          {report.no_expiry_information > 0 && (
            <p className="expiry-footnote">
              {report.no_expiry_information} document
              {report.no_expiry_information === 1 ? '' : 's'} carry no expiry
              information and could not be checked.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
