# PyKeyCatcher

This is a generic script for catching keystrokes from a specific HID keyboard device. This repo is designed to by used in conjunction with generic addon USB keyboards, configured with the repo [ch57x-keyboard-tool](https://github.com/kriomant/ch57x-keyboard-tool).

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running as an unprivileged user

By default your user probably can't read and write any USB device. To open a single USB device up to users you can do so with a udev rule.
```
# Find the ID of your device
sudo lsusb

# Create a udev rule for it, supliment the ID's for your device
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="1189", ATTR{idProduct}=="8890", MODE="0666"' | sudo tee /etc/udev/rules.d/40-usbkeyboard.rules 
```

## Usage

Either `--config` or `--manual` must be provided. Use  `--help` for a full list of options.
```bash
./pykeycatcher.py --manual
./pykeycatcher.py --config config.yaml
```
