#!/bin/sh
# Local/CI S3-compatible object storage (SeaweedFS). Production uses R2/S3; this only
# stands in for it, speaking the same S3 API the app uses.
#
# Two identities, generated from env so no credential is committed:
#   root  admin, used only by the init container to create the bucket
#   app   scoped to S3_BUCKET only (read/write/list), mirroring the per-environment,
#         bucket-scoped access key rule in Feature 01 §11
set -eu

: "${S3_ROOT_ACCESS_KEY:?S3_ROOT_ACCESS_KEY is required}"
: "${S3_ROOT_SECRET_KEY:?S3_ROOT_SECRET_KEY is required}"
: "${S3_ACCESS_KEY:?S3_ACCESS_KEY is required}"
: "${S3_SECRET_KEY:?S3_SECRET_KEY is required}"
: "${S3_BUCKET:?S3_BUCKET is required}"

umask 077
cat > /tmp/s3.json <<EOF
{
  "identities": [
    {
      "name": "root",
      "credentials": [{"accessKey": "${S3_ROOT_ACCESS_KEY}", "secretKey": "${S3_ROOT_SECRET_KEY}"}],
      "actions": ["Admin", "Read", "List", "Tagging", "Write"]
    },
    {
      "name": "app",
      "credentials": [{"accessKey": "${S3_ACCESS_KEY}", "secretKey": "${S3_SECRET_KEY}"}],
      "actions": ["Read:${S3_BUCKET}", "Write:${S3_BUCKET}", "List:${S3_BUCKET}", "Tagging:${S3_BUCKET}"]
    }
  ]
}
EOF

exec weed server \
  -dir=/data \
  -s3 -s3.port=8333 -s3.config=/tmp/s3.json \
  -master.volumeSizeLimitMB=64 \
  -volume.max=0
