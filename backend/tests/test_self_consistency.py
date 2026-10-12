"""
Fast — Piano motore Fase 4 (SELF_CONSISTENCY): l'organizzazione contro sé stessa.

Pin dei confronti deterministici (il modello estrae, Python giudica):
  - un certificato citato a registro e assente dal pacco → MISSING;
  - registro "Pass" contro certificato "fail", scadenze diverse → INCONSISTENT;
  - azione aperta oltre la data obiettivo → INCONSISTENT;
  - matrice: persona formata ma assente dal foglio presenze leggibile → INCONSISTENT
    (illeggibile → TO_VERIFY: nel dubbio non si accusa una persona);
    corso senza nessuna registrazione → MISSING; formatore diverso; campo formatore vuoto;
  - stesso oggetto, due documenti, due valori/date → INCONSISTENT;
  - versione nel nome del file diversa da quella interna → INCONSISTENT;
  - aggancio: un esito → una clausola di una norma; con le regole diventa MINOR;
  - prudenza: solo i codici etichettati sono citazioni (un registro legale non cita
    certificati); "per ogni fornitore" si contesta se alcuni hanno la registrazione
    e altri no; una registrazione dichiarata è mancante solo dopo elenco dei file e
    ricerca; due valori si confrontano solo se riguardano la stessa cosa (obiettivo
    contro obiettivo, data pianificata contro effettiva); quantità dichiarata contro
    voci elencate e ritrovate alla lettera.
"""
from __future__ import annotations

import datetime as dt

from compliance import self_consistency as S
from compliance.facts import Facts, parse_register_rows


def _rows(file_name, text):
    return parse_register_rows(file_name, text)


def test_dates_and_names():
    assert S.parse_date("8.2.24") == dt.date(2024, 2, 8)
    assert S.parse_date("11 November 2026") == dt.date(2026, 11, 11)
    assert S.parse_date("2026-03-11") == dt.date(2026, 3, 11)
    assert S._names_match("Tom Ashworth", "T. Ashworth") and not S._names_match("Tom Ashworth", "Dan Morley")


def test_reference_register_missing_failed_and_due_mismatch():
    reg = ('[SHEET "R"]\nRow 2: ID: CAL-01 | Certificate: NWC-2201 | Result: Pass | Next due: 10/09/2026\n'
           "Row 3: ID: CAL-02 | Certificate: NWC-2202 | Result: Pass | Next due: 11/08/2026\n"
           "Row 4: ID: CAL-03 | Certificate: NWC-2203 | Result: Pass | Next due: 12/08/2026\n")
    corpus = S._Corpus([{"filename": "IMS9 Register.xlsx", "content": reg},
                        {"filename": "NWC-2201.pdf", "content": "Certificate NWC-2201 pass, next due 10/08/2026"},
                        {"filename": "NWC-2202.pdf", "content": "Certificate NWC-2202 FAIL"}])
    facts = {"NWC-2201.pdf": {"result": "pass", "next_due": "10/08/2026", "number": "NWC-2201"},
             "NWC-2202.pdf": {"result": "fail", "next_due": None, "number": "NWC-2202"}}
    spec = {"reference_column": "Certificate", "result_column": "Result", "next_due_column": "Next due",
            "clause": "ISO 9001 §7.1.5"}
    out = S._check_reference_register(_rows("IMS9 Register.xlsx", reg), spec, corpus, lambda n, t: facts[n])
    kinds = sorted((c["kind"], c["status"]) for c in out)
    assert ("referenced_record", "MISSING") in kinds                       # NWC-2203
    assert sum(1 for c in out if c["kind"] == "register_vs_record") == 2   # fail + scadenza


def test_overdue_nc():
    rows = _rows("NC Log.xlsx", '[SHEET "L"]\nRow 2: Ref: NC-014 | Target date: 31/03/2026 | Status: Open\n'
                                "Row 3: Ref: NC-013 | Target date: 31/01/2026 | Status: Closed\n")
    out = S._check_nc_log(rows, {"status_column": "Status", "target_date_column": "Target date"}, dt.date(2026, 10, 12))
    assert len(out) == 1 and out[0]["kind"] == "overdue_action"


