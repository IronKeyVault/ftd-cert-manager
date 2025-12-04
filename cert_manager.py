#!/usr/bin/env python3
"""
Certificate Manager for FTD via FMC
Manages Let's Encrypt SSL certificate renewal and upload to Cisco FMC/FTD
Supports Bitwarden for secure credential storage
"""

import os
import sys
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from wingpy import CiscoFMC

# Try to import Bitwarden helper (optional)
try:
    from bitwarden_helper import get_credentials_from_bitwarden
    BITWARDEN_AVAILABLE = True
except ImportError:
    BITWARDEN_AVAILABLE = False
    logging.info("Bitwarden helper not available, using .env only")

# Load environment variables from .env (fallback)
load_dotenv()

def load_config():
    """
    Load configuration from Bitwarden (if available) or .env file
    Priority: Environment variables > Bitwarden > .env file
    """
    config = {}
    
    # Try Bitwarden first if BW_SESSION is set
    if BITWARDEN_AVAILABLE and os.getenv('BW_SESSION'):
        try:
            logging.info("Attempting to load credentials from Bitwarden...")
            bw_credentials = get_credentials_from_bitwarden()
            
            # Use Bitwarden values if they exist, otherwise fall back to .env
            for key, value in bw_credentials.items():
                if value:  # Only use non-None values from Bitwarden
                    config[key] = value
                    logging.info(f"Loaded {key} from Bitwarden")
        except Exception as e:
            logging.warning(f"Failed to load from Bitwarden: {e}")
            logging.info("Falling back to .env file")
    else:
        if not os.getenv('BW_SESSION'):
            logging.info("BW_SESSION not set, using .env file")
    
    # Load from environment/dotenv (fallback or override)
    env_vars = {
        'FMC_HOST': os.getenv('FMC_HOST'),
        'FMC_USERNAME': os.getenv('FMC_USERNAME'),
        'FMC_PASSWORD': os.getenv('FMC_PASSWORD'),
        'DOMAIN_NAME': os.getenv('DOMAIN_NAME'),
        'FTD_DEVICE_NAME': os.getenv('FTD_DEVICE_NAME'),
        'FTD_CERT_NAME': os.getenv('FTD_CERT_NAME', 'VPN-Certificate'),
        'CLOUDFLARE_TOKEN': os.getenv('CLOUDFLARE_TOKEN'),
    }
    
    # Merge: env vars override Bitwarden
    for key, value in env_vars.items():
        if value or key not in config:
            config[key] = value
    
    return config

# Load configuration
CONFIG = load_config()

# Configuration
EMAIL = os.getenv('LETSENCRYPT_EMAIL')
DOMAIN = CONFIG.get('DOMAIN_NAME')
CERT_OUTPUT_DIR = Path(os.getenv('CERT_OUTPUT_DIR', './certs'))
LOG_DIR = Path(os.getenv('LOG_DIR', './logs'))
STAGING = os.getenv('CERTBOT_STAGING', 'false').lower() == 'true'
WEBROOT = os.getenv('CERTBOT_WEBROOT')
DNS_PROVIDER = os.getenv('CERTBOT_DNS_PROVIDER', '')

# FMC Configuration
FMC_HOST = CONFIG.get('FMC_HOST')
FMC_USERNAME = CONFIG.get('FMC_USERNAME')
FMC_PASSWORD = CONFIG.get('FMC_PASSWORD')
FMC_VERIFY_SSL = os.getenv('FMC_VERIFY_SSL', 'false').lower() == 'true'

# FTD Configuration
FTD_DEVICE_NAME = CONFIG.get('FTD_DEVICE_NAME')
FTD_CERT_NAME_BASE = CONFIG.get('FTD_CERT_NAME', 'VPN-Certificate')
# Add year-month to certificate name (e.g., RA-VPN-Certificate-2025-12)
FTD_CERT_NAME = f"{FTD_CERT_NAME_BASE}-{datetime.now().strftime('%Y-%m')}"

# Cloudflare token handling
CLOUDFLARE_TOKEN = CONFIG.get('CLOUDFLARE_TOKEN')

