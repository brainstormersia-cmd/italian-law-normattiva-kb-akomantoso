# normattiva_kb

Pipeline deterministica per ingestire XML Normattiva in Postgres con parsing gerarchico, versioni di vigenza e riferimenti normativi canonicalizzati. **Nessun embedding / vector DB**: l'output è pronto per un sistema separato di embedding.

## Cosa include

- **Parser XML deterministico** (lxml) per estrarre struttura gerarchica e nodi atomici.
- **Parser Akoma Ntoso generico** con visitor ricorsivo e tag config per structural/container/inline.
- **Database relazionale Postgres** con schema idempotente (documenti, versioni, nodi, riferimenti).
- **CLI** per ingest, parsing, indicizzazione full‑text, estrazione/risoluzione riferimenti.
- **URN resolution engine** con fallback explicit → contextual → heuristic → manual e tracciamento in `urn_resolution_log`.
- **API FastAPI** di debug per consultazione base.
- **Alembic migrations** per versionare lo schema.
- **Test pytest** con fixture XML minimali e test di idempotenza.

## Librerie principali

- **SQLAlchemy 2.x** + **Alembic**: ORM e migrazioni DB.
- **FastAPI** + **Uvicorn**: API di debug.
- **lxml**: parsing XML robusto.
- **structlog** + **loguru**: logging strutturato e output JSON.
- **pydantic v2**: config e validazioni.
- **pytest**: test automatici.

## Principi guida

- **Robustezza e idempotenza**: re‑ingest non duplica né corrompe.
- **Parsing deterministico**: no LLM, solo regole e XPath.
- **Fedeltà al testo**: nessuna riscrittura semantica, normalizzazione conservativa.
- **Tracciabilità**: ogni dato derivato conserva snippet e metodo.
- **Gerarchia esplicita**: struttura Legge → Titolo → Capo → Articolo → Comma.
- **Versioni storiche**: ogni versione è preservata con `valid_from`/`valid_to`.

## Stato del progetto e roadmap stakeholder

Di seguito lo stato attuale rispetto alle richieste prioritarie; le voci **In progress** sono già implementate in forma iniziale, mentre le altre sono **Planned** (da pianificare in sprint successivi).

1. **URN Resolution Engine (critico)** → **In progress**
   - Resolver contestuale con cache LRU, confidence scoring e fallback explicit → contextual → heuristic → manual.
   - Logging delle risoluzioni in `urn_resolution_log` con metodo e confidence.
   - Heuristic/NER light basato su alias testuali e snippet contestuali.
2. **Temporal Conflict Detection (alto valore)** → **In progress**
   - Detector per modifiche sovrapposte su `canonical_path` con severità e workflow di revisione.
   - Schema eventi conflitto con stati `pending/reviewed/resolved`.
3. **Differential Versioning (ottimizzazione storage)** → **In progress**
   - Delta storage con `diff-match-patch`, ricostruzione lazy e compressione oltre soglia.
4. **Semantic Validation Layer (innovazione)** → **Planned**
   - Embeddings + `pgvector` per alert di ridondanza/contraddizione con review umana.
5. **Enhanced Observability (produzione)** → **In progress**
   - Correlation ID per run, timing metrics per fase, health check esteso.
6. **Gestione Tag Complessi Avanzata** → **Planned**
   - Parsing avanzato per `<mod>` nidificati, `<quotedStructure>`, `<foreign>`, `<remark>`, namespace multipli.
7. **Incremental Processing** → **Planned**
   - Change detection via SHA256 e re‑process selettivo con dependency graph.
8. **Cross‑Reference Graph Enrichment** → **Planned**
   - Referenze bidirezionali, metriche grafo e impact analysis.
9. **Quality Assurance Automation** → **Planned**
   - Validazione XSD, controlli di consistenza e regression suite su corpus.
10. **Performance Optimization** → **Planned**
    - Parallel processing, batching ottimizzato, pooling DB, caching e profiling.
11. **Data Export & Interoperabilità** → **Planned**
    - Export RDF/OWL, JSON‑LD, bulk export e API di sync incrementale.
12. **Advanced Metadata Extraction** → **Planned**
    - Eventi lifecycle, autori istituzionali, classificazione e keywords.

## Requisiti

- Python 3.11+
- Postgres 15+
- Docker opzionale

## Documentazione operativa

- [Struttura del progetto](STRUCTURE.md)
- [Guida setup pulito](SETUP.md)

## Avvio con Docker

```bash
docker-compose up --build
```

All'avvio vengono eseguite le migrazioni Alembic e parte l'API su `http://localhost:8000`.

## Avvio senza Docker

1. Crea un virtualenv e installa le dipendenze:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configura le variabili ambiente (esempio in `.env.example`).

3. Applica le migrazioni:

```bash
alembic upgrade head
```

4. Avvia CLI/API:

```bash
python -m app.cli serve
```

## CLI

```bash
python -m app.cli ingest --dir /path/to/xml
python -m app.cli parse
python -m app.cli build-fts
python -m app.cli extract-references
python -m app.cli resolve-references
python -m app.cli detect-conflicts
python -m app.cli stats
python -m app.cli serve
```

### Flusso tipico

1. **ingest**: registra i file XML/ZIP in `raw_files`.
2. **parse**: estrae documenti/versioni e nodi atomici.
3. **build-fts**: crea indice full‑text su `nodes.text_clean`.
4. **extract-references**: estrae riferimenti normativi.
5. **resolve-references**: risolve i riferimenti su nodi esistenti.
6. **detect-conflicts**: segnala conflitti temporali su percorsi canonici.

## API (debug)

- `GET /health`
- `GET /docs?doc_type=&year=&number=`
- `GET /doc/{canonical_doc}`
- `GET /doc/{canonical_doc}/tree?version_tag=`
- `GET /node/{node_id}`
- `GET /search?q=...`
- `POST /extract_references` (body: `{ "text": "..." }`)

## Idempotenza

- `raw_files` evita duplicati tramite hash SHA256.
- `document_versions` evita duplicati per `doc_id + version_tag` e checksum testo.
- `nodes` è unico per `version_id + canonical_path`.
- `references_extracted` evita duplicati per `source_node_id + match_text`.

## Test

```bash
pytest
```
