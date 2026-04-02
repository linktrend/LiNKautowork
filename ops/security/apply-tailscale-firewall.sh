#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $0 [--ports "5678 8080 4222 8222"] [--iface tailscale0]

Allows selected ports only via tailscale interface and drops public access.
Rules are installed in DOCKER-USER chain.
USAGE
}

PORTS="5678 8080 4222 8222"
IFACE="tailscale0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ports)
      PORTS="$2"
      shift 2
      ;;
    --iface)
      IFACE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 1
      ;;
  esac
done

for port in $PORTS; do
  while iptables -C DOCKER-USER -i "$IFACE" -p tcp --dport "$port" -j ACCEPT 2>/dev/null; do
    iptables -D DOCKER-USER -i "$IFACE" -p tcp --dport "$port" -j ACCEPT
  done
  while iptables -C DOCKER-USER -p tcp --dport "$port" -j DROP 2>/dev/null; do
    iptables -D DOCKER-USER -p tcp --dport "$port" -j DROP
  done

  iptables -I DOCKER-USER 1 -i "$IFACE" -p tcp --dport "$port" -j ACCEPT
  iptables -I DOCKER-USER 2 -p tcp --dport "$port" -j DROP
done

echo "Applied tailscale-only firewall rules on ports: $PORTS"
iptables -S DOCKER-USER
