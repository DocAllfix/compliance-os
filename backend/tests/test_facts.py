"""
Fast — Piano motore Fase 3 (FACT_MODEL): il modello dei fatti.

Pin: dalle schede si sa chi ha emesso ogni documento e chi lavora per chi;
i ruoli chiave non contengono mai persone che compaiono solo su documenti
esterni (errore F01 dell'auditor); le righe dei registri letti senza perdite
diventano campi strutturati; le etichette per i prompt dicono emittente e
dominio.
"""
from __future__ import annotations

from compliance import facts as F

CARDS = [
    {"file_name": "5 Leadership/IMS1 Manual.docx", "issuer": "client", "domain": "integrated", "doc_code": "IMS1",
     "people": [{"name": "Laura Pennington", "role": "Managing Director", "organisation": "client"}]},
    {"file_name": "7 Support/Calibration/NWC-2201.pdf", "issuer": "supplier", "issuer_name": "Calibrex Services Ltd",
     "domain": "quality", "doc_code": "NWC-2201",
     "people": [{"name": "Helen Marsh", "role": "Technical Manager", "organisation": "Calibrex Services Ltd"}]},
]
DOCS = [{"filename": "7 Support/IMS9 Calibration Register.xlsx", "content":
         '[SHEET "Register"]\nColumns: ID | Certificate | Result\n'
         "Row 2: ID: CAL-01 | Certificate: NWC-2201 | Result: Pass\n"
         "Row 3: ID: CAL-03 | Certificate: NWC-2203 | Result: (blank)\n"}]


def test_documents_people_and_tags():
    f = F.build(CARDS, DOCS)
    assert f.is_external("NWC-2201.pdf") and not f.is_external("ims1 manual.docx")
    assert f.tag("NWC-2201.pdf") == "issued by: supplier (Calibrex Services Ltd); domain: quality"
    assert f.is_external_person("Helen Marsh") and not f.is_external_person("Laura Pennington")


def test_key_roles_never_include_external_people():
    f = F.build(CARDS)
    roles = ["Managing Director: Laura Pennington", "Technical Manager: Helen Marsh"]
    assert f.filter_key_roles(roles) == ["Managing Director: Laura Pennington"]


def test_register_rows_become_fields():
    rows = F.build([], DOCS).register_rows
    assert rows[0]["sheet"] == "Register" and rows[0]["fields"]["Certificate"] == "NWC-2201"
    assert rows[1]["fields"]["Result"] == "" and rows[1]["row"] == 3


def test_card_addendum_is_parsable_yaml():
    import yaml
    sample = (
        'file_name: "x.pdf"\nsigned_by: null\nissuer: "supplier"\nissuer_name: "Calibrex"\n'
        'domain: "quality"\ndoc_code: "NWC-1"\nversion: null\npeople:\n'
        '  - name: "Helen Marsh"\n    role: "Technical Manager"\n    organisation: "Calibrex"\n'
    )
    card = yaml.safe_load(sample)
    assert F.build([card]).is_external_person("Helen Marsh")


def test_certificate_signatories_and_matrix_people():
    cards = [{"file_name": "First Aid - P Shah.pdf", "issuer": "client", "doc_type": "certificate",
              "people": [{"name": "Marcus Reed", "role": "CEO", "organisation": "client"}]}]
    docs = [{"filename": "IMS11 Training Matrix.xlsx",
             "content": '[SHEET "M"]\nColumns: Name | First Aid\nRow 2: Name: Tom Ashworth | First Aid: 2024-01-05\n'}]
    f = F.build(cards, docs)
    roles = ["CEO: Marcus Reed", "Compliance Manager: T. Ashworth", "Trainer: Gary Lyne"]
    assert f.filter_key_roles(roles) == ["Compliance Manager: T. Ashworth"]


def test_key_roles_come_from_system_documents():
    # chi compare solo su un foglio presenze o su un attestato (formatore, istruttore) non è un
    # ruolo chiave, anche se la scheda lo dà per personale del cliente (banco Box, 2026-10-12)
    cards = [{"file_name": "SOP1 Document Control.docx", "issuer": "client", "doc_type": "procedure",
              "people": [{"name": "Tom Ashworth", "role": "Compliance Manager", "organisation": "client"}]},
             {"file_name": "Training record 23-2-2024.jpeg", "issuer": "client", "doc_type": "training_record",
              "people": [{"name": "Gary Lyne", "role": "Trainer", "organisation": "client"}]},
             {"file_name": "FLT D Morley.pdf", "issuer": "client", "doc_type": "training_record",
              "people": [{"name": "Owen Clarke", "role": "Instructor", "organisation": "client"}]}]
    f = F.build(cards)
    assert set(f.key_people) == {"tom ashworth"} and len(f.client_people) == 3
    roles = ["Trainer: Gary Lyne", "Compliance Manager: Tom Ashworth", "Instructor: Owen Clarke"]
    assert f.filter_key_roles(roles) == ["Compliance Manager: Tom Ashworth"]
