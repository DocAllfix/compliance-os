# Banco di misura del motore (Piano motore, Fase 0)

Serve a decidere con i numeri se una modifica al motore migliora davvero: quante
non conformità note trova, quante accuse false fa, quanto è severo e quanto
cambia tra due esecuzioni identiche.

**Regola:** nessun interruttore si accende in produzione se il miglioramento non
supera la variabilità misurata e se la precisione scende.

## Strumenti

| File | Cosa fa |
|---|---|
| `run_pack.py` | Esegue la pipeline su un pacco ZIP N volte. Salva `result.json`, schede, corpus e meta in una cartella **fuori dal repo** (rifiuta percorsi interni). Non scrive sul DB dell'app. `--reuse-corpus` salta la Phase 1, `--card-cache` accende la cache delle schede. |
| `score.py` | Misura le esecuzioni contro la chiave di un pacco: ENC trovate per classe A-E, accuse vietate, severità, variabilità, e la precisione delle contestazioni "contro le proprie registrazioni" (Fasi 4-5). Senza `--key` calcola solo severità e variabilità. |
| `findings.py` | Formato unico dei rilievi (da `result.json` o dall'export DOCX). |
| `synthetic_pack.py` | Genera il pacco sintetico inglese (azienda UK inventata) con la sua chiave. |
| `reapply_rules.py` | Riapplica fuori linea le regole di gravità e delle azioni a un'esecuzione salvata. |
| `self_debug.py` | Riesegue solo le Fasi 4-5 su un'esecuzione salvata e mostra cosa è stato estratto (fogli classificati, dichiarazioni) e gli esiti: serve a iterare sui confronti senza rifare la pipeline. |

Precisione delle Fasi 4-5: ogni contestazione "incoerente / registrazione mancante" viene
abbinata dal giudice a una ENC della chiave. Sul pacco sintetico la chiave è completa (più
l'elenco `true_unplanted` dei difetti veri non piantati apposta): ciò che resta fuori è
un'accusa falsa. Su un pacco reale la chiave può non essere esaustiva: quel numero è un
tetto, non una misura.

## Classi delle ENC

- **A** — norma contro documento (il sistema documentato non copre un requisito);
- **B** — qualità interna di un documento (campo vuoto, scadenza passata, revisione incoerente);
- **C** — contraddizione tra due documenti;
- **D** — "dichiara ma non fa": un documento promette un'evidenza che non c'è;
- **E** — aspettativa di settore.

## Il giudice

L'abbinamento rilievo↔ENC lo fa un LLM (profilo deep, temperature 0, cache su
disco accanto alla chiave):

- per ogni domanda vede solo i passaggi pertinenti per clausola, documenti citati o identificativi;
- deve citare il testo, e una citazione che non si ritrova nel rilievo viene scartata;
- una "parziale" conta solo se nomina lo stesso oggetto della ENC.

Taratura sul report della demo Box contro le etichette dell'auditor: **42/45
d'accordo su "trovata sì/no"**. Le parziali restano più rumorose: sono una
misura secondaria.

## Uso tipico

```powershell
cd backend
# pacco sintetico
python tools/bench/synthetic_pack.py --out C:\Users\user\amisys-bench\synthetic\uk_v1
python tools/bench/run_pack.py C:\Users\user\amisys-bench\synthetic\uk_v1\pack.zip `
    --out C:\Users\user\amisys-bench\runs\synthetic\prova --company "Northwind Fabrication Ltd" `
    --sector Manufacturing --employees 11-50 --norms "ISO 9001:2015" "ISO 14001:2015" "ISO 45001:2018" --runs 2
python tools/bench/score.py --key C:\Users\user\amisys-bench\synthetic\uk_v1\key.json `
    --out C:\Users\user\amisys-bench\scores\synthetic\prova <cartella_r1> <cartella_r2>
```

Per confrontare una modifica isolando il rumore delle schede, usare la stessa
`--card-cache` e lo stesso `--reuse-corpus` della base.

I pacchi dei clienti, le chiavi e i punteggi restano in `C:\Users\user\amisys-bench\`,
mai nel repository.
