/**
 * Documented Information Coverage — Phase 2.6 (Sprint R3/R6).
 *
 * Shows whether the documented information the standards OBLIGE the company
 * to maintain/retain was found in the package. ABSENT items first (they are
 * the findings), weak matches next, found items summarised in the footer.
 * Reuses the expiry-table look: collapsible section, severity-tinted rows.
 */
import { useState } from 'react';
import type { DocumentedInfoReport, DocumentedInfoItem } from '@/lib/api';

interface Props {
  report: DocumentedInfoReport;
}

function ChevronIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function lastPathSegment(path: string | null | undefined): string {
  if (!path) return '';
  const normalised = path.replace(/\\/g, '/');
  const idx = normalised.lastIndexOf('/');
  return idx >= 0 ? normalised.slice(idx + 1) : normalised;
}

function methodLabel(item: DocumentedInfoItem): string {
  switch (item.match_method) {
    case 'metadata':             return 'matched by content classification';
    case 'semantic':             return 'matched by semantic search';
    case 'llm_rescued':          return 'matched under a different name';
    case 'llm_confirmed_absent': return 'absence confirmed across the package';
    default:                     return 'not found';
  }
}

function rowClass(item: DocumentedInfoItem): string {
  if (item.status === 'ABSENT') {
    return item.risk_if_missing === 'MAJOR' ? 'expiry-row-major' : 'expiry-row-minor';
  }
  return 'expiry-row-obs'; // FOUND_WEAK — needs a human glance
}

export function DocumentedInfoSection({ report }: Props) {
  const absent = report.items.filter((i) => i.status === 'ABSENT');
  const weak = report.items.filter((i) => i.status === 'FOUND_WEAK');
  const [expanded, setExpanded] = useState(absent.length > 0);

  if (absent.length === 0 && weak.length === 0) return null;

  return (
    <section className={`expiry-section${expanded ? ' expanded' : ''}`}>
      <button
        type="button"
        className="expiry-head"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <span className="expiry-head-title">Required documented information</span>
        <span className="expiry-head-counts">
          {absent.length > 0 && (
            <span className="expiry-count expiry-count-expired">
              {absent.length} not found
            </span>
          )}
          {weak.length > 0 && (
            <span className="expiry-count expiry-count-soon">
              {weak.length} weak match{weak.length === 1 ? '' : 'es'}
            </span>
          )}
        </span>
        <ChevronIcon />
      </button>

      {expanded && (
        <div className="expiry-body">
          <div className="expiry-table-wrap">
            <table className="expiry-table">
              <thead>
                <tr>
                  <th>Required item</th>
                  <th>Standard</th>
                  <th>Kind</th>
                  <th>Status</th>
                  <th>How it was checked</th>
                </tr>
              </thead>
              <tbody>
                {[...absent, ...weak].map((item) => (
                  <tr key={`${item.norm}-${item.item}`} className={rowClass(item)}>
                    <td>{item.item}</td>
                    <td className="expiry-doctype">{item.norm.replace(/:\d{4}$/, '')}</td>
                    <td className="expiry-doctype">{item.retain_or_maintain.toLowerCase()}</td>
                    <td>
                      {item.status === 'ABSENT' ? (
                        <span className={`badge badge-${item.risk_if_missing.toLowerCase()}`}>
                          Not found
                        </span>
                      ) : (
                        <span className="badge badge-obs">Weak match</span>
                      )}
                    </td>
                    <td className="expiry-days">
                      {item.status === 'FOUND_WEAK' && item.matched_file_name
                        ? `${lastPathSegment(item.matched_file_name)} · ${methodLabel(item)}`
                        : methodLabel(item)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="expiry-footnote">
            {report.found_count} required item{report.found_count === 1 ? ' was' : 's were'} found
            in the package by content classification — file names are never used for this check.
          </p>
        </div>
      )}
    </section>
  );
}
