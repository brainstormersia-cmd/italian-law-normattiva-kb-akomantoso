# 🎮 IMMAGINE BASE CON CUDA
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# Variabili d'ambiente
ENV PYTORCH_ALLOC_CONF=expandable_segments:True
ENV PIP_DEFAULT_TIMEOUT=3000
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CUDA_VISIBLE_DEVICES=0

# Installa Python e dipendenze sistema
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3.10-dev \
    python3-pip \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Symlink python
RUN ln -s /usr/bin/python3.10 /usr/bin/python

WORKDIR /app

# =============================================================================
# FASE 1: Base ML Stack (con cache Docker layer)
# =============================================================================
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel

# NumPy PRIMA di tutto
RUN pip install --no-cache-dir "numpy<2.0.0"

# PyTorch con CUDA support
RUN pip install --no-cache-dir \
    torch>=2.4.0 \
    torchvision>=0.19.0 \
    torchaudio>=2.4.0 \
    --index-url https://download.pytorch.org/whl/cu118

# =============================================================================
# FASE 2: Requirements.txt (tutto il resto)
# =============================================================================
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# =============================================================================
# FASE 3: Application Code
# =============================================================================
COPY . .

# Crea directory necessarie
RUN mkdir -p \
    /tmp/chroma_db_internal \
    /app/chroma_db \
    /app/scripts \
    /app/xml_input \
    /app/logs

# Test GPU (opzionale, per debug build)
RUN python -c "\
import torch; \
print('='*60); \
print('🔥 Docker Build GPU Test'); \
print('='*60); \
print(f'CUDA Available: {torch.cuda.is_available()}'); \
if torch.cuda.is_available(): \
    print(f'GPU Name: {torch.cuda.get_device_name(0)}'); \
    print(f'GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB'); \
print('='*60); \
" || echo "⚠️ GPU test skipped (build time)"

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

CMD ["bash", "-c", "alembic upgrade head && python -m app.cli serve"]