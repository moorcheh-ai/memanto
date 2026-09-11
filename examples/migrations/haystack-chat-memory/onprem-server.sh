#!/usr/bin/env bash
# Start the official ARM64 server against the native Ollama instance from README.
set -euo pipefail
image='moorcheh/server@sha256:10598b965f29e8f748ecc3fa345a7abdcd0340d44f32fa2019b5c83551ea3733'
name='memanto-haystack-example'
volume='memanto-haystack-example-data'
if docker container inspect "$name" >/dev/null 2>&1; then
  echo "Container $name already exists; inspect it before restarting this example." >&2
  exit 1
fi
docker run --detach --name "$name" --publish 127.0.0.1:18080:8080 \
  --env SERVER_HOST=0.0.0.0 --env SERVER_PORT=8080 \
  --env EMBEDDING_PROVIDER=ollama --env EMBEDDING_MODEL=all-minilm-haystack \
  --env EMBEDDING_BASE_URL=http://host.docker.internal:11435 \
  --env OLLAMA_URL=http://host.docker.internal:11435 --env OLLAMA_MODEL=all-minilm-haystack \
  --env LLM_PROVIDER=ollama --env LLM_MODEL=qwen2.5 \
  --env LLM_BASE_URL=http://host.docker.internal:11435 \
  --env DATA_FILE=/app/data/moorcheh_data_store.json \
  --env NAMESPACE_REGISTRY_FILE=/app/data/namespace_registry.json \
  --env FILE_REGISTRY_FILE=/app/data/file_registry.json \
  --env CHUNKER_URL=http://127.0.0.1:8090 \
  --mount "type=volume,src=$volume,dst=/app/data" "$image"
# The official image runs as UID/GID 65532; new named volumes start owned by root.
docker exec --user 0 "$name" chown 65532:65532 /app/data
printf 'Server started on localhost:18080. Stop with: docker stop %s\n' "$name"
