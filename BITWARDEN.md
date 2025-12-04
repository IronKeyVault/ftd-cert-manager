# Bitwarden Integration for FTD Certificate Manager

This guide explains how to use Bitwarden password manager for secure credential storage instead of storing passwords in `.env` files.

## Why Bitwarden?

- **Secure**: Credentials stored encrypted in Bitwarden vault
- **Centralized**: One place for all secrets
- **No local files**: No `.env` or credential files with plain text passwords
- **Team sharing**: Share credentials securely with team members (Bitwarden Premium)
- **Audit trail**: Track who accessed credentials (Bitwarden Business)

## Prerequisites

- Bitwarden account (Free, Premium, or Business)
- Bitwarden CLI (`bw`) installed

## Installation

### Install Bitwarden CLI

Choose one method:

**Option 1: NPM (cross-platform)**
```bash
npm install -g @bitwarden/cli
```

**Option 2: Snap (Linux)**
```bash
sudo snap install bw
```

**Option 3: Download binary**
```bash
# Download from https://bitwarden.com/download/
curl -L "https://vault.bitwarden.com/download/?app=cli&platform=linux" -o bw.zip
unzip bw.zip
chmod +x bw
sudo mv bw /usr/local/bin/
```

Verify installation:
```bash
bw --version
```

## Setup Bitwarden Vault

### 1. Login to Bitwarden CLI

```bash
bw login
```

Enter your Bitwarden email and master password.

### 2. Create Vault Item for FMC Credentials

You can create the item in Bitwarden web vault or via CLI:

**Via Web Vault (easiest):**

1. Go to https://vault.bitwarden.com
2. Click "New Item"
3. Fill in:
   - **Name**: `FMC Certificate Manager`
   - **Type**: Login
   - **Username**: Your FMC username (e.g., `apiuser`)
   - **Password**: Your FMC password
   
4. Add Custom Fields (click "New custom field"):
   - `FMC_HOST` = `192.168.0.247` (your FMC IP/hostname)
   - `DOMAIN_NAME` = `vpn.ai-chatbot.dk` (your certificate domain)
   - `FTD_DEVICE_NAME` = `FTD1010` (your FTD device name)
   - `FTD_CERT_NAME` = `RA-VPN-cert` (certificate base name)
   - `CLOUDFLARE_TOKEN` = `your_cloudflare_api_token` (if using Cloudflare DNS)

5. Save the item

**Via CLI:**

```bash
bw unlock
export BW_SESSION="your_session_key"

# Create item (manual way)
bw get template item | jq '.name="FMC Certificate Manager" | .type=1' | bw encode | bw create item

# Better: Edit the item in web vault to add custom fields
```

### 3. Verify Item

```bash
bw unlock
export BW_SESSION="$(bw unlock --raw)"
bw get item "FMC Certificate Manager"
```

You should see your credentials in JSON format.

## Usage

### Method 1: Wrapper Script (Recommended)

Use the provided wrapper script that handles Bitwarden unlock automatically:

```bash
./run_with_bitwarden.sh
```

The script will:
1. Check if `bw` CLI is installed
2. Login to Bitwarden (if needed)
3. Unlock vault (prompts for master password)
4. Sync vault (get latest data)
5. Run `cert_manager.py` with `BW_SESSION` environment variable
6. Lock vault when done (if `BITWARDEN_AUTO_LOCK=true`)

### Method 2: Manual Session Management

If you want more control:

```bash
# Unlock vault and export session
bw login  # if not logged in
export BW_SESSION="$(bw unlock --raw)"

# Run cert manager (it will automatically fetch from Bitwarden)
sudo -E BW_SESSION="$BW_SESSION" venv/bin/python cert_manager.py

# Lock vault when done
bw lock
unset BW_SESSION
```

### Method 3: Hybrid (Bitwarden + .env fallback)

The cert_manager.py supports automatic fallback:

1. **Priority 1**: Environment variables (if set explicitly)
2. **Priority 2**: Bitwarden (if `BW_SESSION` is set)
3. **Priority 3**: `.env` file (fallback)

This means you can:
- Use Bitwarden for sensitive credentials (passwords, tokens)
- Keep non-sensitive config in `.env` (email, domains)
- Override anything with environment variables

