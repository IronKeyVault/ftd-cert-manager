#!/usr/bin/env python3
"""
Bitwarden Helper Module
Retrieves credentials from Bitwarden vault via REST API
"""

import os
import json
import subprocess
import sys
from typing import Optional, Dict

class BitwardenClient:
    """Simple Bitwarden client using CLI"""
    
    def __init__(self, session_key: Optional[str] = None):
        """
        Initialize Bitwarden client
        
        Args:
            session_key: BW_SESSION environment variable (optional)
        """
        self.session_key = session_key or os.getenv('BW_SESSION')
        self._check_cli()
    
    def _check_cli(self):
        """Check if bw CLI is installed"""
        try:
            result = subprocess.run(['which', 'bw'], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=5)
            if result.returncode != 0:
                raise FileNotFoundError(
                    "Bitwarden CLI not found. Install with: npm install -g @bitwarden/cli"
                )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"Warning: Bitwarden CLI check failed: {e}", file=sys.stderr)
    
    def unlock(self, password: str) -> str:
        """
        Unlock Bitwarden vault and get session key
        
        Args:
            password: Master password
            
        Returns:
            Session key (BW_SESSION value)
        """
        try:
            result = subprocess.run(
                ['bw', 'unlock', password, '--raw'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                raise Exception(f"Failed to unlock: {result.stderr}")
            
            session_key = result.stdout.strip()
            self.session_key = session_key
            return session_key
            
        except subprocess.TimeoutExpired:
            raise Exception("Bitwarden unlock timeout")
        except Exception as e:
            raise Exception(f"Unlock error: {e}")
    
    def get_item(self, item_name: str) -> Optional[Dict]:
        """
        Get item from Bitwarden vault by name
        
        Args:
            item_name: Name of the vault item
            
        Returns:
            Item data as dictionary or None if not found
        """
        if not self.session_key:
            raise Exception("Not authenticated. Set BW_SESSION or call unlock()")
        
        try:
            env = os.environ.copy()
            env['BW_SESSION'] = self.session_key
            
            result = subprocess.run(
                ['bw', 'get', 'item', item_name],
                capture_output=True,
                text=True,
                env=env,
                timeout=30
            )
            
            if result.returncode != 0:
                print(f"Warning: Item '{item_name}' not found in Bitwarden", 
                      file=sys.stderr)
                return None
            
            return json.loads(result.stdout)
            
        except subprocess.TimeoutExpired:
            print(f"Warning: Bitwarden get item timeout for '{item_name}'", 
                  file=sys.stderr)
            return None
        except json.JSONDecodeError:
            print(f"Warning: Invalid JSON from Bitwarden for '{item_name}'", 
                  file=sys.stderr)
            return None
        except Exception as e:
            print(f"Warning: Bitwarden error for '{item_name}': {e}", 
                  file=sys.stderr)
            return None
    
    def get_password(self, item_name: str) -> Optional[str]:
        """
        Get password field from a Bitwarden item
        
        Args:
            item_name: Name of the vault item
            
        Returns:
            Password string or None if not found
        """
        item = self.get_item(item_name)
        if item and 'login' in item and 'password' in item['login']:
            return item['login']['password']
        return None
    
    def get_field(self, item_name: str, field_name: str) -> Optional[str]:
        """
        Get custom field value from a Bitwarden item
        
        Args:
            item_name: Name of the vault item
            field_name: Name of the custom field
            
        Returns:
            Field value or None if not found
        """
        item = self.get_item(item_name)
        if not item or 'fields' not in item:
            return None
        
        for field in item['fields']:
            if field.get('name') == field_name:
                return field.get('value')
        
        return None
    
    def lock(self):
        """Lock the Bitwarden vault"""
        try:
            subprocess.run(['bw', 'lock'], timeout=10)
        except Exception as e:
            print(f"Warning: Failed to lock Bitwarden: {e}", file=sys.stderr)


def get_credentials_from_bitwarden(
    item_name: str = "FMC Certificate Manager",
    session_key: Optional[str] = None
) -> Dict[str, Optional[str]]:
    """
    Retrieve FMC credentials from Bitwarden
    
    Expected Bitwarden item structure:
    - Item Name: "FMC Certificate Manager"
    - Username: FMC username
    - Password: FMC password
    - Custom Fields:
      - FMC_HOST: FMC hostname/IP
      - DOMAIN_NAME: Certificate domain
      - FTD_DEVICE_NAME: FTD device name
      - FTD_CERT_NAME: Certificate base name
      - CLOUDFLARE_TOKEN: Cloudflare API token
    
    Args:
        item_name: Name of the Bitwarden vault item
        session_key: BW_SESSION value (optional, can use env var)
    
    Returns:
        Dictionary with credentials (values are None if not found)
    """
    credentials = {
        'FMC_HOST': None,
        'FMC_USERNAME': None,
        'FMC_PASSWORD': None,
        'DOMAIN_NAME': None,
        'FTD_DEVICE_NAME': None,
        'FTD_CERT_NAME': None,
        'CLOUDFLARE_TOKEN': None,
    }
    
    try:
        client = BitwardenClient(session_key)
        item = client.get_item(item_name)
        
        if not item:
            print(f"Warning: Bitwarden item '{item_name}' not found", 
                  file=sys.stderr)
            return credentials
        
        # Get username and password from login
        if 'login' in item:
            credentials['FMC_USERNAME'] = item['login'].get('username')
            credentials['FMC_PASSWORD'] = item['login'].get('password')
        
        # Get custom fields
        if 'fields' in item:
            for field in item['fields']:
                field_name = field.get('name')
                if field_name in credentials:
                    credentials[field_name] = field.get('value')
        
        # Special handling for Cloudflare token
        cloudflare_token = client.get_field(item_name, 'CLOUDFLARE_TOKEN')
        if cloudflare_token:
            credentials['CLOUDFLARE_TOKEN'] = cloudflare_token
        
        return credentials
        
    except Exception as e:
        print(f"Warning: Failed to retrieve from Bitwarden: {e}", 
              file=sys.stderr)
        return credentials


if __name__ == "__main__":
    """Test Bitwarden integration"""
    import getpass
    
    print("Bitwarden Helper Test")
    print("=" * 50)
    
    # Check if BW_SESSION is already set
    session_key = os.getenv('BW_SESSION')
    
    if not session_key:
        print("\nBW_SESSION not found in environment")
        password = getpass.getpass("Enter Bitwarden master password: ")
        
        client = BitwardenClient()
        try:
            session_key = client.unlock(password)
            print(f"\n✓ Unlocked successfully")
            print(f"Export this: export BW_SESSION='{session_key}'")
        except Exception as e:
            print(f"✗ Failed to unlock: {e}")
            sys.exit(1)
    else:
        print("✓ Using existing BW_SESSION from environment")
    
    # Test credential retrieval
    print("\nRetrieving credentials from 'FMC Certificate Manager'...")
    credentials = get_credentials_from_bitwarden(session_key=session_key)
    
    print("\nRetrieved credentials:")
    for key, value in credentials.items():
        if value:
            # Mask sensitive values
            if 'PASSWORD' in key or 'TOKEN' in key:
                display_value = value[:4] + '*' * (len(value) - 4) if len(value) > 4 else '****'
            else:
                display_value = value
            print(f"  {key}: {display_value}")
        else:
            print(f"  {key}: (not found)")