def _matrix():
    return _rows("Matrix.xlsx", '[SHEET "M"]\n'
                 "Row 2: Name: Tom Ashworth | Manual Handling: 05/02/2026 | Fire Warden: 14/01/2026 | Fire Warden trainer: Tom Ashworth\n"
                 "Row 3: Name: Priya Shah | Manual Handling: 05/02/2026 | Fire Warden: 14/01/2026 | Fire Warden trainer: Tom Ashworth\n"
                 "Row 4: Name: Dan Morley | Manual Handling: 05/02/2026 | Abrasive Wheels: 12/03/2026\n")


def test_training_matrix_against_attendance_records():
    corpus = S._Corpus([
        {"filename": "Matrix.xlsx", "content": ""},
        {"filename": "Attendance - Manual Handling 05-02-2026.docx",
         "content": "Training Attendance Sheet Course: Manual Handling Date: 05/02/2026 Trainer: Attendees: Tom Ashworth; Dan Morley"},
        {"filename": "Attendance - Fire Warden 14-01-2026.docx",
         "content": "Training Attendance Sheet Course: Fire Warden Date: 14/01/2026 Trainer: Gareth Lyle Attendees: Tom Ashworth; Priya Shah"},
    ])
    recs = {"Attendance - Manual Handling 05-02-2026.docx": {"trainer": None, "trainer_field_present": True,
                                                            "attendees": ["Tom Ashworth", "Dan Morley"], "attendees_readable": True},
            "Attendance - Fire Warden 14-01-2026.docx": {"trainer": "Gareth Lyle", "trainer_field_present": True,
                                                        "attendees": ["Tom Ashworth", "Priya Shah"], "attendees_readable": True}}
    spec = {"person_column": "Name", "trainer_column": "Fire Warden trainer",
            "course_date_columns": ["Manual Handling", "Fire Warden", "Abrasive Wheels"], "clause": "ISO 45001 §7.2"}
    out = S._check_training(_matrix(), spec, corpus, lambda n, t: recs[n])
    got = {(c["kind"], c["status"], c.get("person")) for c in out}
    assert ("training_attendance", "INCONSISTENT", "Priya Shah") in got      # non firma Manual Handling
    assert ("training_record", "MISSING", None) in got                      # Abrasive Wheels senza registrazione
    assert any(k == "trainer" for k, _, _ in got) and any(k == "record_field" for k, _, _ in got)


def test_unreadable_attendance_is_only_to_verify():
    corpus = S._Corpus([{"filename": "Matrix.xlsx", "content": ""},
                        {"filename": "Attendance MH.jpg", "content": "Training attendance Manual Handling 05/02/2026"}])
    spec = {"person_column": "Name", "course_date_columns": ["Manual Handling"], "clause": "ISO 9001 §7.2"}
    out = S._check_training(_matrix(), spec, corpus,
                            lambda n, t: {"attendees": ["T. Ashworth"], "attendees_readable": False})
    assert {c["status"] for c in out if c["kind"] == "training_attendance"} == {"TO_VERIFY"}


def test_values_dates_and_versions():
    claims = [("MR minutes.docx", {"type": "value", "subject": "rework hours objective", "value": "5%", "quote": "q1",
                                   "planned": True}),
              ("Objectives.docx", {"type": "value", "subject": "rework hours objective", "value": "3%", "quote": "q2",
                                   "planned": True}),
              ("Programme.xlsx", {"type": "date", "subject": "internal audit IA-01", "value": "14/04/2026", "quote": "q3",
                                  "planned": True}),
              ("Audit report.docx", {"type": "date", "subject": "internal audit IA-01", "value": "21/04/2026", "quote": "q4"})]
    # le due date hanno lo stesso codice (IA-01): si confrontano dopo la conferma che è lo stesso evento
    kinds = sorted(c["kind"] for c in S._compare_values(claims, lambda pairs: [True] * len(pairs)))
    assert kinds == ["date_mismatch", "value_mismatch"]
    f = Facts()
    f.documents["sop4 v2.docx"] = {"file_name": "SOP4 Supplier Control v2.docx", "issuer": "client", "version": "1.0"}
    assert S._check_versions(f)[0]["kind"] == "version"


