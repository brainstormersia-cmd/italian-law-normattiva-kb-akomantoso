# Project structure

This document summarizes the main folders and files in the repository, with a focus on the `normattiva_kb` service.

## Top-level

- `normativa_processor/`: PDF/Text-oriented preprocessing pipeline (chunking, parsing, metadata utilities).
- `normattiva_kb/`: Normattiva XML ingestion, parsing, DB schema, API, and CLI.
- `tests/`: General unit tests for shared components (token estimation, config validation).

## `normattiva_kb/` layout

### Configuration & runtime
- `.env.example`: environment variables reference for DB and runtime settings.
- `Dockerfile`: container image for the API/CLI service.
- `docker-compose.yml`: local orchestration (DB + API).
- `alembic.ini`: Alembic migration config for schema management.
- `pyproject.toml` / `requirements.txt`: dependency definitions.

### App code (`normattiva_kb/app/`)
- `api/`: FastAPI application.
  - `routes.py`: HTTP endpoints (`/health`, `/docs`, `/doc/*`, `/search`, etc.).
  - `schemas.py`: API response/request schemas.
  - `deps.py`: dependency wiring (DB session).
- `analysis/`: analytical jobs and detectors.
  - `conflict_detector.py`: temporal overlap detection for conflict events.
- `core/`: shared utilities.
  - `config.py`: settings loader.
  - `logging.py`: structured logging configuration.
  - `utils_*`: hashing/date/text helpers.
- `db/`: database layer.
  - `models.py`: ORM models (documents, nodes, references, conflicts, deltas).
  - `repo.py`: repository helpers for upserts.
  - `session.py`: SQLAlchemy session setup.
  - `migrations/`: Alembic migrations (schema history).
- `ingestion/`: input discovery and raw file storage.
  - `scanner.py`: file discovery.
  - `zip_cache.py`: ZIP extraction.
  - `raw_store.py`: raw file metadata.
  - `normattiva_reader.py`: XML parsing entry.
- `parsing/`: Normattiva/Akoma Ntoso parsing and reference extraction.
  - `normattiva_parser.py`: main deterministic parser.
  - `akoma_parser.py`: generic Akoma Ntoso visitor.
  - `references.py`: regex reference extraction and helpers.
  - `urn_resolver.py`: URN resolution engine.
- `versioning/`: version delta utilities.
  - `diff_store.py`: diff/patch helpers (diff-match-patch).
- `cli.py`: CLI entrypoint (`ingest`, `parse`, `extract-references`, `detect-conflicts`, etc.).

### Tests (`normattiva_kb/tests/`)
- XML fixtures for unit tests.
- Parser/reference extraction smoke tests.
