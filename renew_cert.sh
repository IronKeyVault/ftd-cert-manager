#!/bin/bash
# RA VPN Certificate Renewal Script
# Usage: ./renew_cert.sh
# Run every 3 months to renew Let's Encrypt certificate

set -e

WORK_DIR="/home/kasperadm/projects/ftd-cert-manager"
cd "$WORK_DIR"

# Load configuration from .env
source "$WORK_DIR/.env"

# Activate Python environment
if [ -d "venv" ]; then
    source venv/bin/activate
fi

CLOUDFLARE_CREDS="$WORK_DIR/.cloudflare-credentials"
PASSWORD="cisco123"
PERMANENT_KEY="$WORK_DIR/certs/vpn-private.key"

echo "=== RA VPN Certificate Renewal ==="
echo "Domain: $DOMAIN_NAME"
echo "Working directory: $WORK_DIR"
echo ""

# Use existing private key or generate new one (first time only)
if [ -f "$PERMANENT_KEY" ]; then
    echo "[1/4] Using existing private key (from certs/)..."
    cp "$PERMANENT_KEY" vpn-private.key
    echo "  Key reused to avoid key sprawl on FTD"
else
    echo "[1/4] Generating new private key (first time)..."
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
sudo certbot certonly --csr vpn.csr \
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
    -passout pass:$PASSWORD

echo ""
echo "=== SUCCESS ==="
echo "PKCS12 file created: vpn-complete.p12"
echo "Password: $PASSWORD"
echo ""
echo "Certificate details:"
openssl pkcs12 -in vpn-complete.p12 -nokeys -passin pass:$PASSWORD | \
    openssl x509 -noout -subject -issuer -dates
echo ""
echo "=== Importing to FMC Enrollment ===" 
cd "$WORK_DIR"
source venv/bin/activate
FMC_PASSWORD="$(<.env grep FMC_PASSWORD | cut -d= -f2)" \
PKCS12_FILE=vpn-complete.p12 \
PKCS12_PASSWORD=$PASSWORD \
python3 fmc_wingpy_import.py
