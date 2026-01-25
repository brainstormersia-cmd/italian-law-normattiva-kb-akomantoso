FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md /app/
RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir -e .
COPY . /app
CMD ["bash", "-lc", "alembic upgrade head && python -m app.cli serve"]