def test_attach_one_clause_and_minor(monkeypatch):
    from compliance.schemas import ClauseGap, NormGapReport, RemediationPlan
    monkeypatch.setenv("SEVERITY_RULES", "1")
    gap = ClauseGap(clause_id="45001_7_2", clause_title="7.2 Competence", score=90, severity="CONFORMANT",
                    is_spof=False, finding="Competence is managed.", sources=[],
                    remediation=RemediationPlan(what="x", who="y", when="z", effort="LOW"))
    rep = NormGapReport(norm="ISO 45001:2018", overall_score=90, clauses=[gap], major_count=0, minor_count=0,
                        observation_count=0, conformant_count=1, spof_count=0)
    checks = [S._check("training_record", "MISSING", "No attendance record for Abrasive Wheels (12/03/2026)",
                       "ISO 45001 §7.2", [("Matrix.xlsx", "Row 4")])]
    out = S.attach([rep], checks, {"ISO 45001:2018": {"45001_7_2": {"id": "45001_7_2"}}})
    g = out[0].clauses[0]
    assert g.severity == "MINOR" and out[0].minor_count == 1
    assert any(".self." in c.requirement_id and c.searched for c in g.requirement_checks)


def test_different_events_are_not_compared():
    # due audit diversi (date lontane) e due date entrambe "effettive" non sono una contraddizione;
    # i valori delle singole registrazioni (attestati) sono esclusi a monte da run() per tipo di documento
    claims = [("Programme.xlsx", {"type": "date", "subject": "internal audit IA-02", "value": "15/09/2026", "planned": True}),
              ("Report IA-01.docx", {"type": "date", "subject": "internal audit IA-02", "value": "21/04/2026"}),
              ("Minutes A.docx", {"type": "date", "subject": "management review meeting", "value": "20/05/2026"}),
              ("Minutes B.docx", {"type": "date", "subject": "management review meeting", "value": "22/05/2026"})]
    assert S._compare_values(claims) == []
    assert "theory" not in str(S._SYSTEM_DOC_TYPES) and "certificate" not in S._SYSTEM_DOC_TYPES


# ── regole di prudenza (banco di misura, 2026-10-12) ─────────────────────────

def test_only_labelled_codes_are_citations():
    # il codice del certificato sta in una cella di stato ("Pass (Cert: NWC-2301)"), l'Asset ID
    # nomina lo strumento, un registro legale cita leggi con l'anno: solo il primo è una citazione
    reg = ('[SHEET "R"]\nRow 2: Asset ID: CAL004 | Certified By: Calibrex Services | Status: Pass (Cert: NWC-2301)\n'
           "Row 3: Asset ID: CAL005 | Certified By: Calibrex Services | Status: Pass (Cert: NWC-2302)\n")
    rows = _rows("IMS9 Calibration Register.xlsx", reg)
    assert S._citations(rows[0], "Asset ID") == [("Status", "NWC-2301")]
    corpus = S._Corpus([{"filename": "IMS9 Calibration Register.xlsx", "content": reg},
                        {"filename": "NWC-2301.pdf", "content": "Certificate NWC-2301 for asset CAL004: pass"}])
    out = S._check_reference_register(rows, {"reference_column": "Asset ID"}, corpus,
                                      lambda n, t: {"result": "pass", "number": "NWC-2301"})
    assert [(c["kind"], c["status"]) for c in out] == [("referenced_record", "MISSING")]
    assert "NWC-2302" in out[0]["description"]

    legal = ('[SHEET "L"]\nRow 2: Legislation: Health and Safety at Work etc. Act 1974 | Responsibility: QHSE\n'
             "Row 3: Legislation: Management of Health and Safety at Work Regulations 1999 | Responsibility: QHSE\n")
    assert S._check_reference_register(_rows("Legal.xlsx", legal), {"reference_column": "Legislation"}, corpus,
                                       lambda n, t: {}) == []


