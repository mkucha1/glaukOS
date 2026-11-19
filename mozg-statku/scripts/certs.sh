#!/usr/bin/env bash
# Certyfikat HTTPS dla serwera w sieci lokalnej statku.
#   ./scripts/certs.sh 192.168.8.100
# Używa mkcert, jeśli jest; inaczej tworzy własne mini-CA przez openssl.
# Telefon: otwórz http://<IP>/ca.crt, zainstaluj certyfikat CA i zaufaj mu
#   Android: Ustawienia > Bezpieczeństwo > Szyfrowanie > Zainstaluj certyfikat > Certyfikat CA
#   iOS:     zainstaluj profil, potem Ustawienia > Ogólne > To urządzenie > Ustawienia zaufania certyfikatów
# Bez zaufanego CA strona zadziała po kliknięciu „Przejdź mimo to”, ale service worker (offline PWA) — NIE.
set -euo pipefail
IP="${1:?podaj IP serwera, np. ./scripts/certs.sh 192.168.8.100}"
cd "$(dirname "$0")/.."
mkdir -p certs certs-private
chmod 700 certs-private

if command -v mkcert >/dev/null 2>&1; then
  echo "[certs] mkcert -> certs/ dla $IP"
  mkcert -install >/dev/null 2>&1 || true
  mkcert -cert-file certs/server.pem -key-file certs/server-key.pem "$IP" localhost 127.0.0.1 ::1
  cp "$(mkcert -CAROOT)/rootCA.pem" certs/rootCA.pem
else
  echo "[certs] brak mkcert — tworzę lokalne CA przez openssl"
  if [ ! -f certs-private/rootCA-key.pem ]; then
    openssl req -x509 -new -nodes -newkey rsa:2048 -sha256 -days 825 \
      -keyout certs-private/rootCA-key.pem -out certs/rootCA.pem \
      -subj "/O=Mozg Statku/CN=Mozg Statku Demo CA" \
      -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
  fi
  openssl req -new -nodes -newkey rsa:2048 -sha256 \
    -keyout certs/server-key.pem -out certs-private/server.csr -subj "/O=Mozg Statku/CN=$IP" 2>/dev/null
  cat > certs-private/server.ext <<EOF
basicConstraints=CA:FALSE
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=IP:$IP,IP:127.0.0.1,DNS:localhost
EOF
  openssl x509 -req -in certs-private/server.csr -CA certs/rootCA.pem -CAkey certs-private/rootCA-key.pem \
    -CAcreateserial -out certs/server.pem -days 397 -sha256 -extfile certs-private/server.ext 2>/dev/null
fi
chmod 644 certs/server.pem certs/server-key.pem certs/rootCA.pem
echo "[certs] gotowe: certs/server.pem (SAN: $IP, localhost). CA dla telefonów: http://$IP/ca.crt"
