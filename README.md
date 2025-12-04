# FTD Certificate Manager

Automated Let's Encrypt certificate management for Cisco FTD RA VPN.

## Status

✅ **Automated (Step 1/2):**
- Let's Encrypt certificate generation (DNS-01 challenge via Cloudflare)
- PKCS12 bundle creation
- FMC enrollment update via REST API
- Email expiry reminders (14 days before)

⚠️ **Manual (Step 2/2):**
- Link enrollment to device via FMC GUI (Devices > Certificates > Add)
- No REST API endpoint exists for this step

## Why 2 Steps?

**Step 1 - Enrollment Update (Automated):**
- Updates PKCS12 enrollment object with new certificate via API
- Endpoint: `PUT /object/certenrollments/{id}`
- Payload: `pkcs12Content: {passPhrase, base64Certificate}`

**Step 2 - Device Assignment (Manual):**
- Links enrollment to FTD device  
- FMC GUI: Devices > Certificates > Add
- No equivalent REST API endpoint exists in FMC

Once linked, FMC auto-deploys to FTD.
- Sætte korrekte rettigheder

### 3. Konfigurer credentials

**Mulighed A: Brug Bitwarden (Anbefalet til produktion)**

Se detaljeret guide: [BITWARDEN.md](BITWARDEN.md)

Hurtig start:
```bash
# Installer Bitwarden CLI
npm install -g @bitwarden/cli

# Opret vault item med dine credentials
# Se BITWARDEN.md for komplet setup

# Kør med Bitwarden
./run_with_bitwarden.sh
```

**Mulighed B: Brug .env fil**

Kopier `.env.example` til `.env` og udfyld dine oplysninger:

```bash
## Prerequisites

- Python 3.8+
- Certbot with Cloudflare DNS plugin
- Cisco FMC with API access
- FTD device registered in FMC
- Cloudflare account for DNS-01 challenge
- Systemd for scheduled monitoring

## Setup

1. **Install dependencies:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install wingpy certbot certbot-dns-cloudflare python-dotenv
   ```

2. **Configure Cloudflare credentials:**
   ```bash
   nano .cloudflare-credentials
   # Add: dns_cloudflare_api_token = your_token_here
   chmod 600 .cloudflare-credentials
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   nano .env
   ```
   
   Required settings:
   ```bash
   DOMAIN_NAME=vpn.ai-chatbot.dk
   LETSENCRYPT_EMAIL=your@email.com
   FMC_HOST=192.168.0.247
   FMC_USERNAME=apiuser
   FMC_PASSWORD=your_password
   FTD_CERT_NAME=RA-VPN-cert
   ```

4. **Create PKCS12 enrollment in FMC (one-time):**
   - FMC GUI: **Devices > Certificates > Add > Certificate Enrollment**
   - Name: `RA-VPN-cert`
   - Type: `PKCS12`
   - Save

5. **Install expiry monitoring:**
   ```bash
   sudo cp systemd/cert-expiry-check.* /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now cert-expiry-check.timer
   ```

## Usage

### Generate New Certificate

```bash
./renew_cert.sh
```

Output: `vpn-complete.p12` with password `cisco123`

### Import to FMC

**Step 1/2 - Automated (included in script):**
```bash
./renew_cert.sh
```
This updates the enrollment with new PKCS12 data via API.

**Step 2/2 - Manual GUI (one-time per renewal):**
1. Open FMC: `https://192.168.0.247`
2. Navigate: **Devices > Certificates**
3. Click: **Add**
4. Device: **FTD1010**
5. Cert Enrollment: **RA-VPN-cert**
6. Click: **Add**

FMC then auto-deploys certificate to FTD1010.

### Verify on FTD

```bash
ssh admin@192.168.0.246
show crypto ca certificates
```

## Certificate Lifecycle

- **Validity:** 90 days (Let's Encrypt)
- **Issuer:** Let's Encrypt R11/R12/R13/R14 (rotating intermediates)
- **Renewal window:** 14 days before expiry
- **Monitoring:** Daily systemd timer checks expiry
- **Alerts:** Email sent 14 days before expiration

## Limitations

**Let's Encrypt Rate Limits:**
- 5 certificates per exact identifier set per 168 hours
- If hit: wait until retry date or use existing certificate

**FMC API Limitation:**
- No support for PKCS12 certificate import via REST API
- Manual GUI import required for every renewal
- FMC auto-deploys after GUI import

## Files

- `renew_cert.sh` - Main certificate renewal script
- `check_cert_expiry.sh` - Monitors PKCS12 expiry, sends email alerts
- `fmc_wingpy_import.py` - Non-functional API import attempt (reference only)
- `vpn-complete.p12` - Current certificate bundle (git ignored)
- `.cloudflare-credentials` - Cloudflare DNS API token
- `.env` - Configuration (git ignored)
- `systemd/cert-expiry-check.*` - Daily expiry monitoring

## Project Structure

```
ftd-cert-manager/
├── renew_cert.sh                    # Certificate generation
├── check_cert_expiry.sh            # Expiry monitoring
├── fmc_wingpy_import.py            # API reference
├── .env                            # Configuration
├── .cloudflare-credentials         # DNS API token
├── vpn-complete.p12               # Current certificate
├── certs/                         # Certificate files
├── logs/                          # Log files
└── systemd/
    ├── cert-expiry-check.service
    └── cert-expiry-check.timer
```

## Troubleshooting

**"Too many certificates already issued"**
```
Error: too many certificates (5) already issued
```
Solution: Wait until retry date or use existing `vpn-complete.p12`

**Certificate not visible in FMC**
- Don't rely on API import - it doesn't work
- Use GUI import: Devices > Certificates > RA-VPN-cert
- Verify PKCS12: `openssl pkcs12 -info -in vpn-complete.p12`

**FTD not receiving certificate**
- Check FMC: Deploy > Deployment
- If pending changes exist, deploy manually
- Verify on FTD: `show crypto ca certificates`

**Email alerts not working**
- Check systemd timer: `systemctl status cert-expiry-check.timer`
- Test manually: `./check_cert_expiry.sh`
- Verify mail command: `echo "test" | mail -s "test" your@email.com`

## Logs

```bash
tail -f logs/cert-manager-$(date +%Y%m%d).log
```

## Fejlfinding

### Certbot fejl

Tjek at certbot er installeret:
```bash
certbot --version
```

### FMC connection fejl

Test FMC forbindelse:
```bash
python3 -c "from wingpy import CiscoFMC; fmc = CiscoFMC(base_url='https://YOUR_FMC_IP', username='admin', password='password', verify=False); print('Connected!')"
```

### DNS Challenge fejl

Sørg for at din DNS provider credentials er korrekt sat op og har de nødvendige rettigheder.

### Rettigheder

Certbot kræver typisk sudo adgang. Sørg for at scriptet kan køre med sudo eller kør det som root.

Logs stored in `logs/` directory.

## References

- **Let's Encrypt:** https://letsencrypt.org/docs/rate-limits/
- **wingpy:** https://wingpy.automation.wingmen.dk/
- **FMC API:** Check FMC GUI built-in API Explorer
- **Certbot:** https://certbot.eff.org/

## Author

Kasper Elsborg - AI-Chatbot.dk / Wingmen Solutions


Kasper Elsborg (kasper@elsborg.eu)
