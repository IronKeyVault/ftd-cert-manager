#!/bin/bash
# Check RA VPN certificate expiry and send email reminder.
# Run daily via systemd timer to alert when cert expires within 14 days.
#
# Configuration loaded from ftd-cert-manager (~/ftd-cert-manager/config.json + keyring).

set -e

WORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$WORK_DIR"

if [ -d "venv" ]; then
    source venv/bin/activate
fi

if ! command -v ftd-cert-manager &> /dev/null; then
    echo "ERROR: ftd-cert-manager CLI not found"
    exit 1
fi
eval "$(ftd-cert-manager --export-env)"

CERT_FILE="$WORK_DIR/vpn-complete.p12"
DAYS_WARNING=14

if [ -z "$PKCS12_PASSWORD" ] || [ -z "$LETSENCRYPT_EMAIL" ] || [ -z "$DOMAIN_NAME" ]; then
    echo "ERROR: Configuration incomplete. Run: ftd-cert-manager --setup"
    exit 1
fi

if [ ! -f "$CERT_FILE" ]; then
    echo "ERROR: PKCS12 file not found: $CERT_FILE"
    exit 1
fi

EXPIRY=$(openssl pkcs12 -in "$CERT_FILE" -nokeys -passin pass:"$PKCS12_PASSWORD" 2>/dev/null | \
    openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)

if [ -z "$EXPIRY" ]; then
    echo "ERROR: Could not read certificate expiry date"
    exit 1
fi

EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s)
NOW_EPOCH=$(date +%s)
DAYS_LEFT=$(( (EXPIRY_EPOCH - NOW_EPOCH) / 86400 ))

echo "Certificate expires: $EXPIRY"
echo "Days remaining: $DAYS_LEFT"

if [ "$DAYS_LEFT" -le "$DAYS_WARNING" ]; then
    SUBJECT="RA VPN Certificate Expires in $DAYS_LEFT Days"
    BODY="Your RA VPN certificate for $DOMAIN_NAME will expire on $EXPIRY.

Certificate Details:
- Domain: $DOMAIN_NAME
- FTD device: $FTD_NAME ($FTD_IP)
- Expires: $EXPIRY
- Days remaining: $DAYS_LEFT

RENEWAL STEPS:
1. SSH to this server
2. cd $WORK_DIR
3. ./renew_cert.sh
4. FMC GUI: Devices > Certificates > Add
5. Device: $FTD_NAME, Cert Enrollment: $FTD_CERT_NAME
6. Click Add. FMC auto-deploys to FTD.

Next renewal should be done before: $(date -d "$EXPIRY - 7 days" '+%Y-%m-%d')
"

    if command -v mail &> /dev/null; then
        echo "$BODY" | mail -s "$SUBJECT" "$LETSENCRYPT_EMAIL"
        echo "Email sent to $LETSENCRYPT_EMAIL"
    else
        echo "WARNING: 'mail' command not found. Install with: sudo apt install mailutils"
        echo "$SUBJECT"
        echo "$BODY"
    fi
fi
