# Manuel Upload af Certifikat til FMC

Da FMC API ikke direkte understøtter import af eksterne certifikater via certenrollments,
skal certifikatet uploades manuelt via FMC GUI.

## Fremgangsmåde:

1. **Log ind på FMC** (https://192.168.0.247)

2. **Naviger til:** Objects > PKI > Cert Enrollment

3. **Klik "Add Cert Enrollment"**

4. **Vælg "Import"** (ikke SCEP eller Manual)

5. **Udfyld:**
   - Name: `VPN-Certificate`
   - Certificate: Upload `certs/cert.pem`
   - Private Key: Upload `certs/privkey.pem`
   - Password: (tomt hvis key ikke er encrypted)

6. **Gem certifikatet**

7. **Gå til RA VPN konfiguration** for at bruge certifikatet

## Certifikat filer findes i:
- `/home/kasperadm/projects/ftd-cert-manager/certs/`

## Automatisk fornyelse:
Scriptet vil automatisk forny certifikatet hver 60 dage.
Du skal dog manuelt uploade det nye certifikat til FMC når det er fornyet.

## Fremtidig automation:
Vi kan muligvis automatisere dette via:
- FMC file upload API (hvis tilgængelig)
- SCP til FMC og import via CLI
- Eller notifikation når nyt certifikat er klar
