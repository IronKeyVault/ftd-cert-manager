# FTD Certificate Manager

Automatisk certifikathåndtering for Cisco FTD 1010 via FMC med Let's Encrypt og wingpy.

**NYT**: Understøtter nu Bitwarden password manager til sikker credential-lagring! Se [BITWARDEN.md](BITWARDEN.md)

## Oversigt

Dette projekt automatiserer processen med at:
1. Anmode om SSL/TLS certifikater fra Let's Encrypt for FTD RA VPN
2. Forny certifikater automatisk
3. Uploade certifikater til Cisco FMC via API (wingpy)
4. Konfigurere certifikater til brug på FTD enheder

**Sikkerhedsfunktioner:**
- 🔐 Bitwarden integration til sikker credential-lagring (valgfrit)
- 📁 Fallback til `.env` filer med restriktive rettigheder
- 🔒 Automatisk credential cleanup efter brug
- 🛡️ Ingen hardcoded passwords i koden

## Forudsætninger

- Python 3.8 eller nyere
- Certbot (til Let's Encrypt)
- Adgang til Cisco FMC med admin rettigheder
- FTD enhed registreret i FMC
- Cloudflare konto (til automatisk DNS validering)
- Systemd (til automatisk fornyelse)
- **(Valgfrit)** Bitwarden CLI til sikker credential-håndtering

## Installation

### 1. Klon eller download projektet

```bash
cd ~/projects
# Projektet burde allerede være her som ftd-cert-manager
cd ftd-cert-manager
```

### 2. Kør setup scriptet

```bash
./setup.sh
```

Dette vil:
- Oprette et Python virtual environment
- Installere alle nødvendige pakker
- Oprette nødvendige mapper
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
cp .env.example .env
nano .env
```

Vigtigt at udfylde:

```bash
# Let's Encrypt konfiguration
LETSENCRYPT_EMAIL=kasper@elsborg.eu
DOMAIN_NAME=vpn.ai-chatbot.dk

# FMC konfiguration
FMC_HOST=192.168.x.x
FMC_USERNAME=admin
FMC_PASSWORD=dit_password_her
FMC_VERIFY_SSL=false

# FTD konfiguration
FTD_DEVICE_NAME=FTD-1010
FTD_CERT_NAME=VPN-Certificate
```

## Brug

### Manuelt køre certifikat fornyelse

```bash
# Aktiver virtual environment
source venv/bin/activate

# Kør cert manager
./cert_manager.py
```

### Test med Let's Encrypt staging environment

For at teste uden at ramme rate limits:

```bash
# Sæt CERTBOT_STAGING=true i .env filen
nano .env
# Ændre: CERTBOT_STAGING=true

# Kør test
./cert_manager.py
```

### Automatisk fornyelse med systemd

Installer systemd service og timer:

```bash
# Kopier systemd filer
sudo cp systemd/ftd-cert-renew.service /etc/systemd/system/
sudo cp systemd/ftd-cert-renew.timer /etc/systemd/system/

# Aktiver og start timer
sudo systemctl daemon-reload
sudo systemctl enable ftd-cert-renew.timer
sudo systemctl start ftd-cert-renew.timer

# Tjek status
sudo systemctl status ftd-cert-renew.timer
sudo systemctl list-timers --all | grep ftd-cert
```

## DNS Challenge

For FTD RA VPN certifikater skal du typisk bruge DNS challenge, da FTD ikke eksponerer en webserver på port 80.

### Cloudflare DNS (anbefalet)

1. Opret `.cloudflare-credentials` fil:

```bash
nano .cloudflare-credentials
```

2. Tilføj dine Cloudflare credentials:

```
dns_cloudflare_api_token = your_cloudflare_api_token_here
```

3. Sæt korrekte rettigheder:

```bash
chmod 600 .cloudflare-credentials
```

4. Opdater `.env`:

```bash
CERTBOT_DNS_PROVIDER=cloudflare
```

### Manuel DNS Challenge

Hvis du ikke bruger Cloudflare:

```bash
CERTBOT_DNS_PROVIDER=manual
```

Dette vil bede dig om at tilføje en TXT record til din DNS manuelt under processen.

## Sikkerhed

- Hold din `.env` fil sikker - den indeholder adgangskoder
- `.env` er allerede i `.gitignore` så den ikke committed til git
- Overvej at bruge et dedikeret FMC bruger konto med begrænsede rettigheder
- Private keys gemmes i `certs/` mappen med begrænsede rettigheder

## Struktur

```
ftd-cert-manager/
├── cert_manager.py          # Hovedscript
├── requirements.txt         # Python dependencies
├── .env.example            # Eksempel konfiguration
├── .env                    # Din konfiguration (git ignored)
├── setup.sh               # Installation script
├── README.md              # Denne fil
├── certs/                 # Certifikater gemmes her
├── logs/                  # Log filer
├── scripts/               # Hjælpescripts
└── systemd/              # Systemd service filer
    ├── ftd-cert-renew.service
    └── ftd-cert-renew.timer
```

## Logs

Logs gemmes i `logs/` mappen med dato i filnavnet:

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

## FMC Deployment

Efter certifikatet er uploaded til FMC, skal du:

1. Log ind på FMC GUI
2. Gå til Devices > Device Management
3. Find din FTD enhed
4. Gå til RA VPN konfigurationen
5. Vælg det nye certifikat
6. Deploy konfigurationen til FTD

Dette kan også automatiseres via FMC API i fremtiden.

## Let's Encrypt Rate Limits

Let's Encrypt har rate limits:
- 50 certifikater per registreret domæne per uge
- 5 fejlede valideringer per konto, per hostname, per time

Brug staging environment til test for at undgå at ramme limits.

## Support

For wingpy dokumentation: https://wingpy.automation.wingmen.dk/

For FMC API dokumentation: Tjek din FMC's indbyggede API Explorer

## Licens

Dette projekt er til intern brug hos Wingmen Solutions / AI-Chatbot.dk

## Forfatter

Kasper Elsborg (kasper@elsborg.eu)
