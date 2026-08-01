#!/bin/sh
# Generate internal CA + leaf certificates for inter-service mTLS.
#
# Idempotent: if ca.key exists, only missing leaf certs are created.
# Usage: gen-internal-certs.sh /certs
#
# This script is mounted into the cert-generator container and invoked
# by docker-compose.yml. It exists as a standalone file (rather than an
# inline YAML scalar) because:
#   - YAML block scalars cannot be linted with shellcheck
#   - Compose interpolates $variables at parse time (see F-01)
#   - A standalone file is diffable and testable in isolation.

set -euo pipefail

# Install openssl (alpine container is bare)
apk add --no-cache openssl > /dev/null 2>&1

CERTS_DIR="${1:?Usage: $0 <certs-dir>}"
mkdir -p "$CERTS_DIR"

CA_KEY="${CERTS_DIR}/ca.key"
CA_CRT="${CERTS_DIR}/ca.crt"

# CA — only generate once
if [ ! -f "$CA_KEY" ]; then
    echo "==> Generating CA key and self-signed certificate..."
    openssl genrsa -out "$CA_KEY" 4096
    openssl req -x509 -new -nodes \
        -key "$CA_KEY" \
        -sha256 -days 3650 \
        -out "$CA_CRT" \
        -subj '/CN=Internal CA'
else
    echo "==> CA key exists, skipping."
fi

# Extfile for subjectAltName (written fresh each run to pick up changes)
EXTFILE="${CERTS_DIR}/extfile.cnf"

for service in backend frontend postgres redis; do
    KEY="${CERTS_DIR}/${service}.key"
    CSR="${CERTS_DIR}/${service}.csr"
    CRT="${CERTS_DIR}/${service}.crt"

    if [ -f "$CRT" ]; then
        echo "==> ${service}.crt exists, skipping."
        continue
    fi

    echo "==> Generating certificate for ${service}..."
    openssl genrsa -out "$KEY" 2048
    openssl req -new \
        -key "$KEY" \
        -out "$CSR" \
        -subj "/CN=${service}"

    # SAN includes service name (for Docker DNS) and localhost (for health checks)
    cat > "$EXTFILE" <<EOF
subjectAltName = DNS:${service}, DNS:localhost
EOF

    openssl x509 -req \
        -in "$CSR" \
        -CA "$CA_CRT" \
        -CAkey "$CA_KEY" \
        -CAcreateserial \
        -out "$CRT" \
        -days 365 \
        -sha256 \
        -extfile "$EXTFILE"

    rm -f "$CSR"
    echo "==> ${service}.crt created."
done

# Ensure readable certs, private keys readable only by owner
chmod 644 "$CERTS_DIR"/*.crt
chmod 600 "$CERTS_DIR"/*.key

echo "==> All certificates ready."