# Setup logging
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOG_DIR / f"cert-manager-{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def validate_config():
    """Validate required configuration"""
    if not EMAIL:
        logger.error("LETSENCRYPT_EMAIL is not set in .env file")
        return False
    if not DOMAIN:
        logger.error("DOMAIN_NAME is not set in .env file")
        return False
    if not FMC_HOST:
        logger.error("FMC_HOST is not set in .env file")
        return False
    if not FMC_USERNAME or not FMC_PASSWORD:
        logger.error("FMC_USERNAME and FMC_PASSWORD must be set in .env file")
        return False
    if not FTD_DEVICE_NAME:
        logger.error("FTD_DEVICE_NAME is not set in .env file")
        return False
    return True


def request_certificate():
    """Request or renew certificate from Let's Encrypt"""
    logger.info(f"Requesting certificate for domain: {DOMAIN}")
    
    # Create certificate output directory
    CERT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Handle Cloudflare credentials
    if DNS_PROVIDER == 'cloudflare':
        cloudflare_creds_file = Path('.cloudflare-credentials')
        
        # If Cloudflare token is available (from Bitwarden or env), write it to file
        if CLOUDFLARE_TOKEN:
            logger.info("Writing Cloudflare credentials from configuration")
            try:
                cloudflare_creds_file.write_text(
                    f"# Cloudflare API token\n"
                    f"dns_cloudflare_api_token = {CLOUDFLARE_TOKEN}\n"
                )
                cloudflare_creds_file.chmod(0o600)
                logger.info("Cloudflare credentials file created")
            except Exception as e:
                logger.error(f"Failed to write Cloudflare credentials: {e}")
                return False
        elif not cloudflare_creds_file.exists():
            logger.error("Cloudflare credentials not found in Bitwarden or .env, and .cloudflare-credentials file missing")
            return False
    
    # Check if running as root
    is_root = os.geteuid() == 0
    
    # Build certbot command - use sudo only if not root
    cmd = []
    if not is_root:
        cmd.append('sudo')
    
    cmd.extend([
        'certbot', 'certonly',
        '--non-interactive',
        '--agree-tos',
        '--email', EMAIL,
        '-d', DOMAIN,
    ])
    
    # Add staging flag if testing
    if STAGING:
        cmd.append('--staging')
        logger.info("Using Let's Encrypt staging environment")
    
    # Choose authentication method
    if DNS_PROVIDER:
        if DNS_PROVIDER == 'cloudflare':
            cmd.extend(['--dns-cloudflare', '--dns-cloudflare-credentials', '.cloudflare-credentials'])
            logger.info("Using Cloudflare DNS challenge")
        elif DNS_PROVIDER == 'manual':
            # Manual DNS challenge - user must add TXT records
            cmd.extend(['--manual', '--preferred-challenges', 'dns'])
            logger.info("Using manual DNS challenge - you will need to add TXT records")
            # Remove --non-interactive for manual mode
            cmd = [c for c in cmd if c != '--non-interactive']
        else:
            logger.warning(f"DNS provider {DNS_PROVIDER} may require additional configuration")
            cmd.append(f'--dns-{DNS_PROVIDER}')
    elif WEBROOT:
        cmd.extend(['--webroot', '-w', WEBROOT])
        logger.info(f"Using webroot authentication: {WEBROOT}")
    else:
        # Try standalone mode
        logger.info("Using standalone mode")
        cmd.append('--standalone')
    
    try:
        # For manual DNS mode, run without capturing output so user can interact
        if DNS_PROVIDER == 'manual':
            result = subprocess.run(cmd, check=True)
        else:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.debug(result.stdout)
        logger.info("Certificate obtained successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to obtain certificate: {e}")
        if hasattr(e, 'stderr') and e.stderr:
            logger.error(e.stderr)
        return False


