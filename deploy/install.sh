#!/usr/bin/env bash
# Installs Christmas Piano on a fresh Pi. Run from the checkout with: sudo deploy/install.sh
# Safe to run again: it never overwrites the config, login or existing Sound Packs.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR=/var/lib/christmas-piano
OWNER=piano
SERVICES=(christmas-piano christmas-piano-web christmas-piano-wifi)

apt-get update
apt-get install -y python3-pygame python3-rpi.gpio python3-flask python3-waitress ffmpeg polkitd dnsmasq-base

install -d -o "$OWNER" -g "$OWNER" -m 750 "$DATA_DIR" "$DATA_DIR/sounds"
for pack in "$REPO_DIR"/sounds/*/; do
  name="$(basename "$pack")"
  if [[ ! -e "$DATA_DIR/sounds/$name" ]]; then
    cp -r "$pack" "$DATA_DIR/sounds/$name"
    find "$DATA_DIR/sounds/$name" -name .DS_Store -delete
    chown -R "$OWNER:$OWNER" "$DATA_DIR/sounds/$name"
  fi
done

install -d /etc/polkit-1/rules.d
install -m 644 "$REPO_DIR/deploy/50-christmas-piano.rules" /etc/polkit-1/rules.d/50-christmas-piano.rules
for service in "${SERVICES[@]}"; do
  install -m 644 "$REPO_DIR/deploy/$service.service" "/etc/systemd/system/$service.service"
done
systemctl daemon-reload
systemctl enable "${SERVICES[@]}"
systemctl restart "${SERVICES[@]}"

echo "Installed. Set the page login with: sudo -u $OWNER CHRISTMAS_PIANO_DATA=$DATA_DIR python3 -m christmas_piano.setup_login"
