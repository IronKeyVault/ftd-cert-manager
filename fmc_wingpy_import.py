#!/usr/bin/env python3
"""
FMC Certificate Import using wingpy
Automated certificate renewal workflow
"""
import os
import sys
import base64
from dotenv import load_dotenv
from wingpy import CiscoFMC

# Load environment variables
load_dotenv()

# Configuration from .env
FMC_HOST = os.getenv('FMC_HOST', '192.168.0.247')
FMC_USERNAME = os.getenv('FMC_USERNAME', 'apiuser')
FMC_PASSWORD = os.getenv('FMC_PASSWORD')
CERT_NAME = os.getenv('FTD_CERT_NAME', 'RA-VPN-cert')
PKCS12_FILE = os.getenv('PKCS12_FILE', 'vpn-complete.p12')
PKCS12_PASSWORD = os.getenv('PKCS12_PASSWORD', 'cisco123')

def main():
    print("=== FMC Certificate Import (wingpy) ===")
    print(f"FMC: https://{FMC_HOST}")
    print(f"Certificate: {CERT_NAME}")
    print(f"PKCS12: {PKCS12_FILE}")
    print()
    
    if not os.path.exists(PKCS12_FILE):
        print(f"✗ PKCS12 file not found: {PKCS12_FILE}")
        return 1
    
    if not FMC_PASSWORD:
        print("✗ FMC_PASSWORD environment variable not set")
        return 1
    
    # Connect to FMC
    print("[1/3] Connecting to FMC...")
    fmc = CiscoFMC(
        base_url=f"https://{FMC_HOST}",
        username=FMC_USERNAME,
        password=FMC_PASSWORD,
        verify=False
    )
    print("✓ Connected")
    
    # Get domain UUID from FMC info
    info_response = fmc.get("/api/fmc_platform/v1/info/domain")
    info = info_response.json() if hasattr(info_response, 'json') else info_response
    domain_uuid = info['items'][0]['uuid']
    print(f"  Domain UUID: {domain_uuid}")
    
    # Find certificate enrollment
    print(f"[2/3] Finding certificate: {CERT_NAME}...")
    
    enrollments = fmc.get_all(f"/api/fmc_config/v1/domain/{domain_uuid}/object/certenrollments")
    
    enrollment = None
    for item in enrollments:
        if item['name'] == CERT_NAME:
            enrollment = item
            print(f"✓ Found {CERT_NAME}")
            print(f"  ID: {item['id']}")
            print(f"  Type: {item.get('enrollmentType', 'unknown')}")
            break
    
    if not enrollment:
        print(f"✗ Certificate {CERT_NAME} not found")
        print(f"  Available enrollments: {[e['name'] for e in enrollments]}")
        return 1
    
    # Import certificate using correct FMC API structure
    print(f"[3/3] Importing certificate to enrollment...")
    
    # Read PKCS12 file
    with open(PKCS12_FILE, 'rb') as f:
        pkcs12_data = f.read()
    
    # Base64 encode with standard line breaks (76 chars + \r\n)
    # This matches PEM format that FMC expects
    pkcs12_b64_raw = base64.b64encode(pkcs12_data).decode('ascii')
    
    # Add \r\n every 76 characters (standard base64 line length)
    pkcs12_b64_lines = []
    for i in range(0, len(pkcs12_b64_raw), 76):
        pkcs12_b64_lines.append(pkcs12_b64_raw[i:i+76])
    pkcs12_b64 = '\r\n'.join(pkcs12_b64_lines) + '\r\n'
    
    enrollment_id = enrollment['id']
    
    # Build payload preserving all existing enrollment fields
    payload = {
        'id': enrollment_id,
        'name': enrollment['name'],
        'type': enrollment['type'],
        'enrollmentType': enrollment['enrollmentType'],
        'pkcs12Content': {
            'passPhrase': PKCS12_PASSWORD,
            'base64Certificate': pkcs12_b64
        }
    }
    
    # Preserve existing fields if present
    for field in ['revocation', 'skipCaFlagCheck', 'validationUsage', 'overridable']:
        if field in enrollment:
            payload[field] = enrollment[field]
    
    try:
        result = fmc.put(
            f"/api/fmc_config/v1/domain/{domain_uuid}/object/certenrollments/{enrollment_id}",
            data=payload
        )
        
        if result:
            print("✓ Certificate imported to enrollment!")
            print()
            print("=== Step 1/2 Complete ===")
            print("Certificate enrollment updated successfully")
            print()
            print("STEP 2/2 - Manual GUI step required:")
            print("  FMC REST API has no endpoint for 'Devices > Certificates > Add'")
            print()
            print("  1. Open FMC GUI: https://192.168.0.247")
            print("  2. Navigate: Devices > Certificates")
            print("  3. Click: Add")
            print("  4. Device: FTD1010")
            print(f"  5. Cert Enrollment: {CERT_NAME}")
            print("  6. Click: Add")
            print()
            print("  This links the enrollment (with new certificate) to the device.")
            print("  FMC will then auto-deploy to FTD1010.")
            print()
            return 0
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return 1
    
    return 1

if __name__ == "__main__":
    sys.exit(main())