Example:
```bash
# Use Bitwarden for FMC password, but override domain
export BW_SESSION="$(bw unlock --raw)"
export DOMAIN_NAME="test.example.com"
sudo -E venv/bin/python cert_manager.py
```

## Systemd Integration

To use Bitwarden with systemd timer, you need to keep the vault unlocked or use a different approach:

### Option 1: Long-lived Session (Less Secure)

```bash
# Unlock once and keep session
export BW_SESSION="$(bw unlock --raw)"
echo "export BW_SESSION='$BW_SESSION'" >> ~/.bashrc
```

Update systemd service:
```ini
[Service]
Type=oneshot
User=root
Environment="BW_SESSION=your_session_key_here"
ExecStart=/home/user/ftd-cert-manager/venv/bin/python /home/user/ftd-cert-manager/cert_manager.py
```

### Option 2: Bitwarden Secrets Manager (Recommended for Production)

Use Bitwarden Secrets Manager with machine accounts (requires Business plan):

1. Create a machine account in Bitwarden
2. Generate service account token
3. Use `bw config server https://your-org.bitwarden.com`
4. Store token in systemd environment

### Option 3: Hybrid Approach (Recommended)

Use Bitwarden for manual runs, `.env` for automated systemd runs:

- Manual runs: `./run_with_bitwarden.sh` (most secure)
- Systemd timer: Uses `.env` with restrictive permissions (`chmod 600`)

## Testing

Test Bitwarden integration with the helper module:

```bash
export BW_SESSION="$(bw unlock --raw)"
venv/bin/python bitwarden_helper.py
```

This will show which credentials were successfully retrieved from Bitwarden.

## Security Best Practices

1. **Lock vault when not in use**: Set `BITWARDEN_AUTO_LOCK=true`
2. **Use strong master password**: Bitwarden security depends on it
3. **Enable 2FA**: Enable two-factor authentication in Bitwarden
4. **Limit session duration**: Don't keep `BW_SESSION` exported permanently
5. **Restrict item access**: Use Bitwarden Organizations for team access control
6. **Audit access**: Review Bitwarden event logs regularly (Business plan)
7. **Secure BW_SESSION**: Never commit `BW_SESSION` to git or logs

## Troubleshooting

### "bw: command not found"

Install Bitwarden CLI (see Installation section above).

### "Not logged into Bitwarden"

```bash
bw login
```

### "Vault is locked"

```bash
export BW_SESSION="$(bw unlock --raw)"
```

### "Failed to retrieve from Bitwarden"

Check item name matches exactly:
```bash
bw list items --search "FMC Certificate Manager"
```

### Cert manager still uses .env

Make sure `BW_SESSION` is exported and passed to sudo:
```bash
export BW_SESSION="$(bw unlock --raw)"
sudo -E BW_SESSION="$BW_SESSION" venv/bin/python cert_manager.py
```

### "Permission denied" errors

Ensure you run with `sudo -E` to preserve environment variables:
```bash
sudo -E BW_SESSION="$BW_SESSION" venv/bin/python cert_manager.py
```

## Migration from .env to Bitwarden

1. **Create Bitwarden item** with all credentials from `.env`
2. **Test** with wrapper script: `./run_with_bitwarden.sh`
3. **Verify** credentials are loaded: Check logs for "Loaded X from Bitwarden"
4. **Backup** your `.env` file: `cp .env .env.backup`
5. **Optional**: Remove sensitive data from `.env` (keep non-sensitive config)
6. **Keep** `.env.example` for documentation

You can keep `.env` as fallback - cert_manager will prefer Bitwarden if `BW_SESSION` is set.

## Bitwarden Item Structure

Required structure for "FMC Certificate Manager" item:

```json
{
  "name": "FMC Certificate Manager",
  "type": 1,
  "login": {
    "username": "apiuser",
    "password": "your_fmc_password"
  },
  "fields": [
    {"name": "FMC_HOST", "value": "192.168.0.247"},
    {"name": "DOMAIN_NAME", "value": "vpn.ai-chatbot.dk"},
    {"name": "FTD_DEVICE_NAME", "value": "FTD1010"},
    {"name": "FTD_CERT_NAME", "value": "RA-VPN-cert"},
    {"name": "CLOUDFLARE_TOKEN", "value": "your_token_here"}
  ]
}
```

All custom fields are optional - missing fields will fall back to `.env`.
