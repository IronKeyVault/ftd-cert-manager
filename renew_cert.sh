#!/bin/bash
# RA VPN Certificate Renewal Script
# Usage: ./renew_cert.sh
# Run every ~75 days to renew the Let's Encrypt certificate.
#
# Configuration is loaded from ftd-cert-manager (~/ftd-cert-manager/config.json
# + OS keyring). Run `ftd-cert-manager --setup` first.

set -e

WORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$WORK_DIR"

# Activate Python venv if present
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Pull config + secrets from ftd-cert-manager
if ! command -v ftd-cert-manager &> /dev/null; then
    echo "ERROR: ftd-cert-manager CLI not found. Install with: pip install -e ."
    exit 1
fi
eval "$(ftd-cert-manager --export-env)"

if [ -z "$DOMAIN_NAME" ] || [ -z "$LETSENCRYPT_EMAIL" ] || [ -z "$PKCS12_PASSWORD" ]; then
    echo "ERROR: Configuration incomplete. Run: ftd-cert-manager --setup"
    exit 1
fi

CLOUDFLARE_CREDS="$WORK_DIR/.cloudflare-credentials"
PERMANENT_KEY="$WORK_DIR/certs/vpn-private.key"

# If the static creds file is missing, materialize one from keyring (if set)
if [ ! -f "$CLOUDFLARE_CREDS" ]; then
    CLOUDFLARE_CREDS="$(mktemp -t cloudflare-creds.XXXXXX)"
    trap 'rm -f "$CLOUDFLARE_CREDS"' EXIT
    if ! ftd-cert-manager --write-cf-creds "$CLOUDFLARE_CREDS"; then
        echo "ERROR: No .cloudflare-credentials file and no token in keyring."
        echo "       Either create the file, or run: ftd-cert-manager --setup"
        exit 1
    fi
fi

echo "=== RA VPN Certificate Renewal ==="
echo "Domain: $DOMAIN_NAME"
echo "FTD device: $FTD_NAME ($FTD_IP)"
echo "Working directory: $WORK_DIR"
echo ""

# Use existing private key or generate new one (first time only)
if [ -f "$PERMANENT_KEY" ]; then
    echo "[1/4] Using existing private key (from certs/)..."
    cp "$PERMANENT_KEY" vpn-private.key
    echo "  Key reused to avoid key sprawl on FTD"
else
    echo "[1/4] Generating new private key (first time)..."
    mkdir -p "$(dirname "$PERMANENT_KEY")"
    openssl genrsa -out vpn-private.key 2048
    cp vpn-private.key "$PERMANENT_KEY"
    chmod 600 "$PERMANENT_KEY"
    echo "  Key saved to: $PERMANENT_KEY"
    echo "  Future renewals will reuse this key"
fi

# Create CSR
echo "[2/4] Creating certificate signing request..."
openssl req -new -key vpn-private.key -out vpn.csr \
    -subj "/C=DK/CN=$DOMAIN_NAME/emailAddress=$LETSENCRYPT_EMAIL" \
    -addext "subjectAltName=DNS:$DOMAIN_NAME"

# Sign with Let's Encrypt
echo "[3/4] Signing certificate with Let's Encrypt (DNS-01 challenge)..."
CERTBOT="$(command -v certbot || true)"
if [ -z "$CERTBOT" ]; then
    echo "ERROR: certbot not found. Install with: pip install -e . (in venv)"
    exit 1
fi
sudo "$CERTBOT" certonly --csr vpn.csr \
    --dns-cloudflare \
    --dns-cloudflare-credentials "$CLOUDFLARE_CREDS" \
    --non-interactive \
    --agree-tos \
    --email "$LETSENCRYPT_EMAIL"

# Find the latest certificate files (certbot creates numbered files)
CERT_FILE=$(ls -t 000*_cert.pem 2>/dev/null | head -1)
CHAIN_FILE=$(ls -t 000*_chain.pem 2>/dev/null | tail -1)

if [ -z "$CERT_FILE" ]; then
    echo "ERROR: Certificate file not found!"
    exit 1
fi

echo "Certificate: $CERT_FILE"
echo "Full chain: $CHAIN_FILE"

# Create PKCS12 bundle
echo "[4/4] Creating PKCS12 file with password..."
openssl pkcs12 -export \
    -out vpn-complete.p12 \
    -inkey vpn-private.key \
    -in "$CHAIN_FILE" \
    -passout pass:"$PKCS12_PASSWORD"

echo ""
echo "=== SUCCESS ==="
echo "PKCS12 file created: vpn-complete.p12"
echo ""
echo "Certificate details:"
openssl pkcs12 -in vpn-complete.p12 -nokeys -passin pass:"$PKCS12_PASSWORD" | \
    openssl x509 -noout -subject -issuer -dates
echo ""
echo "Run 'ftd-cert-manager --import' to upload to FMC,"
echo "or 'ftd-cert-manager --import --renew' next time to do both in one go."
