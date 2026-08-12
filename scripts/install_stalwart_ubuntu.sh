#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this script with sudo: sudo bash scripts/install_stalwart_ubuntu.sh" >&2
  exit 1
fi

apt-get update
apt-get install -y ca-certificates curl

installer="$(mktemp)"
trap 'rm -f "$installer"' EXIT

curl --proto '=https' --tlsv1.2 -sSf https://get.stalw.art/install.sh -o "$installer"
sh "$installer"

systemctl enable stalwart >/dev/null 2>&1 || true
systemctl restart stalwart

echo
echo "Stalwart native installation completed."
echo "Service status:"
systemctl --no-pager --full status stalwart || true
echo
echo "Typical paths:"
echo "  Configuration: /etc/stalwart/config.json"
echo "  Environment:   /etc/stalwart/stalwart.env"
echo "  Data:          /var/lib/stalwart/"
echo "  Logs:          /var/log/stalwart/"
echo
echo "Before public email use, configure your mail hostname, DNS, PTR/rDNS and confirm outbound TCP/25 with your VPS provider."
