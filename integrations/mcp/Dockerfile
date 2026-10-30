FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY . /app
RUN pip install .

# Run as a non-root user. memanto keeps its local state in ~/.memanto,
# so the user needs a writable home directory.
RUN useradd --create-home --uid 1000 memanto
USER memanto

ENTRYPOINT ["memanto-mcp"]