def copy_certificates():
    """Copy certificates from certbot directory to local output directory"""
    logger.info("Copying certificates to local directory")
    
    # System certbot stores certs in /etc/letsencrypt/live/{domain}/
    le_cert_dir = Path(f'/etc/letsencrypt/live/{DOMAIN}')
    
    try:
        # Check if running as root
        is_root = os.geteuid() == 0
        
        # Check if directory exists
        check_cmd = ['test', '-d', str(le_cert_dir)]
        if not is_root:
            check_cmd.insert(0, 'sudo')
        check_result = subprocess.run(check_cmd, capture_output=True)
        if check_result.returncode != 0:
            logger.error(f"Certificate directory not found: {le_cert_dir}")
            return False
        
        files_to_copy = ['fullchain.pem', 'privkey.pem', 'cert.pem', 'chain.pem']
        for file in files_to_copy:
            src = le_cert_dir / file
            dst = CERT_OUTPUT_DIR / file
            # Use sudo to read the files only if not root (they're owned by root)
            cat_cmd = ['cat', str(src)]
            if not is_root:
                cat_cmd.insert(0, 'sudo')
            result = subprocess.run(cat_cmd, check=True, capture_output=True)
            dst.write_bytes(result.stdout)
            logger.info(f"Copied {file}")
        return True
    except Exception as e:
        logger.error(f"Failed to copy certificates: {e}")
        return False


def upload_certificate_to_fmc():
    """Upload certificate to FMC as Internal Certificate"""
    logger.info(f"Uploading certificate to FMC: {FTD_CERT_NAME}")
    
    cert = CERT_OUTPUT_DIR / 'cert.pem'
    privkey = CERT_OUTPUT_DIR / 'privkey.pem'
    
    if not cert.exists() or not privkey.exists():
        logger.error("Certificate files not found")
        return False
    
    try:
        # Initialize FMC client
        fmc = CiscoFMC(
            base_url=f"https://{FMC_HOST}",
            username=FMC_USERNAME,
            password=FMC_PASSWORD,
            verify=FMC_VERIFY_SSL,
            timeout=30
        )
        
        logger.info("Connected to FMC")
        
        # Read certificate and private key
        cert_data = cert.read_text().strip()
        key_data = privkey.read_text().strip()
        
        # Build Internal Certificate object for FMC
        cert_object = {
            "name": FTD_CERT_NAME,
            "type": "InternalCertificate",
            "cert": cert_data,
            "privateKey": key_data,
        }
        
        # Try to find existing certificate with same name
        logger.info(f"Checking for existing certificate: {FTD_CERT_NAME}")
        try:
            certs = fmc.get_all("/api/fmc_config/v1/domain/{domainUUID}/object/internalcertificates")
            existing_cert = None
            for cert_obj in certs:
                if cert_obj.get('name') == FTD_CERT_NAME:
                    existing_cert = cert_obj
                    break
            
            if existing_cert:
                logger.info(f"Found existing certificate with ID: {existing_cert['id']}")
                # Update existing certificate
                cert_object['id'] = existing_cert['id']
                response = fmc.put(
                    f"/api/fmc_config/v1/domain/{{domainUUID}}/object/internalcertificates/{existing_cert['id']}",
                    data=cert_object
                )
                logger.info(f"Certificate updated successfully: {response.status_code}")
            else:
                # Create new certificate
                logger.info("Creating new internal certificate")
                response = fmc.post(
                    "/api/fmc_config/v1/domain/{domainUUID}/object/internalcertificates",
                    data=cert_object
                )
                logger.info(f"Certificate created successfully: {response.status_code}")
                
        except Exception as e:
            logger.warning(f"Error checking existing certificates: {e}")
            # Try to create new certificate
            logger.info("Attempting to create new certificate")
            response = fmc.post(
                "/api/fmc_config/v1/domain/{domainUUID}/object/internalcertificates",
                data=cert_object
            )
            logger.info(f"Certificate created successfully: {response.status_code}")
        
        logger.info("Certificate uploaded to FMC successfully!")
        logger.info(f"Certificate '{FTD_CERT_NAME}' is now available in FMC")
        logger.info("  Location: Objects > PKI > Internal Certificates")
        logger.warning("Remember to assign certificate to RA VPN policy and deploy to FTD device via FMC")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to upload certificate to FMC: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def deploy_to_ftd():
    """Deploy pending changes to FTD device via FMC API"""
    auto_deploy = os.getenv('FMC_AUTO_DEPLOY', 'false').lower() == 'true'
    
    if not auto_deploy:
        logger.info("Auto-deploy is disabled. Set FMC_AUTO_DEPLOY=true in .env to enable")
        return True
    
    logger.info(f"Checking for pending changes to deploy to {FTD_DEVICE_NAME}")
    
    try:
        # Initialize FMC client
        fmc = CiscoFMC(
            base_url=f"https://{FMC_HOST}",
            username=FMC_USERNAME,
            password=FMC_PASSWORD,
            verify=FMC_VERIFY_SSL,
            timeout=30
        )
        
        # Get devices with pending changes
        response = fmc.get('/api/fmc_config/v1/domain/{domainUUID}/deployment/deployabledevices')
        deployable = response.json().get('items', [])
        
        if not deployable:
            logger.info("No pending changes to deploy")
            return True
        
        # Find our device
        target_device = None
        for device in deployable:
            if device.get('name') == FTD_DEVICE_NAME:
                target_device = device
                break
        
        if not target_device:
            logger.info(f"Device {FTD_DEVICE_NAME} has no pending changes")
            return True
        
        logger.info(f"Found pending changes for {FTD_DEVICE_NAME}, deploying...")
        
        # Build deployment request
        deployment_request = {
            "type": "DeploymentRequest",
            "version": target_device.get("version"),
            "forceDeploy": False,
            "ignoreWarning": True,
            "deviceList": [target_device.get("device", {}).get("id")]
        }
        
        # Submit deployment
        deploy_response = fmc.post(
            '/api/fmc_config/v1/domain/{domainUUID}/deployment/deploymentrequests',
            data=deployment_request
        )
        
        logger.info(f"Deployment initiated successfully: {deploy_response.status_code}")
        logger.info(f"Deployment is running. Check FMC GUI for progress: Devices > Device Management")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to deploy to FTD: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def send_notification(success: bool, message: str):
    """Send notification about certificate renewal"""
    notification_email = os.getenv('NOTIFICATION_EMAIL')
    
    if notification_email:
        status = "SUCCESS" if success else "FAILED"
        subject = f"FTD Certificate Renewal {status} - {DOMAIN}"
        
        try:
            # Check if mail command exists
            result = subprocess.run(['which', 'mail'], capture_output=True)
            if result.returncode != 0:
                logger.warning("'mail' command not found. Install mailutils to enable email notifications.")
                return
            
            subprocess.run([
                'mail', '-s', subject, notification_email
            ], input=message.encode(), check=True)
            logger.info(f"Notification sent to {notification_email}")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f"Failed to send email notification: {e}")


