#!/bin/sh
# Idempotently create the private uploads bucket. Run by `make infra` and CI.
set -eu

: "${S3_BUCKET:?S3_BUCKET is required}"
MASTER="${SEAWEED_MASTER:-object-storage:9333}"

attempt=0
until echo "cluster.check" | weed shell -master="$MASTER" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "object storage did not become ready" >&2
    exit 1
  fi
  sleep 2
done

if echo "s3.bucket.list" | weed shell -master="$MASTER" 2>/dev/null | grep -qw "$S3_BUCKET"; then
  echo "bucket $S3_BUCKET already exists"
else
  echo "s3.bucket.create -name $S3_BUCKET" | weed shell -master="$MASTER"
fi
