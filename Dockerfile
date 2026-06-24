FROM python:3.12-slim

# Version baked into the image. Override at build time with:
#   docker build --build-arg VERSION=x.y.z .
ARG VERSION=0.1.1

# Prevent .pyc files and force stdout/stderr flush (important for container logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION}

WORKDIR /app

# Install uv — faster than pip for resolving and installing dependencies
RUN pip install --no-cache-dir uv

# ── Dependency layer ─────────────────────────────────────────────────────────
# Copy only the files that define dependencies first so Docker can cache this
# layer and avoid re-installing packages when only source code changes.
COPY pyproject.toml README.md ./

# Generate requirements.txt from pyproject.toml and install dependencies first
# This ensures that your dependency installation is properly cached!
RUN uv pip compile pyproject.toml -o requirements.txt && \
    uv pip install --system --no-cache -r requirements.txt

# ── Source layer ─────────────────────────────────────────────────────────────
COPY memanto/ ./memanto/

# Install the application itself without reinstalling dependencies
RUN uv pip install --system --no-cache --no-deps .

# ── Security: run as non-root ─────────────────────────────────────────────────
RUN useradd -m --shell /bin/false --uid 1001 memanto
USER memanto

EXPOSE 8000

# Use /ready — a lightweight endpoint that always returns 200 without calling
# the external Moorcheh API.  (Use /health if you want Moorcheh connectivity
# to gate the health check instead.)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready')" || exit 1

CMD ["uvicorn", "memanto.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
