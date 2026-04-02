#!/usr/bin/env bash
set -euo pipefail

SERVICE_SCRIPT='/usr/local/sbin/linkautowork-tailscale-firewall.sh'
SERVICE_UNIT='/etc/systemd/system/linkautowork-tailscale-firewall.service'

install -m 700 ops/security/apply-tailscale-firewall.sh "$SERVICE_SCRIPT"

cat > "$SERVICE_UNIT" <<UNIT
[Unit]
Description=LiNKautowork tailscale-only firewall rules
After=docker.service tailscaled.service
Wants=docker.service tailscaled.service

[Service]
Type=oneshot
ExecStart=$SERVICE_SCRIPT
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now linkautowork-tailscale-firewall.service
systemctl --no-pager --full status linkautowork-tailscale-firewall.service | sed -n '1,20p'
