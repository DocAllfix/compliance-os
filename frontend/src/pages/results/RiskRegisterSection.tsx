/**
 * Risk Register — Phase 2.7 (Sprint R8, Fase A surface).
 *
 * Structured extraction from the risk documents in the package: one row per
 * identified risk, with score / mitigation / owner as data fields. Missing
 * fields (incl. "to be defined" placeholders) are flagged deterministically
 * by the engine; here they render as Minor-tinted cells so the manager can
 * see at a glance which risks are not fully managed.
 * Reuses the collapsible expiry-section look.
 */
import { useState } from 'react';
import type { RiskRegisterExtract, RiskRegisterEntry } from '@/lib/api';

interface Props {
  register: RiskRegisterExtract;
}

function ChevronIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function fieldCell(value: string | null | undefined, present: boolean, missingLabel: string) {
  if (present && value) return <td>{value}</td>;
  return (
    <td>
      <span className="badge badge-minor">{missingLabel}</span>
      {value ? <span style={{ marginLeft: 6, color: 'var(--text-tertiary)' }}>{value}</span> : null}
    </td>
  );
}

function entryKey(e: RiskRegisterEntry, idx: number): string {
  return e.ref ?? `${idx}-${e.description.slice(0, 24)}`;
}

export function RiskRegisterSection({ register }: Props) {
  const flagged = register.unscored_count + register.unmitigated_count + register.unowned_count;
  const [expanded, setExpanded] = useState(flagged > 0);

  if (register.total_risks === 0) return null;

  return (
    <section className={`expiry-section${expanded ? ' expanded' : ''}`}>
      <button
        type="button"
        className="expiry-head"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <span className="expiry-head-title">Risk register</span>
        <span className="expiry-head-counts">
          <span className="expiry-count">
            {register.total_risks} risk{register.total_risks === 1 ? '' : 's'} identified
          </span>
          {flagged > 0 && (
            <span className="expiry-count expiry-count-soon">
              {register.unmitigated_count > 0 && `${register.unmitigated_count} without mitigation`}
              {register.unmitigated_count > 0 && register.unowned_count > 0 && ' · '}
              {register.unowned_count > 0 && `${register.unowned_count} without owner`}
            </span>
          )}
        </span>
        <ChevronIcon />
      </button>

      {expanded && (
        <div className="expiry-body">
          {register.documents.map((doc) => (
            <div key={doc.evidence_id || doc.file_name} style={{ marginBottom: 18 }}>
              <div className="section-title" style={{ marginBottom: 8 }}>
                <span className="finding-clause-id">{doc.file_name}</span>
                <span className="count">
                  {doc.methodology_declared && doc.methodology
                    ? `methodology: ${doc.methodology}`
                    : 'no scoring methodology declared'}
                </span>
              </div>
              <div className="expiry-table-wrap">
                <table className="expiry-table">
                  <thead>
                    <tr>
                      <th>Ref</th>
                      <th>Risk</th>
                      <th>Score</th>
                      <th>Mitigation</th>
                      <th>Owner</th>
                    </tr>
                  </thead>
                  <tbody>
                    {doc.risks.map((r, idx) => {
                      const incomplete = !r.score_present || !r.mitigation_present || !r.owner_present;
                      return (
                        <tr key={entryKey(r, idx)} className={incomplete ? 'expiry-row-minor' : ''}>
                          <td className="expiry-doctype">{r.ref ?? '·'}</td>
                          <td>
                            {r.description}
                            {r.category === 'opportunity' && (
                              <span className="badge badge-conf" style={{ marginLeft: 6 }}>Opportunity</span>
                            )}
                          </td>
                          {fieldCell(r.score, r.score_present, 'Unscored')}
                          {fieldCell(r.mitigation, r.mitigation_present, 'Not defined')}
                          {fieldCell(r.owner, r.owner_present, 'Unassigned')}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
          <p className="expiry-footnote">
            Extracted from the risk documents in the package. Placeholder text such as
            "to be defined" counts as missing: a risk is only managed when score,
            mitigation and owner are all in place.
          </p>
        </div>
      )}
    </section>
  );
}
