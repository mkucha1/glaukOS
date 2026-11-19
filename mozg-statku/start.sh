#!/usr/bin/env bash
# Mózg statku — start całego serwera pokładowego jedną komendą.
#   ./start.sh                 # wykryje IP laptopa
#   ./start.sh 192.168.8.100   # albo podaj stałe IP (zalecane na demo)
#   ./start.sh --llm           # dodatkowo Ollama w Dockerze
set -euo pipefail
cd "$(dirname "$0")"

PROFILE_ARGS=()
IP=""
for a in "$@"; do
  case "$a" in
    --llm) PROFILE_ARGS+=(--profile llm) ;;
    --gpu) PROFILE_ARGS+=(-f docker-compose.yml -f docker-compose.gpu.yml --profile llm) ;;
    *) IP="$a" ;;
  esac
done

detect_ip() {
  if command -v ipconfig >/dev/null 2>&1 && ipconfig getifaddr en0 >/dev/null 2>&1; then ipconfig getifaddr en0; return; fi
  if command -v hostname >/dev/null 2>&1 && hostname -I >/dev/null 2>&1; then hostname -I | awk '{print $1}'; return; fi
  echo 127.0.0.1
}
IP="${IP:-$(detect_ip)}"
echo "▶ IP serwera: $IP"

# .env
[ -f .env ] || cp .env.example .env
if grep -q '^SERVER_IP=' .env; then
  sed -i.bak "s/^SERVER_IP=.*/SERVER_IP=$IP/" .env && rm -f .env.bak
else
  echo "SERVER_IP=$IP" >> .env
fi

# certyfikat (nowy, gdy brak albo zmieniło się IP)
if [ ! -f certs/server.pem ] || ! openssl x509 -in certs/server.pem -noout -ext subjectAltName 2>/dev/null | grep -Eq "IP Address:${IP//./\\.}(,|\$)"; then
  ./scripts/certs.sh "$IP"
fi

mkdir -p data/ship data/shore pwa-dist

docker compose ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} up -d --build

echo -n "▶ czekam na API"
for _ in $(seq 1 60); do
  if curl -fsk "https://localhost/api/health" >/dev/null 2>&1 || curl -fs "http://localhost:8000/api/health" >/dev/null 2>&1; then
    echo " ✔"; break; fi
  echo -n "."; sleep 1
done

cat <<EOF

  API serwera:                     https://$IP/api/health
  Stan kolejki na ląd:             https://$IP/api/sync/status
  Atrapa armatora (API):           http://$IP:9000/api/stats
  Certyfikat CA dla telefonów:     http://$IP/ca.crt
  MQTT dla aplikacji (MQTT.js):    wss://$IP/mqtt
  Test end-to-end:                 python3 scripts/e2e_test.py
  Logi:                            docker compose logs -f api
EOF
