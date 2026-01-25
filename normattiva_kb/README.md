# normattiva_kb

Pipeline deterministica per ingestire XML Normattiva in Postgres con parsing gerarchico, versioni di vigenza e riferimenti normativi canonicalizzati. Nessun embedding o vector DB: l'output è pronto per un sistema separato di embedding.

## Requisiti

- Python 3.11+
- Postgres 15+
- Docker opzionale

Dipendenze Python principali:
- SQLAlchemy 2.x
- Alembic
- FastAPI + Uvicorn
- lxml
- structlog
- pydantic v2
- pytest (test)

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
python -m app.cli stats
python -m app.cli serve
```

### Flusso tipico

1. `ingest`: registra i file XML/ZIP in `raw_files`.
2. `parse`: estrae documenti/ versioni e nodi atomici.
3. `build-fts`: crea indice full-text su `nodes.text_clean`.
4. `extract-references`: estrae riferimenti normativi.
5. `resolve-references`: risolve i riferimenti su nodi esistenti.

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
