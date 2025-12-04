#!/bin/bash
# Check RA VPN certificate expiry and send email reminder
# Run daily to check if certificate expires within 14 days

CERT_FILE="/home/kasperadm/projects/ftd-cert-manager/vpn-with-password.p12"
PASSWORD="cisco123"
EMAIL="kasper@elsborg.eu"
DAYS_WARNING=14

# Extract expiry date from PKCS12
EXPIRY=$(openssl pkcs12 -in "$CERT_FILE" -nokeys -passin pass:$PASSWORD 2>/dev/null | \
    openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)

if [ -z "$EXPIRY" ]; then
    echo "ERROR: Could not read certificate expiry date"
    exit 1
fi

# Convert to epoch timestamp
EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s)
NOW_EPOCH=$(date +%s)
DAYS_LEFT=$(( ($EXPIRY_EPOCH - $NOW_EPOCH) / 86400 ))

echo "Certificate expires: $EXPIRY"
echo "Days remaining: $DAYS_LEFT"

if [ $DAYS_LEFT -le $DAYS_WARNING ]; then
    SUBJECT="⚠️ RA VPN Certificate Expires in $DAYS_LEFT Days"
    BODY="Your RA VPN certificate for vpn.ai-chatbot.dk will expire on $EXPIRY.

Certificate Details:
- Domain: vpn.ai-chatbot.dk
- Expires: $EXPIRY
- Days remaining: $DAYS_LEFT

RENEWAL STEPS:
1. SSH to Linux server
2. cd /home/kasperadm/projects/ftd-cert-manager
3. ./renew_cert.sh
4. Copy vpn-complete.p12 to Windows PC
5. FMC GUI: Devices > Certificates > RA-VPN-cert > Import Identity Certificate
6. Upload vpn-complete.p12 (password: cisco123)
7. FMC will auto-deploy to FTD

Next renewal should be done before: $(date -d "$EXPIRY - 7 days" '+%Y-%m-%d')
"

    # Send email using mail command (requires mailutils)
    if command -v mail &> /dev/null; then
        echo "$BODY" | mail -s "$SUBJECT" "$EMAIL"
        echo "Email sent to $EMAIL"
    else
        echo "WARNING: 'mail' command not found. Install with: sudo apt install mailutils"
        echo "$SUBJECT"
        echo "$BODY"
    fi
fi
