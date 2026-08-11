# syntax=docker/dockerfile:1

# =====================================================================
# Stage 1: builder - has the compiler toolchain, produces a venv only
# =====================================================================
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml README.md ./
COPY shared ./shared

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    # CPU-only torch build. Plain `pip install torch` on Linux pulls the
    # CUDA-enabled wheel (1-2GB+) even though nothing here uses a GPU -
    # this one line is the single biggest size saving in this image.
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -e . && \
    # Strip test suites and bytecode caches that ship inside dependencies
    find /opt/venv -type d -name "tests" -prune -exec rm -rf {} + && \
    find /opt/venv -type d -name "test" -prune -exec rm -rf {} + && \
    find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + && \
    find /opt/venv -name "*.dist-info" -type d -exec sh -c 'rm -f "$1"/RECORD' _ {} \;

# =====================================================================
# Stage 2: runtime - slim base + venv only, no compiler/build tools
# =====================================================================
FROM python:3.12-slim

# libgomp1 is required at runtime by torch/faiss (OpenMP) and is not
# present in the slim base image by default.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY . .

# No CMD here on purpose - docker-compose.yml sets the right
# uvicorn/celery command for each service using this same image.