def main():
    """Main execution flow"""
    logger.info("=" * 60)
    logger.info("FTD Certificate Manager Started")
    logger.info("=" * 60)
    
    if not validate_config():
        logger.error("Configuration validation failed")
        sys.exit(1)
    
    # Request/renew certificate
    if not request_certificate():
        message = f"Failed to obtain certificate for {DOMAIN}"
        logger.error(message)
        send_notification(False, message)
        sys.exit(1)
    
    # Copy certificates locally
    if not copy_certificates():
        message = f"Failed to copy certificates for {DOMAIN}"
        logger.error(message)
        send_notification(False, message)
        sys.exit(1)
    
    # Upload certificate to FMC
    if not upload_certificate_to_fmc():
        message = f"Failed to upload certificate to FMC for {DOMAIN}"
        logger.error(message)
        send_notification(False, message)
        sys.exit(1)
    
    # Deploy to FTD (optional, only if FMC_AUTO_DEPLOY=true)
    if not deploy_to_ftd():
        message = f"Failed to deploy changes to FTD for {DOMAIN}"
        logger.error(message)
        send_notification(False, message)
        sys.exit(1)
    
    message = f"Certificate successfully renewed and uploaded to FMC for {DOMAIN}"
    logger.info(message)
    send_notification(True, message)
    
    logger.info("=" * 60)
    logger.info("FTD Certificate Manager Completed Successfully")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
