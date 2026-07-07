#!/usr/bin/env bash
# Run from skill folder root. Requires: python3, CODEHUB_TOKEN
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
: "${CODEHUB_TOKEN:?export CODEHUB_TOKEN=your-token}"

export CODEHUB_BASE_URL="${CODEHUB_BASE_URL:-https://open.codehub.huawei.com}"
export CODEHUB_PROJECT="${CODEHUB_PROJECT:-OpenSourceCenter_CR/openharmony/filemanagement_app_file_service}"

python3 scripts/fetch_codehub_crs.py \
  --classes "${STABILITY_CLASSES:-appfreeze,jserror,jsleak,memoryleak}" \
  --state "${MR_STATE:-merged}" \
  "$@"
