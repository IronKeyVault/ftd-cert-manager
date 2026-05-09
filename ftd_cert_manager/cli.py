#!/usr/bin/env python3
"""ftd-cert-manager CLI: configure credentials and import PKCS12 to FMC."""
import argparse
import getpass
import logging
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional

from wingpy import CiscoFMC

from ftd_cert_manager.config import CredentialManager, ConfigManager
from ftd_cert_manager.fmc_import import import_pkcs12

log = logging.getLogger("ftd-cert-manager")

DEFAULTS = {
    "fmc_base_url": "https://192.168.0.247",
    "fmc_username": "apiuser",
    "ftd_cert_name": "RA-VPN-cert",
    "domain_name": "vpn.ai-chatbot.dk",
    "letsencrypt_email": "kasper@elsborg.eu",
    "pkcs12_password": "cisco123",
}


def _masked_input(prompt: str) -> str:
    """Read input echoing '*' per character. Falls back to getpass on non-TTY."""
    if not sys.stdin.isatty():
        return getpass.getpass(prompt)
    try:
        import termios
        import tty
        sys.stdout.write(prompt)
        sys.stdout.flush()
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        chars = []
        try:
            tty.setraw(fd)
            while True:
                c = sys.stdin.read(1)
                if c in ("\r", "\n"):
                    sys.stdout.write("\r\n")
                    break
                if c in ("\x7f", "\x08"):
                    if chars:
                        chars.pop()
                        sys.stdout.write("\b \b")
                elif c == "\x03":
                    sys.stdout.write("\r\n")
                    raise KeyboardInterrupt
                elif c == "\x1b":
                    nxt = sys.stdin.read(1)
                    if nxt == "[":
                        while True:
                            seq = sys.stdin.read(1)
                            if seq.isalpha() or seq == "~":
                                break
                elif ord(c) >= 32:
                    chars.append(c)
                    sys.stdout.write("*")
                sys.stdout.flush()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return "".join(chars)
    except Exception:
        return getpass.getpass(prompt)


def _prompt(label: str, default: Optional[str] = None, *, secret: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        if secret:
            value = _masked_input(f"{label}{suffix}: ")
        else:
            value = input(f"{label}{suffix}: ").strip()
        value = value or (default or "")
        if value:
            return value
        print(f"  {label} cannot be empty.")


def _normalize_fmc_url(value: str) -> str:
    value = value.strip()
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value.rstrip("/")


def _list_ftd_devices(fmc: CiscoFMC, domain_uuid: str) -> list:
    """Return list of {name, id, mgmt_ip} for all device records.

    The list endpoint returns minimal fields without expanded=true; mgmt IP
    (hostName) only shows up in the expanded form.
    """
    devices = fmc.get_all(
        f"/api/fmc_config/v1/domain/{domain_uuid}/devices/devicerecords",
        expanded=True,
    )
    result = []
    for d in devices:
        result.append({
            "name": d.get("name", "?"),
            "id": d.get("id", ""),
            "mgmt_ip": d.get("hostName") or d.get("managementIp") or "",
            "model": d.get("model", ""),
        })
    return result


def _pick_ftd_device(devices: list, previous_name: Optional[str]) -> dict:
    if not devices:
        raise RuntimeError("No FTD devices found in FMC. Register one first.")

    print("\nAvailable FTD devices in FMC:")
    default_idx = 0
    for i, d in enumerate(devices, 1):
        marker = ""
        if previous_name and d["name"] == previous_name:
            marker = " (current)"
            default_idx = i
        print(f"  {i}. {d['name']}  [{d['mgmt_ip']}]  {d['model']}{marker}")

    default_str = str(default_idx) if default_idx else "1"
    while True:
        raw = input(f"\nSelect device [1-{len(devices)}, default={default_str}]: ").strip()
        if not raw:
            raw = default_str
        try:
            idx = int(raw)
            if 1 <= idx <= len(devices):
                return devices[idx - 1]
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(devices)}.")