def test_wrong_file_name_for_a_cited_record():
    reg = '[SHEET "R"]\nRow 2: Asset ID: CAL003 | Status: Active (Cert: GL-0018)\n'
    corpus = S._Corpus([{"filename": "Register.xlsx", "content": reg},
                        {"filename": "GL-0081.pdf", "content": "Calibration certificate GL-0018, smart meter logger"}])
    out = S._check_reference_register(_rows("Register.xlsx", reg), {}, corpus,
                                      lambda n, t: {"kind": "certificate", "number": "GL-0018", "result": "unknown"})
    assert [c["kind"] for c in out] == ["file_name"] and "GL-0081" in out[0]["description"]


def test_per_supplier_record_only_when_some_have_it():
    asl = "Suppliers/IMS5 Approved Supplier List.xlsx"
    docs = [{"filename": "Suppliers/Calibrex Services Ltd/Supplier questionnaire.docx",
             "content": "Supplier questionnaire - Calibrex"},
            {"filename": asl, "content": "Yorkshire Steel Stockholders | Approval basis: Questionnaire; mill certificates"}]
    corpus = S._Corpus(docs)
    suppliers = ["Calibrex Services Ltd", "Yorkshire Steel Stockholders"]
    claim = {"subject": "supplier questionnaire", "quote": "Every approved supplier must return the supplier questionnaire"}
    out = S._check_per_entity(claim, "SOP4.docx", corpus, suppliers, {asl})
    assert out[0]["status"] == "MISSING"
    assert "Yorkshire Steel Stockholders" in out[0]["description"].split("none found for:")[1]
    assert "Calibrex" not in out[0]["description"].split("none found for:")[1]
    # nessun fornitore ha quella registrazione: può stare fuori dal pacco → solo da verificare
    review = {"subject": "annual performance review", "quote": "An annual performance review is filed for each supplier"}
    assert [c["status"] for c in S._check_per_entity(review, "SOP4.docx", corpus, suppliers, set())] == ["TO_VERIFY"]
    # la frase non dice "ogni fornitore" e la registrazione ce l'hanno in pochi: non è una regola per tutti
    ncr = {"subject": "supplier questionnaire", "quote": "A questionnaire is sent to the supplier"}
    three = suppliers + ["Greenline Waste Ltd"]
    assert S._check_per_entity(ncr, "SOP4.docx", corpus, three, {asl}) is None      # resta la verifica semplice
    assert S._entity_keys(["Greenline Waste Ltd", "Yorkshire Steel Stockholders", "West Yorkshire Gases"]) == {
        "Greenline Waste Ltd": ["greenline"], "Yorkshire Steel Stockholders": ["yorkshire", "steel"],
        "West Yorkshire Gases": ["west"]}
    # "dove applicabile": mai una mancanza provata
    cond = S._check_per_entity({"subject": "supplier questionnaire", "quote": "where applicable, a questionnaire"},
                               "SOP4.docx", corpus, suppliers, {asl})
    assert cond[0]["status"] == "TO_VERIFY"


def test_document_feature_none_some_all():
    docs = [(f"SOP{i}.docx", "text") for i in range(1, 5)]
    claim = {"subject": "a revision table", "quote": "Each controlled document carries a revision table"}
    assert S._check_document_feature(claim, "SOP1.docx", docs, lambda n, t: False)[0]["status"] == "MISSING"
    some = S._check_document_feature(claim, "SOP1.docx", docs, lambda n, t: n == "SOP2.docx")
    assert some[0]["status"] == "TO_VERIFY"
    assert S._check_document_feature(claim, "SOP1.docx", docs, lambda n, t: True) == []
    assert S._check_document_feature(claim, "SOP1.docx", docs, lambda n, t: None) == []      # non determinabile


