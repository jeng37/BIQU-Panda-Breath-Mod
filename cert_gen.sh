#!/bin/bash

# BIQU-Panda-Breath-Mod: SSL Certificate Generator
# Dieses Skript erstellt die benötigten Zertifikate für die MQTT-Simulation.

# Farben für die Ausgabe
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}--- BIQU-Panda-Breath-Mod: SSL Generator ---${NC}"

# Prüfen ob openssl installiert ist
if ! command -v openssl &> /dev/null
then
    echo -e "${RED}Fehler: openssl konnte nicht gefunden werden.${NC}"
    echo "Bitte installiere es mit: sudo apt install openssl"
    exit
fi

# Dateinamen definieren
KEY_FILE="key.pem"
CERT_FILE="cert.pem"

# Alte Zertifikate sichern oder löschen
if [ -f "$KEY_FILE" ] || [ -f "$CERT_FILE" ]; then
    echo -e "Alte Zertifikate gefunden. Werden überschrieben..."
    rm $KEY_FILE $CERT_FILE
fi

# Zertifikat generieren
echo "Generiere 4096-bit RSA Schlüssel und Zertifikat (Gültigkeit: 10 Jahre)..."

openssl req -x509 -newkey rsa:4096 -keyout $KEY_FILE -out $CERT_FILE -sha256 -days 3650 -nodes \
  -subj "/C=DE/ST=Panda/L=Panda/O=Bambu/OU=Printer/CN=bambulab.local"

# Berechtigungen setzen (Sicherheit: Nur der Besitzer darf den Key lesen)
chmod 600 $KEY_FILE
chmod 644 $CERT_FILE

echo -e "${GREEN}---------------------------------------------${NC}"
echo -e "${GREEN}ERFOLG!${NC}"
echo -e "Dateien erstellt: ${GREEN}$KEY_FILE${NC} und ${GREEN}$CERT_FILE${NC}"
echo "Stelle sicher, dass diese Dateien im selben Ordner wie Panda.py liegen."
echo -e "${GREEN}---------------------------------------------${NC}"
