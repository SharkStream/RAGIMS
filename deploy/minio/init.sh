#!/bin/sh
# Create the MinIO buckets required by RAGIMS. Idempotent: safe to re-run.
# Runs inside the `minio-init` service (minio/mc image); config via env vars.
set -e

MC_ALIAS="local"
MC_ENDPOINT="${MINIO_ENDPOINT:-http://minio:9000}"
MC_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
MC_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"

# Register the MinIO endpoint as an mc alias.
mc alias set "$MC_ALIAS" "$MC_ENDPOINT" "$MC_ACCESS_KEY" "$MC_SECRET_KEY"

# raw-docs  -> original uploaded files
# parsed-text -> extracted/cleaned text artifacts
for bucket in raw-docs parsed-text; do
  mc mb --ignore-existing "$MC_ALIAS/$bucket"
done

echo "MinIO buckets ready: raw-docs, parsed-text"