def test_declared_record_needs_inventory_and_search():
    claim = {"subject": "H&S committee minutes", "quote": "minutes are stored digitally", "clause": "ISO 45001 §5.4"}
    assert S._check_record_kept(claim, "SOP5.docx", lambda s, q, src: False, lambda s, q, src: True) == []
    assert S._check_record_kept(claim, "SOP5.docx", lambda s, q, src: None, lambda s, q, src: False) == []
    assert S._check_record_kept(claim, "SOP5.docx", lambda s, q, src: False, lambda s, q, src: False)[0]["status"] == "MISSING"
    assert S._check_record_kept(claim, "MR.docx", lambda s, q, src: False, None, rule_doc=False)[0]["status"] == "TO_VERIFY"
    assert S._is_self_reference("QHSE Policy document", "IMS2 QHSE Policy.docx", "policy")
    assert S._is_self_reference("risk assessment record", "RA1 Welding.docx", "risk_assessment")
    assert not S._is_self_reference("fire drill evacuation times", "SOP6 Emergency Preparedness.docx", "procedure")


def test_same_thing_is_confirmed_before_comparing():
    claims = [("Objectives.docx", {"type": "value", "subject": "rework on fabricated components",
                                   "value": "below 3% of hours", "planned": True}),
              ("MR.docx", {"type": "value", "subject": "rework objective", "value": "5%", "planned": True}),
              ("MR.docx", {"type": "value", "subject": "electricity per tonne", "value": "-4%", "planned": False}),
              ("Objectives.docx", {"type": "value", "subject": "electricity use per tonne", "value": "-5%", "planned": True}),
              ("Programme.xlsx", {"type": "date", "subject": "IA-01", "value": "14/04/2026", "planned": True}),
              ("Internal Audit Report IA-01.docx", {"type": "date", "subject": "internal audit date", "value": "21/04/2026",
                                                    "planned": False})]
    asked = []
    out = S._compare_values(claims, lambda pairs: asked.append(len(pairs)) or [True] * len(pairs))
    assert asked == [2], "obiettivo contro risultato misurato non arriva nemmeno al confronto"
    assert sorted(c["kind"] for c in out) == ["date_mismatch", "value_mismatch"]
    assert S._compare_values(claims, lambda pairs: [False] * len(pairs)) == []
    assert S._compare_values(claims) == []          # senza conferma non si contesta


def test_one_finding_per_group_of_declarations():
    claims = [(f, {"type": "value", "subject": "machinery downtime", "value": v, "planned": True})
              for f, v in (("Objectives.docx", "5%"), ("MR.docx", "10%"), ("Audit.docx", "5%"))]
    out = S._compare_values(claims)
    assert len(out) == 1 and "3 documents" in out[0]["description"]


def test_declared_quantity_against_a_plan():
    plan = "Site plan - fire extinguisher locations\nFE1 CO2 Welding bay\nFE2 CO2 Cutting area\nFE3 Foam Paint store"
    claim = {"subject": "fire extinguishers", "value": "seven", "quote": "There are seven fire extinguishers"}
    listing = {"complete": True,
               "items": ["FE1 CO2 Welding bay", "FE2 CO2 Cutting area", "FE3 Foam Paint store", "FE9 invented"]}
    out = S._check_listed_quantity(claim, "SOP6.docx", "Site plan.png", plan, listing)
    assert out[0]["status"] == "INCONSISTENT" and "shows 3" in out[0]["description"]
    # etichette identiche ripetute (simboli su una planimetria): conteggio indicativo → da verificare
    symbols = "KEY FE Fire Extinguisher\nFE\nFE\nFE"
    out = S._check_listed_quantity(claim, "SOP6.docx", "Plan.png", symbols, {"complete": True, "items": ["FE", "FE", "FE"]})
    assert out[0]["status"] == "TO_VERIFY"
    assert S._check_listed_quantity(claim, "SOP6.docx", "Plan.png", plan,
                                    {"complete": False, "items": ["FE1 CO2 Welding bay"]}) == []
