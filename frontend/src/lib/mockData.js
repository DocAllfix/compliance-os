export const MOCK_GAPS = [
  {
    clause_id: '9001_8_4', clause_title: '8.4 Control of externally provided processes',
    score: 15, severity: 'MAJOR', is_spof: true,
    finding: 'No formal supplier qualification process has been identified in the documentation provided. The approved supplier list is absent and there is no evidence of periodic supplier evaluation.',
    sources: [{ evidence_id: 'ev_001', file_name: 'Supplier_Procedure_Rev1.pdf', pages: [3], excerpt: 'Section 4.2 does not specify qualification criteria.', relevance_score: 0.92 }],
    remediation: { what: 'Establish a formal supplier qualification procedure with an approved vendor list.', who: 'Quality Manager', when: '30 days', effort: 'HIGH' },
    status: 'open',
  },
  {
    clause_id: '9001_7_5', clause_title: '7.5 Documented information',
    score: 22, severity: 'MAJOR', is_spof: true,
    finding: 'Document control is not systematically applied. Multiple procedures found without version numbers, approval signatures, or review dates. Templates are non-standardised.',
    sources: [],
    remediation: { what: 'Implement a document control procedure with version control and approval workflow.', who: 'Quality Manager', when: '30 days', effort: 'HIGH' },
    status: 'open',
  },
  {
    clause_id: '9001_7_2', clause_title: '7.2 Competence',
    score: 55, severity: 'MINOR', is_spof: false,
    finding: 'Training records exist but are not consistently maintained. Several personnel files lack evidence of competence evaluation for their current roles.',
    sources: [],
    remediation: { what: 'Update competence records for all relevant personnel and implement a training matrix.', who: 'HR Manager', when: '90 days', effort: 'MEDIUM' },
    status: 'open',
  },
  {
    clause_id: '9001_9_2', clause_title: '9.2 Internal Audit',
    score: 72, severity: 'OBSERVATION', is_spof: false,
    finding: 'Internal audit programme exists but coverage of high-risk processes could be improved. Last audit cycle did not include supplier management processes.',
    sources: [],
    remediation: { what: 'Review audit programme to ensure all high-risk processes are audited annually.', who: 'Quality Manager', when: 'Next audit cycle', effort: 'LOW' },
    status: 'open',
  },
  {
    clause_id: '9001_5_1', clause_title: '5.1 Leadership and commitment',
    score: 88, severity: 'CONFORMANT', is_spof: false,
    finding: 'Signed quality policy present and dated within the last 12 months. Management review minutes show top management participation.',
    sources: [],
    remediation: { what: 'Maintain current practice.', who: 'Managing Director', when: 'N/A', effort: 'LOW' },
    status: 'closed',
  },
];

export const MOCK_ANALYSIS = {
  analysis_id: 'mock_001',
  company: 'Hartley Construction Ltd',
  norms: [{
    norm: 'ISO 9001:2015',
    overall_score: 58,
    major_count: 2,
    minor_count: 1,
    observation_count: 1,
    conformant_count: 1,
    spof_count: 2,
    clauses: MOCK_GAPS,
  }],
  documents_analyzed: 3,
  analysis_date: '2026-05-06T10:30:00',
};