def cmd_setup(_args) -> int:
    print("\n" + "=" * 60)
    print("ftd-cert-manager - Configuration")
    print("=" * 60)
    print("Configure FMC credentials and select the FTD device.\n")

    existing_config = ConfigManager.all()
    existing_creds = CredentialManager.get_credentials() or {}

    fmc_base_url = _normalize_fmc_url(_prompt(
        "FMC URL or IP",
        existing_config.get("fmc_base_url") or DEFAULTS["fmc_base_url"],
    ))
    fmc_username = _prompt(
        "FMC username",
        existing_creds.get("fmc_username") or DEFAULTS["fmc_username"],
    )

    has_stored_pw = bool(existing_creds.get("fmc_password"))
    pw_label = "FMC password (Enter = keep stored)" if has_stored_pw else "FMC password"
    fmc_password = _masked_input(f"{pw_label}: ")
    if not fmc_password:
        if has_stored_pw:
            fmc_password = existing_creds["fmc_password"]
        else:
            print("FMC password cannot be empty.")
            return 1

    print("\nConnecting to FMC to list available FTD devices...")
    try:
        fmc = CiscoFMC(
            base_url=fmc_base_url,
            username=fmc_username,
            password=fmc_password,
            verify=False,
        )
        info = fmc.get("/api/fmc_platform/v1/info/domain")
        info = info.json() if hasattr(info, "json") else info
        domain_uuid = info["items"][0]["uuid"]
        devices = _list_ftd_devices(fmc, domain_uuid)
    except Exception as e:
        print(f"Error: Could not connect to FMC: {e}")
        return 1

    try:
        chosen = _pick_ftd_device(devices, existing_config.get("ftd_name"))
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1
    print(f"  Selected: {chosen['name']} ({chosen['mgmt_ip']})")

    ftd_cert_name = _prompt(
        "Certificate enrollment name (in FMC)",
        existing_config.get("ftd_cert_name") or DEFAULTS["ftd_cert_name"],
    )
    domain_name = _prompt(
        "VPN domain name",
        existing_config.get("domain_name") or DEFAULTS["domain_name"],
    )
    letsencrypt_email = _prompt(
        "Let's Encrypt email",
        existing_config.get("letsencrypt_email") or DEFAULTS["letsencrypt_email"],
    )
    pkcs12_password = _prompt(
        "PKCS12 bundle password",
        existing_creds.get("pkcs12_password") or DEFAULTS["pkcs12_password"],
    )

    existing_cf = CredentialManager.get_cloudflare_token()
    cf_label = "Cloudflare API token (Enter = keep stored)" if existing_cf else \
               "Cloudflare API token (Enter to skip and use .cloudflare-credentials file)"
    cf_token = _masked_input(f"{cf_label}: ").strip()
    if not cf_token and existing_cf:
        cf_token = existing_cf

    print("\n" + "-" * 60)
    print("Summary:")
    print(f"  FMC URL:           {fmc_base_url}")
    print(f"  FMC username:      {fmc_username}")
    print(f"  FTD device:        {chosen['name']} ({chosen['mgmt_ip']})")
    print(f"  Cert enrollment:   {ftd_cert_name}")
    print(f"  Domain:            {domain_name}")
    print(f"  LE email:          {letsencrypt_email}")
    print(f"  Cloudflare token:  {'<set>' if cf_token else '<not set, will use .cloudflare-credentials file>'}")
    print(f"  Storage backend:   {CredentialManager.get_storage_backend()}")
    print("-" * 60)
    confirm = input("\nSave configuration? [Y/n]: ").strip().lower()
    if confirm in ("n", "no"):
        print("Aborted. No changes saved.")
        return 1

    CredentialManager.set_credentials(fmc_username, fmc_password, pkcs12_password)
    if cf_token:
        CredentialManager.set_cloudflare_token(cf_token)
    ConfigManager.update({
        "fmc_base_url": fmc_base_url,
        "ftd_name": chosen["name"],
        "ftd_ip": chosen["mgmt_ip"],
        "ftd_id": chosen["id"],
        "ftd_cert_name": ftd_cert_name,
        "domain_name": domain_name,
        "letsencrypt_email": letsencrypt_email,
    })
    print("\nConfiguration saved.")
    return 0


def cmd_config(_args) -> int:
    from ftd_cert_manager.config import CONFIG_FILE

    config = ConfigManager.all()
    creds = CredentialManager.get_credentials()

    print("=== ftd-cert-manager Configuration ===")
    print(f"Storage backend: {CredentialManager.get_storage_backend()}")
    print(f"Config file:     {CONFIG_FILE}")
    print()

    if not config and not creds:
        print("No configuration found. Run: ftd-cert-manager --setup")
        return 0

    print(f"  FMC URL:           {config.get('fmc_base_url', '<not set>')}")
    print(f"  FMC username:      {creds.get('fmc_username', '<not set>') if creds else '<not set>'}")
    print(f"  FMC password:      {'<set>' if creds and creds.get('fmc_password') else '<not set>'}")
    print(f"  FTD device:        {config.get('ftd_name', '<not set>')} ({config.get('ftd_ip', '?')})")
    print(f"  FTD device id:     {config.get('ftd_id', '<not set>')}")
    print(f"  Cert enrollment:   {config.get('ftd_cert_name', '<not set>')}")
    print(f"  Domain:            {config.get('domain_name', '<not set>')}")
    print(f"  LE email:          {config.get('letsencrypt_email', '<not set>')}")
    print(f"  PKCS12 password:   {'<set>' if creds and creds.get('pkcs12_password') else '<not set>'}")
    print(f"  Cloudflare token:  {'<set>' if CredentialManager.get_cloudflare_token() else '<not set>'}")
    return 0


