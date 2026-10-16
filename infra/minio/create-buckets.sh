#!/usr/bin/env sh
set -eu

until mc alias set local "${MINIO_ENDPOINT}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}"; do
  sleep 1
done

mc mb --ignore-existing "local/${OBJECT_STORAGE_BUCKET}"
mc anonymous set none "local/${OBJECT_STORAGE_BUCKET}"
