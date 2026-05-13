/**
 * Company Snapshot card — Phase 4 section §1 of the manager-facing report.
 *
 * Renders structured anagrafica + key roles + scope observations from the
 * backend's ExecutiveSummary.company_snapshot. Pure presentation, no state.
 */
import type { CompanySnapshot } from '@/lib/api';

interface Props {
  snapshot: CompanySnapshot;
}

export function CompanySnapshotCard({ snapshot }: Props) {
  const rows: Array<{ label: string; value: string | null }> = [
    { label: 'Company',   value: snapshot.company_name },
    { label: 'Sector',    value: snapshot.sector },
    { label: 'Size',      value: snapshot.size },
    { label: 'Sites',     value: snapshot.sites_summary },
    {
      label: 'Standards',
      value: snapshot.certified_standards.length > 0
        ? snapshot.certified_standards.join(', ')
        : null,
    },
  ];

  return (
    <section className="snapshot-card">
      <header className="snapshot-card-head">
        <span className="eyebrow">Company snapshot</span>
      </header>

      <dl className="snapshot-grid">
        {rows.map(({ label, value }) => (
          <div key={label} className="snapshot-row">
            <dt className="snapshot-label">{label}</dt>
            <dd className="snapshot-value">{value ?? '—'}</dd>
          </div>
        ))}

        {snapshot.key_roles.length > 0 && (
          <div className="snapshot-row snapshot-row-roles">
            <dt className="snapshot-label">Key roles</dt>
            <dd className="snapshot-value">
              <ul className="snapshot-roles">
                {snapshot.key_roles.map((role) => (
                  <li key={role}>{role}</li>
                ))}
              </ul>
            </dd>
          </div>
        )}
      </dl>

      {snapshot.scope_observations && (
        <p className="snapshot-observation">{snapshot.scope_observations}</p>
      )}
    </section>
  );
}