def cmd_write_cf_creds(args) -> int:
    if CredentialManager.write_cloudflare_creds_file(args.write_cf_creds):
        return 0
    print("Error: no Cloudflare token in keyring. Run --setup to add it.",
          file=sys.stderr)
    return 1


def cmd_clear(_args) -> int:
    confirm = input("Remove all stored credentials and config? [y/N]: ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Aborted.")
        return 1
    CredentialManager.clear_credentials()
    ConfigManager.clear()
    print("Credentials and config removed.")
    return 0


def cmd_export_env(_args) -> int:
    """Print KEY=value lines for bash to eval. Secrets are quoted."""
    config = ConfigManager.all()
    creds = CredentialManager.get_credentials() or {}

    fmc_host = config.get("fmc_base_url", "")
    if fmc_host.startswith("https://"):
        fmc_host = fmc_host[len("https://"):]
    elif fmc_host.startswith("http://"):
        fmc_host = fmc_host[len("http://"):]

    pairs = {
        "FMC_BASE_URL": config.get("fmc_base_url", ""),
        "FMC_HOST": fmc_host,
        "FMC_USERNAME": creds.get("fmc_username", ""),
        "FMC_PASSWORD": creds.get("fmc_password", ""),
        "FTD_NAME": config.get("ftd_name", ""),
        "FTD_IP": config.get("ftd_ip", ""),
        "FTD_CERT_NAME": config.get("ftd_cert_name", ""),
        "DOMAIN_NAME": config.get("domain_name", ""),
        "LETSENCRYPT_EMAIL": config.get("letsencrypt_email", ""),
        "PKCS12_PASSWORD": creds.get("pkcs12_password", ""),
    }
    for key, value in pairs.items():
        print(f"{key}={shlex.quote(value)}")
    return 0


def cmd_import(args) -> int:
    if args.renew:
        script = Path(__file__).resolve().parent.parent / "renew_cert.sh"
        if not script.exists():
            print(f"Error: renew script not found at {script}")
            return 1
        print(f"=== Renewing certificate via {script.name} ===\n")
        rc = subprocess.run([str(script)], cwd=str(script.parent)).returncode
        if rc != 0:
            print(f"\nError: renew_cert.sh exited with code {rc}")
            return rc
        print()
    return import_pkcs12(pkcs12_file=args.pkcs12_file)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="ftd-cert-manager",
        description="Automated Let's Encrypt certificate management for Cisco FTD RA VPN",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--setup", action="store_true",
                       help="Interactive configuration wizard")
    group.add_argument("--import", dest="do_import", action="store_true",
                       help="Upload PKCS12 to FMC enrollment (Step 1/2)")
    group.add_argument("--config", action="store_true",
                       help="Show current configuration")
    group.add_argument("--clear", action="store_true",
                       help="Remove all credentials and configuration")
    group.add_argument("--export-env", action="store_true",
                       help="Print KEY=value lines for bash eval")
    group.add_argument("--write-cf-creds", metavar="PATH",
                       help="Materialize the Cloudflare token to PATH (chmod 600); "
                            "used internally by renew_cert.sh")

    parser.add_argument("--pkcs12-file", default="vpn-complete.p12",
                        help="Path to PKCS12 bundle (default: vpn-complete.p12)")
    parser.add_argument("--renew", action="store_true",
                        help="With --import: run renew_cert.sh first to fetch a fresh "
                             "Let's Encrypt cert before importing")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.setup:
        return cmd_setup(args)
    if args.do_import:
        return cmd_import(args)
    if args.config:
        return cmd_config(args)
    if args.clear:
        return cmd_clear(args)
    if args.export_env:
        return cmd_export_env(args)
    if args.write_cf_creds:
        return cmd_write_cf_creds(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
