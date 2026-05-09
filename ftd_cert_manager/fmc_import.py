#!/usr/bin/env python3
"""FMC PKCS12 enrollment update via wingpy.

Step 1/2 of the cert renewal workflow: pushes the PKCS12 bundle into the
existing certificate enrollment object via PUT /object/certenrollments/{id}.

Step 2/2 (linking the enrollment to the FTD device) has no REST endpoint
and must be done in the FMC GUI.
"""
import base64
import logging
from datetime import datetime
from pathlib import Path

from wingpy import CiscoFMC

from ftd_cert_manager.config import CredentialManager, ConfigManager

log = logging.getLogger("ftd-cert-manager")


def _connect_fmc(fmc_base_url: str, username: str, password: str) -> CiscoFMC:
    return CiscoFMC(
        base_url=fmc_base_url,
        username=username,
        password=password,
        verify=False,
    )


def _get_domain_uuid(fmc: CiscoFMC) -> str:
    info_response = fmc.get("/api/fmc_platform/v1/info/domain")
    info = info_response.json() if hasattr(info_response, "json") else info_response
    return info["items"][0]["uuid"]


def _list_enrollment_names(fmc: CiscoFMC, domain_uuid: str) -> set:
    enrollments = fmc.get_all(
        f"/api/fmc_config/v1/domain/{domain_uuid}/object/certenrollments"
    )
    return {e["name"] for e in enrollments}


def _versioned_name(base: str, existing: set) -> str:
    """Return base-YYYY-MM, with -N suffix on collision."""
    stamp = datetime.now().strftime("%Y-%m")
    candidate = f"{base}-{stamp}"
    if candidate not in existing:
        return candidate
    i = 2
    while f"{candidate}-{i}" in existing:
        i += 1
    return f"{candidate}-{i}"


def _encode_pkcs12(pkcs12_path: Path) -> str:
    """Base64-encode PKCS12 with 76-char line breaks (PEM-style) as FMC expects."""
    raw = pkcs12_path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    lines = [b64[i:i + 76] for i in range(0, len(b64), 76)]
    return "\r\n".join(lines) + "\r\n"


def import_pkcs12(pkcs12_file: str = "vpn-complete.p12") -> int:
    """Upload PKCS12 to the configured FMC enrollment. Returns 0 on success."""
    creds = CredentialManager.get_credentials()
    if not creds:
        print("Error: No stored credentials found. Run: ftd-cert-manager --setup")
        return 1

    fmc_base_url = ConfigManager.get("fmc_base_url")
    cert_base_name = ConfigManager.get("ftd_cert_name")
    ftd_name = ConfigManager.get("ftd_name", "<FTD device>")
    if not fmc_base_url or not cert_base_name:
        print("Error: Configuration incomplete. Run: ftd-cert-manager --setup")
        return 1

    pkcs12_path = Path(pkcs12_file)
    if not pkcs12_path.exists():
        print(f"Error: PKCS12 file not found: {pkcs12_path}")
        return 1

    print("=== FMC Certificate Import ===")
    print(f"FMC: {fmc_base_url}")
    print(f"Base enrollment name: {cert_base_name}")
    print(f"PKCS12: {pkcs12_path}")
    print()

    print("[1/3] Connecting to FMC...")
    fmc = _connect_fmc(fmc_base_url, creds["fmc_username"], creds["fmc_password"])
    domain_uuid = _get_domain_uuid(fmc)
    print(f"  Domain UUID: {domain_uuid}")

    print("[2/3] Generating unique enrollment name...")
    existing = _list_enrollment_names(fmc, domain_uuid)
    cert_name = _versioned_name(cert_base_name, existing)
    print(f"  Will create: {cert_name}")

    print("[3/3] Creating enrollment with PKCS12...")
    endpoint = f"/api/fmc_config/v1/domain/{domain_uuid}/object/certenrollments"
    payload = {
        "name": cert_name,
        "type": "CertEnrollment",
        "enrollmentType": "PKCS12",
        "pkcs12Content": {
            "passPhrase": creds["pkcs12_password"],
            "base64Certificate": _encode_pkcs12(pkcs12_path),
        },
    }
    try:
        result = fmc.post(endpoint, data=payload)
    except Exception as e:
        print(f"Error: PKCS12 create failed: {e}")
        return 1

    if not result:
        print("Error: FMC rejected the PKCS12 upload (HTTP 4xx/5xx).")
        print("       Check FMC logs and verify the certificate is valid.")
        return 1
    if hasattr(result, "status_code") and result.status_code >= 400:
        body = ""
        try:
            body = result.text if hasattr(result, "text") else ""
        except Exception:
            pass
        print(f"Error: FMC returned HTTP {result.status_code}")
        if body:
            print(f"       Response: {body[:500]}")
        return 1

    print()
    print("=== Step 1/2 Complete ===")
    print(f"Certificate enrollment '{cert_name}' created successfully.")
    print()
    print("STEP 2/2 - Manual GUI step required:")
    print(f"  1. Open FMC GUI: {fmc_base_url}")
    print("  2. Navigate: Devices > Certificates")
    print("  3. Click: Add")
    print(f"  4. Device: {ftd_name}")
    print(f"  5. Cert Enrollment: {cert_name}")
    print("  6. Click: Add")
    print()
    print(f"  FMC will then auto-deploy to {ftd_name}.")
    print()
    print("(Old enrollments stay in FMC for rollback. Clean up via GUI when stable.)")
    return 0
