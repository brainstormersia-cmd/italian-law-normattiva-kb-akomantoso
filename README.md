# 🏛️ Normattiva Knowledge Base (RAG Ready)

Questo progetto trasforma file XML grezzi di leggi italiane (formato Normattiva / Akoma Ntoso) in un dataset strutturato JSONL di alta qualità, pronto per essere utilizzato in sistemi RAG (Retrieval-Augmented Generation) con LLM.

## ✨ Funzionalità

* **Ingestione Intelligente:** Gestisce file XML e ZIP.
* **Parsing Robusto:** Supporta sia XML Normattiva classici che standard Akoma Ntoso.
* **Pulizia Dati:** Genera gerarchie semantiche pulite (es. `Art. 5 > Comma 2`) rimuovendo tecnicismi XML.
* **Risoluzione Riferimenti:** Identifica collegamenti tra articoli (es. "visto l'art. 3") e li risolve nel database.
* **Export RAG-Ready:** Produce un JSONL con Titolo Legge, Contesto Gerarchico e Testo pulito.

## 🚀 Guida Rapida

### 1. Prerequisiti
* Docker & Docker Compose installati.
* I file XML da processare nella cartella `xml_input` (o una tua scelta).

### 2. Avvio
Avvia il database e l'applicazione:
```bash
docker-compose up -d

3. Pipeline di Elaborazione (The Magic Sequence)
Per trasformare i dati grezzi in conoscenza, esegui questi comandi in sequenza:

A. Ingestione (Scansione file) Carica i file XML nel database (stato: new).

Bash

docker-compose run --rm app python -m app.cli ingest --dir /app/xml_input
B. Parsing (Estrazione Testo e Struttura) Trasforma gli XML in nodi, estrae il testo e calcola la gerarchia.

Bash

docker-compose run --rm app python -m app.cli parse
C. Estrazione Riferimenti (Opzionale ma consigliato) Trova le citazioni all'interno dei testi.

Bash

docker-compose run --rm app python -m app.cli extract-references
D. Risoluzione Riferimenti (Opzionale) Collega le citazioni ai documenti reali presenti nel DB.

Bash

docker-compose run --rm app python -m app.cli resolve-references
4. Verifica e Export
Preview (Sanity Check) Visualizza 3 nodi casuali per verificare che la pulizia e i titoli siano corretti.

Bash

docker-compose run --rm app python -m app.cli preview-rag
Export Finale Genera il file conoscenza_pronta.jsonl pronto per il Vector Database.

Bash

docker-compose run --rm app python -m app.cli export-rag
Il file di output avrà questo formato ideale per l'embedding:

JSON

{
  "id": "hash_univoco...",
  "source": "LEGGE 9 Novembre 2004 n 265",
  "context": "Capo I > Art. 2 > Comma 5",
  "text": "Il testo dell'articolo...",
  "url": "..."
}

🧹 Comandi Utili (Manutenzione)
Reset Totale Database (Attenzione: cancella tutto!) Utile se vuoi ripartire da zero con nuovi file.

Bash

docker-compose run --rm app python -c "from app.db.session import SessionLocal; from app.db.models import RawFile, Document, Node, ReferenceResolved, ReferenceExtracted, DocumentVersion, UrnResolutionLog, ConflictEvent; s=SessionLocal(); s.query(ReferenceResolved).delete(); s.query(ReferenceExtracted).delete(); s.query(UrnResolutionLog).delete(); s.query(ConflictEvent).delete(); s.query(Node).delete(); s.query(DocumentVersion).delete(); s.query(Document).delete(); s.query(RawFile).delete(); s.commit(); print('🧹 DATABASE PULITO')"

---

### 3️⃣ `.gitignore` (Per non caricare spazzatura)

Assicurati che il tuo file `.gitignore` contenga queste righe, così non carichi su GitHub i file XML giganti o il database locale.

```text
__pycache__/
*.pyc
.env
.DS_Store
# Dati locali
xml_input/
normattiva_cache/
pgdata/
*.jsonl
*.log