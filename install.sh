#!/usr/bin/env bash
# Install pykeycatcher for the current user, running from this checkout.
# Safe to re-run: after a git pull, or after changing the device IDs in the config.
set -euo pipefail

repo=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
config_home=${XDG_CONFIG_HOME:-$HOME/.config}
config=$config_home/pykeycatcher/config.yaml
unit=$config_home/systemd/user/pykeycatcher.service
rule=/etc/udev/rules.d/99-pykeycatcher.rules

if [[ $EUID -eq 0 ]]; then
	echo "Run this as the user who will use the keypad, not as root. It calls sudo where needed." >&2
	exit 1
fi

echo "==> Installing Python dependencies into $repo/.venv"
python3 -m venv "$repo/.venv"
"$repo/.venv/bin/pip" install --quiet --disable-pip-version-check --upgrade -r "$repo/requirements.txt"

new_config=false
if [[ ! -e $config ]]; then
	echo "==> Copying the example config to $config"
	install -Dm644 "$repo/config.yaml.example" "$config"
	new_config=true
fi

# The udev rule matches the device named in the config, in the hex form lsusb prints
read -r vendor product < <("$repo/.venv/bin/python" -c '
import sys, yaml
device = yaml.safe_load(open(sys.argv[1]))["device"]
print("%04x %04x" % (device["vendor_id"], device["product_id"]))
' "$config")

echo "==> Writing $rule for device $vendor:$product"
sudo tee "$rule" >/dev/null <<EOF
# Written by pykeycatcher's install.sh. Re-run it to change the device.
#
# Numbered 99 to sort after 50-udev-default.rules, which sets every USB device to
# MODE="0664" and would override a lower-numbered rule. ":=" stops later rules
# changing the values again.
SUBSYSTEM=="usb", ATTR{idVendor}=="$vendor", ATTR{idProduct}=="$product", GROUP:="input", MODE:="0660"
KERNEL=="hidraw*", ATTRS{idVendor}=="$vendor", ATTRS{idProduct}=="$product", GROUP:="input", MODE:="0660"

# Mirror actions write to /dev/uinput. Without this it is only usable during an
# active local login, so a service started at boot cannot open it.
KERNEL=="uinput", GROUP:="input", MODE:="0660", OPTIONS+="static_node=uinput"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger --action=add --subsystem-match=usb --subsystem-match=hidraw --subsystem-match=misc

relogin=false
if ! id -nG "$USER" | grep -qw input; then
	echo "==> Adding $USER to the input group"
	sudo usermod -aG input "$USER"
	relogin=true
elif ! id -nG | grep -qw input; then
	relogin=true
fi

echo "==> Writing $unit"
mkdir -p "$(dirname "$unit")"
cat >"$unit" <<EOF
[Unit]
Description=PyKeyCatcher HID keypad daemon
Documentation=https://github.com/lonk42/pykeycatcher

[Service]
ExecStart="$repo/.venv/bin/python" "$repo/pykeycatcher.py" --config "$config"
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --quiet pykeycatcher.service

echo
if $new_config; then
	echo "Edit $config, then start the service:"
	echo "  systemctl --user start pykeycatcher"
else
	systemctl --user restart pykeycatcher.service
	echo "pykeycatcher is running. Follow its log with:"
	echo "  journalctl --user -u pykeycatcher -f"
fi
if $relogin; then
	echo
	echo "Log out and back in so the input group applies. Until then the keypad cannot be opened."
fi
