#!/usr/bin/env bash
# Generate lab TLS + optional client certs for twinopsctl serve (HTTPS / mTLS).
# Not for production. Do not commit generated files.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${OUT:-${ROOT}/deploy/demo/live-certs}"
mkdir -p "${OUT}"

# CA
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "${OUT}/ca.key" \
  -out "${OUT}/ca.crt" \
  -days 30 \
  -subj "/CN=twinops-lab-ca"

# Server (SAN localhost / 127.0.0.1)
openssl req -newkey rsa:2048 -nodes \
  -keyout "${OUT}/server.key" \
  -out "${OUT}/server.csr" \
  -subj "/CN=localhost"
openssl x509 -req -in "${OUT}/server.csr" -CA "${OUT}/ca.crt" -CAkey "${OUT}/ca.key" \
  -CAcreateserial -out "${OUT}/server.crt" -days 30 \
  -extfile <(printf "subjectAltName=DNS:localhost,IP:127.0.0.1")

# Client (mTLS)
openssl req -newkey rsa:2048 -nodes \
  -keyout "${OUT}/client.key" \
  -out "${OUT}/client.csr" \
  -subj "/CN=twinops-lab-client"
openssl x509 -req -in "${OUT}/client.csr" -CA "${OUT}/ca.crt" -CAkey "${OUT}/ca.key" \
  -CAcreateserial -out "${OUT}/client.crt" -days 30

rm -f "${OUT}/server.csr" "${OUT}/client.csr" "${OUT}/ca.srl"
chmod 600 "${OUT}"/*.key
echo "Wrote lab certs under ${OUT} (gitignored)"
echo "  HTTPS:  --tls-cert ${OUT}/server.crt --tls-key ${OUT}/server.key"
echo "  mTLS:   add --tls-client-ca ${OUT}/ca.crt"
echo "  client: ${OUT}/client.crt + ${OUT}/client.key"
