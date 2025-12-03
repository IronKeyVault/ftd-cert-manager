# FTD Certificate Manager

Automated certificate management for Cisco FTD 1010 via FMC using Let's Encrypt and wingpy.

## Overview

This project automates the process of:
1. Requesting SSL/TLS certificates from Let's Encrypt for FTD RA VPN
2. Automatically renewing certificates
3. Uploading certificates to Cisco FMC via API (wingpy)
4. Configuring certificates for use on FTD devices

## Prerequisites

- Python 3.8 or newer
- Certbot (for Let's Encrypt)
- Access to Cisco FMC with admin privileges
- FTD device registered in FMC
- Cloudflare account (for automatic DNS validation)
- Systemd (for automatic renewal)

## Installation

### 1. Clone or download the project

```bash
cd ~/projects
# The project should already be here as ftd-cert-manager
cd ftd-cert-manager
```

### 2. Run the setup script

```bash
./setup.sh
```

This will:
- Create a Python virtual environment
- Install all necessary packages
- Create required directories
- Set correct permissions

### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in your information:

```bash
cp .env.example .env
nano .env
```

Important fields to configure:

```bash
# Let's Encrypt configuration
LETSENCRYPT_EMAIL=your-email@example.com
DOMAIN_NAME=vpn.yourdomain.com

# FMC configuration
FMC_HOST=192.168.x.x
FMC_USERNAME=apiuser
FMC_PASSWORD=your_password_here
FMC_VERIFY_SSL=false
FMC_AUTO_DEPLOY=false

# FTD configuration
FTD_DEVICE_NAME=FTD1010
FTD_CERT_NAME=RA-VPN-cert

# Certbot configuration
CERTBOT_STAGING=false
CERTBOT_DNS_PROVIDER=cloudflare
```

### 4. Configure Cloudflare DNS

Create `.cloudflare-credentials` file:

```bash
nano .cloudflare-credentials
```

Add your Cloudflare API token:

```
dns_cloudflare_api_token = your_cloudflare_api_token_here
```

Set correct permissions:

```bash
chmod 600 .cloudflare-credentials
```

#### How to get Cloudflare API Token:

1. Go to https://dash.cloudflare.com/profile/api-tokens
2. Click **Create Token**
3. Select **Edit zone DNS** template
4. **Zone Resources:** Include > Specific zone > **your-domain.com**
5. Click **Continue to summary** → **Create Token**
6. Copy the token (shown only once!)

## Usage

### Manual certificate renewal

```bash
# Activate virtual environment
source venv/bin/activate

# Run cert manager
./cert_manager.py
```

### Test with Let's Encrypt staging environment

To test without hitting rate limits:

```bash
# Set CERTBOT_STAGING=true in .env file
nano .env
# Change: CERTBOT_STAGING=true

# Run test
./cert_manager.py
```

### Automatic renewal with systemd

Install systemd service and timer:

```bash
# Copy systemd files
sudo cp systemd/ftd-cert-renew.service /etc/systemd/system/
sudo cp systemd/ftd-cert-renew.timer /etc/systemd/system/

# Enable and start timer
sudo systemctl daemon-reload
sudo systemctl enable ftd-cert-renew.timer
sudo systemctl start ftd-cert-renew.timer

# Check status
sudo systemctl status ftd-cert-renew.timer
sudo systemctl list-timers --all | grep ftd-cert
```

## Certificate Naming

Certificates are automatically named with year-month suffix:
- Base name in `.env`: `FTD_CERT_NAME=RA-VPN-cert`
- Created certificate: `RA-VPN-cert-2025-12`
- Next month: `RA-VPN-cert-2026-01`

This makes it easy to track certificate versions in FMC.

## Cloudflare DNS Challenge

The system uses Cloudflare DNS plugin for fully automatic certificate validation:

**Advantages:**
- ✅ No manual DNS updates required
- ✅ Works even when FTD is not publicly accessible
- ✅ Completely automated renewal process

**Setup:**
1. Transfer DNS management to Cloudflare (free)
2. Create API token with DNS edit permissions
3. Save token in `.cloudflare-credentials`
4. Set `CERTBOT_DNS_PROVIDER=cloudflare` in `.env`

## Auto-Deploy Feature

The system can optionally auto-deploy certificate changes to FTD:

**Disabled (default):**
```bash
FMC_AUTO_DEPLOY=false
```
- Certificate is uploaded to FMC
- Manual deployment required via FMC GUI

**Enabled:**
```bash
FMC_AUTO_DEPLOY=true
```
- Certificate is uploaded to FMC
- Automatically deploys to FTD if pending changes exist

**Important:** Auto-deploy will deploy ALL pending changes on the FTD device, not just the certificate.

## Security

- Keep your `.env` file secure - it contains passwords
- `.env` is already in `.gitignore` so it won't be committed to git
- Consider using a dedicated FMC user account with limited privileges
- Private keys are stored in `certs/` directory with restricted permissions
- Cloudflare API token is stored in `.cloudflare-credentials` with 600 permissions

## Project Structure

```
ftd-cert-manager/
├── cert_manager.py          # Main script
├── requirements.txt         # Python dependencies
├── .env.example            # Example configuration
├── .env                    # Your configuration (git ignored)
├── .cloudflare-credentials # Cloudflare API token (git ignored)
├── setup.sh               # Installation script
├── README.md              # Danish documentation
├── README-EN.md           # This file (English)
├── certs/                 # Certificates stored here
├── logs/                  # Log files
├── scripts/               # Helper scripts
└── systemd/              # Systemd service files
    ├── ftd-cert-renew.service
    └── ftd-cert-renew.timer
```

## Logs

Logs are stored in `logs/` directory with date in filename:

```bash
tail -f logs/cert-manager-$(date +%Y%m%d).log
```

## Troubleshooting

### Certbot errors

Check that certbot is installed:
```bash
certbot --version
```

### FMC connection errors

Test FMC connection:
```bash
python3 -c "from wingpy import CiscoFMC; fmc = CiscoFMC(base_url='https://YOUR_FMC_IP', username='admin', password='password', verify=False); print('Connected!')"
```

### Cloudflare DNS errors

Verify that:
- Your domain is using Cloudflare nameservers
- API token has correct permissions
- Token is correctly saved in `.cloudflare-credentials`

Test DNS:
```bash
dig NS yourdomain.com
```

Should show Cloudflare nameservers.

### Permission issues

Certbot typically requires sudo access. Make sure the script can run with sudo or run it as root.

## FMC Deployment

After the certificate is uploaded to FMC, you need to:

1. Log in to FMC GUI
2. Go to Devices > Device Management
3. Find your FTD device
4. Go to RA VPN configuration
5. Select the new certificate
6. Deploy configuration to FTD

With `FMC_AUTO_DEPLOY=true`, step 6 is automatic.

## Let's Encrypt Rate Limits

Let's Encrypt has rate limits:
- 50 certificates per registered domain per week
- 5 failed validations per account, per hostname, per hour

Use staging environment for testing to avoid hitting limits.

## API Documentation

- wingpy documentation: https://wingpy.automation.wingmen.dk/
- FMC API documentation: Check your FMC's built-in API Explorer at `https://YOUR_FMC_IP/api/api-explorer/`

## How It Works

1. **Certificate Request:** Script requests certificate from Let's Encrypt using Cloudflare DNS challenge
2. **DNS Validation:** Cloudflare plugin automatically creates TXT record for domain validation
3. **Certificate Retrieval:** Let's Encrypt validates domain and issues certificate
4. **Local Storage:** Certificate and private key are copied to `certs/` directory
5. **FMC Upload:** Certificate is uploaded to FMC as Internal Certificate via API
6. **Optional Deploy:** If enabled, changes are automatically deployed to FTD
7. **Logging:** All actions are logged with timestamps

## Automated Renewal

The systemd timer runs daily at 3:00 AM:
- Checks if certificate needs renewal (Let's Encrypt certificates expire after 90 days)
- Automatically renews if needed (typically 30 days before expiry)
- Uploads renewed certificate to FMC
- Optionally deploys to FTD
- Sends email notification (if configured)

## Email Notifications

To enable email notifications, install mailutils:

```bash
sudo apt install mailutils
```

Then set in `.env`:
```bash
NOTIFICATION_EMAIL=your-email@example.com
```

You'll receive notifications about:
- Successful certificate renewals
- Failed renewal attempts
- Upload status to FMC

## License

This project is for internal use at Wingmen Solutions / AI-Chatbot.dk

## Author

Kasper Elsborg (kasper@elsborg.eu)

## Support

For issues or questions:
- Check the logs in `logs/` directory
- Review FMC API Explorer for endpoint details
- Consult wingpy documentation: https://wingpy.automation.wingmen.dk/

## Version History

- **v1.0** (Dec 2025) - Initial release
  - Let's Encrypt integration with Cloudflare DNS
  - FMC API upload via wingpy
  - Automatic date-based certificate naming
  - Optional auto-deploy to FTD
  - Systemd timer for automated renewal
