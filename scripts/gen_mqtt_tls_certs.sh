#!/usr/bin/env bash
# Generate lab-only self-signed certs for Mosquitto TLS demo (8883).
# Not for production. Do not commit the generated files.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${OUT:-${ROOT}/deploy/demo/certs}"
mkdir -p "${OUT}"

# Include localhost / 127.0.0.1 SANs so paho verify works against lab bind.
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "${OUT}/server.key" \
  -out "${OUT}/server.crt" \
  -days 30 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

chmod 600 "${OUT}/server.key"
echo "Wrote ${OUT}/server.crt and ${OUT}/server.key (lab only, gitignored)"
