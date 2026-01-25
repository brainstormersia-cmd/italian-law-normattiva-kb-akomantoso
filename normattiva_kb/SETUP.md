# Clean setup guide

This guide describes a clean, repeatable setup for local development and Docker-based startup.

## 1) Prerequisites

- Python 3.11+
- Docker + Docker Compose (for containerized DB/API)
- Postgres 15+ (if running outside Docker)

## 2) Docker-based setup (recommended)

1. Copy env file and adjust values:

```bash
cp .env.example .env
```

2. Build and start containers:

```bash
docker-compose up --build
```

3. Apply migrations (if the container does not auto-run them):

```bash
docker-compose exec app alembic upgrade head
```

4. Verify health endpoint:

```bash
curl http://localhost:8000/health
```

## 3) Local (non-Docker) setup

1. Create a virtualenv and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configure environment variables (see `.env.example`).

3. Initialize DB schema:

```bash
alembic upgrade head
```

4. Run API:

```bash
python -m app.cli serve
```

## 4) CLI quickstart

```bash
python -m app.cli ingest --dir /path/to/xml
python -m app.cli parse
python -m app.cli extract-references
python -m app.cli resolve-references
python -m app.cli detect-conflicts
```

## 5) Clean reset (development only)

Use only in local/dev environments.

```bash
docker-compose down -v
```

Recreate volumes with:

```bash
docker-compose up --build
```
